"""Eval v2 metrics: one scoring function for every experiment and the final eval run.

    from data_pipeline.metrics import score
    summary = score(predictions)          # predictions: [{id, municipality, municipality_confidence,
                                          #                year, year_low, year_high, place_name_printed?}]
    python -m data_pipeline.metrics predictions.jsonl

Truth comes from data/splits/eval.jsonl (docs/CONTRACTS.md). For the card_posted subset the
catalogue year is only an upper bound (often the postmark), so it gets its own year metric:
how often the guess is at or before that year.
"""

import argparse
import json
import statistics as st
from pathlib import Path

from .jsonl import read_jsonl
from .paths import SPLITS

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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("predictions", type=Path)
    a = ap.parse_args()
    print(json.dumps(score(list(read_jsonl(a.predictions))), indent=1))


if __name__ == "__main__":
    main()
