"""Eval v2 metrics: one scoring function for every experiment and the final eval run.

    from data_pipeline.metrics import score
    summary = score(predictions)          # predictions: [{id, municipality, municipality_confidence,
                                          #                year, year_low, year_high, place_name_printed?}]
    python -m data_pipeline.metrics predictions.jsonl
    python -m data_pipeline.metrics challenge [--results data/results]   # v3: agent vs the hand check

Truth comes from data/splits/eval.jsonl (docs/CONTRACTS.md). For the card_posted subset the
catalogue year is only an upper bound (often the postmark), so it gets its own year metric:
how often the guess is at or before that year.
"""

import argparse
import json
import re
import statistics as st
import sys
from pathlib import Path

from .jsonl import read_jsonl
from .paths import DATA_DIR, SPLITS

CONF_LEVELS = (0.7, 0.8, 0.9)


def _share(xs: list[bool]) -> float | None:
    return round(sum(xs) / len(xs), 3) if xs else None


def _year_metrics(rows: list[tuple[dict, dict]]) -> dict:
    exact = [(t, p) for t, p in rows if not t.get("year_is_upper_bound") and p.get("year") is not None]
    bound = [(t, p) for t, p in rows if t.get("year_is_upper_bound") and p.get("year") is not None]
    err = [abs(p["year"] - t["year_from"]) for t, p in exact]
    ranged = [(t, p) for t, p in exact if p.get("year_low") is not None and p.get("year_high") is not None]
    out = {
        "n": len(exact),
        "median_error": st.median(err) if err else None,
        "within_5": _share([e <= 5 for e in err]),
        "within_10": _share([e <= 10 for e in err]),
        "range_coverage": _share([p["year_low"] <= t["year_from"] <= p["year_high"] for t, p in ranged]),
        "range_median_width": st.median(p["year_high"] - p["year_low"] for _, p in ranged) if ranged else None,
    }
    if bound:
        out["upper_bound_n"] = len(bound)
        out["at_or_before_bound"] = _share([p["year"] <= t["year_from"] for t, p in bound])
    return out


def _muni_metrics(rows: list[tuple[dict, dict]]) -> dict:
    hit = [(p.get("municipality") == t["municipality"], p) for t, p in rows]
    out = {"n": len(hit), "accuracy": _share([h for h, _ in hit])}
    for flag, name in ((True, "printed"), (False, "not_printed")):
        sub = [h for h, p in hit if p.get("place_name_printed") is flag]
        if sub:
            out[f"accuracy_{name}"] = _share(sub)
            out[f"n_{name}"] = len(sub)
    for c in CONF_LEVELS:
        sub = [h for h, p in hit if (p.get("municipality_confidence") or 0) >= c]
        out[f"conf_{c}"] = {"coverage": _share([True] * len(sub) + [False] * (len(hit) - len(sub))),
                            "accuracy": _share(sub)}
    return out


def score(predictions: list[dict], truth: list[dict] | None = None) -> dict:
    truth = truth if truth is not None else list(read_jsonl(SPLITS / "eval.jsonl"))
    by_id = {p["id"]: p for p in predictions}
    pairs = [(t, by_id[t["id"]]) for t in truth if t["id"] in by_id]
    out = {"n_truth": len(truth), "n_scored": len(pairs),
           "all": {"municipality": _muni_metrics(pairs), "year": _year_metrics(pairs)}}
    for subset in sorted({t.get("subset") for t in truth if t.get("subset")}):
        sub = [(t, p) for t, p in pairs if t.get("subset") == subset]
        if sub:
            out[subset] = {"municipality": _muni_metrics(sub), "year": _year_metrics(sub)}
    return out


# ---------------------------------------------------------------- challenge (v3): agent results vs the hand check

CHALLENGE_FIELDS = ("locality", "municipality", "buildings", "street")
CONF_BINS = ((0.0, 0.6), (0.6, 0.85), (0.85, 1.01))


def _same(field: str, pred, truth) -> bool:
    from .places import _norm
    if field == "buildings":  # any predicted name matches any checked one ("Hotel Schwert" ~ "Schwert")
        p, t = [_norm(x) for x in pred or []], [_norm(x) for x in truth or []]
        return any(a and b and (a in b or b in a) for a in p for b in t)
    a, b = _norm(pred), _norm(truth)
    a, b = a.removesuffix(" sz"), b.removesuffix(" sz")  # "Seewen SZ" ~ "Seewen"
    if field == "street":  # the street counts, not the house number ("Hauptplatz 3" ~ "Hauptplatz")
        a, b = re.sub(r"(\s\d+\w?)+$", "", a), re.sub(r"(\s\d+\w?)+$", "", b)
    return bool(a) and a == b


def score_challenge(results: list[dict], qc: list[dict] | None = None) -> dict:
    """Agent results (data/results/<id>.json, CONTRACTS section 3) against splits/challenge_qc.jsonl.

    Per field: n (checked photos with a known truth), answered, hits, hit_rate (hits / answered),
    coverage (answered / n), and the hit rate per field-confidence bin. A null truth is skipped
    (the checker could not tell); a null prediction is an abstention, not a miss.
    """
    from .qc import QC_FILE
    qc = qc if qc is not None else list(read_jsonl(QC_FILE))
    by_id = {r["photo_id"]: r for r in results}
    out = {"n_checked": len(qc), "n_scored": sum(t["id"] in by_id for t in qc), "fields": {}, "misses": []}
    for f in CHALLENGE_FIELDS:
        rows = []
        for t in qc:
            r = by_id.get(t["id"])
            if r is None or t.get(f) in (None, []):
                continue
            fld = (r.get("fields") or {}).get(f) or {}
            v, c = fld.get("value"), fld.get("confidence") or 0
            answered = v not in (None, [], "")
            hit = answered and _same(f, v, t[f])
            rows.append((answered, hit, c))
            if answered and not hit:
                out["misses"].append({"id": t["id"], "field": f, "agent": v, "truth": t[f], "confidence": c})
        ans = [h for a, h, _ in rows if a]
        bins = {}
        for lo, hi in CONF_BINS:
            sub = [h for a, h, c in rows if a and lo <= c < hi]
            bins[f"{lo:g}-{min(hi, 1):g}"] = {"n": len(sub), "hit_rate": _share(sub)}
        out["fields"][f] = {"n": len(rows), "answered": len(ans), "hits": sum(ans), "hit_rate": _share(ans),
                            "coverage": _share([a for a, _, _ in rows]), "by_confidence": bins}
    return out


def load_results(folder: Path) -> list[dict]:
    """data/results/challenge:*.json (latest result per photo; history/ is not read)."""
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("challenge:*.json"))]


def _print_challenge(s: dict) -> None:
    print(f"{s['n_scored']} of {s['n_checked']} hand-checked photos have a result")
    print(f"{'field':<13} {'n':>3} {'answered':>8} {'hits':>5} {'hit rate':>9} {'coverage':>9}   by confidence")
    for f, m in s["fields"].items():
        bins = "  ".join(f"{k}: {v['hit_rate'] if v['hit_rate'] is not None else '-'} ({v['n']})"
                         for k, v in m["by_confidence"].items())
        print(f"{f:<13} {m['n']:>3} {m['answered']:>8} {m['hits']:>5} {str(m['hit_rate']):>9} {str(m['coverage']):>9}   {bins}")
    for x in s["misses"]:
        print(f"  miss {x['id']} {x['field']}: agent {x['agent']!r} ({x['confidence']}) vs checked {x['truth']!r}")


def main() -> None:
    if sys.argv[1:2] == ["challenge"]:
        ap = argparse.ArgumentParser(prog="python -m data_pipeline.metrics challenge")
        ap.add_argument("--results", type=Path, default=DATA_DIR / "results")
        ap.add_argument("--json", action="store_true", help="print the summary as JSON")
        a = ap.parse_args(sys.argv[2:])
        s = score_challenge(load_results(a.results))
        print(json.dumps(s, indent=1, ensure_ascii=False)) if a.json else _print_challenge(s)
        return
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("predictions", type=Path)
    a = ap.parse_args()
    print(json.dumps(score(list(read_jsonl(a.predictions))), indent=1))


if __name__ == "__main__":
    main()
