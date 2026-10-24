"""v5 stage 5: confidence = measured hit rate, not a count of sources.

For retrieval answers ("match", "match_confirmed") a logistic model per field maps the match features
to the probability that the field is right, fitted on the Commons leave-one-out rows
(agent.eval.commons_loo). Paths with no measured data yet use the priors in PRIORS, marked as such in
the explanation; the hand-checked challenge photos replace them when they exist.

    python -m agent.calibration fit     # writes agent/calibration.json, prints the reliability table
"""

import json
import math
import sys
from pathlib import Path

FILE = Path(__file__).with_name("calibration.json")
FIELDS = ["municipality", "locality", "street", "coordinates"]
ACCEPT = 0.9  # overall confidence at or above this is not flagged for review; checked by `fit`

# Assumptions until the hand check measures them (per field). Deliberately below ACCEPT: an answer
# only Claude backs always goes to review.
PRIORS = {
    "claude_pick": {"municipality": 0.75, "locality": 0.7, "street": 0.4, "coordinates": 0.6},
    "claude_text": {"municipality": 0.8, "locality": 0.75, "street": 0.4, "coordinates": 0.6},
    "claude_name": {"municipality": 0.5, "locality": 0.4, "street": 0.0, "coordinates": 0.0},
}


def x(fe: dict) -> list[float]:
    return [math.log1p(fe.get("top_inliers", 0)), fe.get("group_share", 0.0), fe.get("agree10", 0) / 10]


def _load() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else {}


def score(fe: dict, path: str | None) -> dict:
    """{field: probability}. Buildings and landscape features follow the locality (no ground truth)."""
    if path is None:
        return {}
    cal = _load()
    if path in ("match", "match_confirmed") and cal.get("match"):
        out = {}
        for field, m in cal["match"].items():
            z = m["b"] + sum(w * v for w, v in zip(m["w"], x(fe)))
            out[field] = round(1 / (1 + math.exp(-z)), 3)
    elif path == "municipality":
        out = {"municipality": cal.get("municipality_rate", 0.6)}
    else:
        out = dict(PRIORS.get(path, {}))
    if "locality" in out:
        out["buildings"] = round(out["locality"] * 0.8, 3)
        out["landscape_features"] = out["locality"]
    return out


def source(path: str | None) -> str:
    cal = _load()
    if path in ("match", "match_confirmed", "municipality") and cal:
        return f"gemessen an {cal.get('n', '?')} Commons-Fotos"
    return "Annahme, noch nicht gemessen"


def _same(a, b) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def fit() -> None:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_predict

    from .eval.commons_loo import rows

    rs = rows()
    match = [r for r in rs if r["decided_by"] == "match"]
    X = np.array([x(r["features"]) for r in match])
    out = {"n": len(rs), "n_match": len(match), "match": {}}
    print(f"{len(rs)} rows, {len(match)} matched\n")
    for field in FIELDS:
        if field == "coordinates":
            y = np.array([r["dist_m"] is not None and r["dist_m"] <= 300 for r in match], dtype=int)
        else:
            y = np.array([_same((r["pred"] or {}).get(field), r["truth"].get(field)) for r in match], dtype=int)
        if len(set(y)) < 2:
            print(f"{field}: all {y[0] if len(y) else '?'}, constant")
            out["match"][field] = {"w": [0, 0, 0], "b": 4.0 if (len(y) and y[0]) else -4.0}
            continue
        lr = LogisticRegression(C=1.0)
        p = cross_val_predict(lr, X, y, cv=min(5, int(y.sum()), int(len(y) - y.sum())), method="predict_proba")[:, 1]
        lr.fit(X, y)
        out["match"][field] = {"w": [round(float(v), 4) for v in lr.coef_[0]], "b": round(float(lr.intercept_[0]), 4)}
        print(f"{field}: base rate {y.mean():.0%}")
        for lo, hi in ((0, .5), (.5, .7), (.7, .8), (.8, .9), (.9, 1.01)):
            sel = (p >= lo) & (p < hi)
            if sel.any():
                print(f"  predicted {lo:.1f}-{min(hi, 1):.1f}: n={sel.sum():3}  actual {y[sel].mean():.0%}")
    mun = [r for r in rs if r["decided_by"] == "municipality"]
    if mun:
        out["municipality_rate"] = round(sum(_same(r["pred"]["municipality"], r["truth"]["municipality"])
                                             for r in mun) / len(mun), 3)
        print(f"\nmunicipality-only votes: {len(mun)}, correct {out['municipality_rate']:.0%}")
    FILE.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"\nwrote {FILE}")


if __name__ == "__main__":
    if sys.argv[1:] == ["fit"]:
        fit()
    else:
        print(__doc__)
