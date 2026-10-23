"""Consistency check: the same photo analysed N times independently must name the same place.

Single runs are not stable (about 15% of photos got a different Gemeinde in a second run), so a batch
can analyse each photo twice. The runs agree when every run gives the same locality and municipality
(case-insensitive, an unknown value counts as a value, two unknowns agree). The kept result is the run
with the highest overall confidence. On disagreement it needs review and its overall confidence is capped
below the acceptance line, whatever the source count said.

    combine(runs)                  -> the kept result, with an extra key "consistency"
    check(runs)                    -> {"runs", "agree", "values"} only
    from_history(photo_id, last=2) -> check() over the last cached runs, no new analysis
"""

import copy

from . import results

DISAGREE_CAP = 0.6
NUMBER_WORD = {2: "Zwei", 3: "Drei", 4: "Vier", 5: "Fünf"}


def _value(r: dict, name: str):
    return ((r.get("fields") or {}).get(name) or {}).get("value")


def _norm(v):
    if v in (None, "", []):
        return None
    if isinstance(v, list):
        return tuple(str(x).strip().casefold() for x in v)
    return str(v).strip().casefold()


def _overall(r: dict):
    """The run's own overall confidence (before any cap a previous combine applied)."""
    c = r.get("consistency") or {}
    own = c.get("own_overall")
    return own if own is not None else r.get("overall_confidence")


def check(runs: list[dict]) -> dict:
    """Agreement of the runs on locality and municipality. Pure, no side effects."""
    values = [{"locality": _value(r, "locality"), "municipality": _value(r, "municipality"),
               "overall": _overall(r)} for r in runs]
    keys = {(_norm(v["locality"]), _norm(v["municipality"])) for v in values}
    return {"runs": len(runs), "agree": len(keys) <= 1, "values": values}


def place(v: dict) -> str:
    loc, mun = v.get("locality"), v.get("municipality")
    if loc and mun and _norm(loc) != _norm(mun):
        return f"{loc}, {mun}"
    return str(mun or loc or "nicht bestimmbar")


def sentence(c: dict) -> str:
    """The German sentence appended to confidence_explanation."""
    n = c["runs"]
    if c["agree"]:
        return f"In {n} unabhängigen Analysen übereinstimmend."
    places = " / ".join(dict.fromkeys(place(v) for v in c["values"]))
    return f"{NUMBER_WORD.get(n, str(n))} unabhängige Analysen nennen verschiedene Orte ({places}); Prüfung nötig."


def combine(runs: list[dict]) -> dict:
    """The kept result of N independent runs of one photo (the most confident run), marked with its
    consistency. With a single run it is returned unchanged."""
    if not runs:
        raise ValueError("combine needs at least one run")
    if len(runs) == 1:
        return runs[0]
    c = check(runs)
    best = max(range(len(runs)), key=lambda i: (c["values"][i]["overall"] or 0.0, -i))
    kept = copy.deepcopy(runs[best])
    own = c["values"][best]["overall"]
    kept["consistency"] = {**c, "kept_run_id": kept.get("run_id"), "own_overall": own}
    explanation = (kept.get("confidence_explanation") or "").rstrip()
    kept["confidence_explanation"] = f"{explanation} {sentence(c)}".strip()
    if not c["agree"]:
        kept["needs_review"] = True
        kept["status"] = "needs_review"
        kept["overall_confidence"] = min(own or 0.0, DISAGREE_CAP)
    return kept


def from_history(photo_id: str, last: int = 2) -> dict | None:
    """check() over the last `last` cached runs of a photo (results.history), or None with fewer runs."""
    runs = results.history(photo_id)[-last:]
    if len(runs) < 2:
        return None
    return check(runs)
