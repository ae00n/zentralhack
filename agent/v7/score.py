"""v7 results against the hand check: hit rate per field and per tier, optionally written as the confidence table.

    python -m agent.v7.score            # data/results_v7 vs data/splits/challenge_qc.jsonl
    python -m agent.v7.score --fit      # also writes agent/v7_tiers.json (shown confidence = measured rate)

A tier's hit: Gemeinde right, and Ortschaft right where the checker gave one.
"""

import argparse
import json
from pathlib import Path

from data_pipeline.jsonl import read_jsonl
from data_pipeline.metrics import _same, score_challenge
from data_pipeline.qc import QC_FILE

from ..config import DATA_DIR
from .tiers import TABLE


def load(d: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(d.glob("challenge:*.json"))]


def by_tier(results: list[dict], qc: list[dict]) -> dict:
    truth = {t["id"]: t for t in qc}
    out: dict = {}
    for r in results:
        t = truth.get(r["photo_id"])
        if not t or not t.get("municipality"):
            continue
        f = r["fields"]
        tier = (r.get("settings") or {}).get("tier", "?")
        mun = f["municipality"]["value"]
        if not mun:
            hit = None  # abstained
        else:
            hit = _same("municipality", mun, t["municipality"]) and (
                not t.get("locality") or _same("locality", f["locality"]["value"], t["locality"]))
        cell = out.setdefault(tier, {"n": 0, "hits": 0, "abstained": 0, "misses": []})
        if hit is None:
            cell["abstained"] += 1
            continue
        cell["n"] += 1
        cell["hits"] += hit
        if not hit:
            cell["misses"].append(r["photo_id"])
    for cell in out.values():
        cell["rate"] = round(cell["hits"] / cell["n"], 3) if cell["n"] else None
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=str(DATA_DIR / "results_v7"))
    ap.add_argument("--fit", action="store_true")
    a = ap.parse_args()
    results, qc = load(Path(a.dir)), list(read_jsonl(QC_FILE))
    s = score_challenge(results, qc)
    print(f"checked {s['n_checked']}, scored {s['n_scored']}")
    for f, v in s["fields"].items():
        print(f"  {f:14} {v['hits']}/{v['answered']} right (answered {v['answered']} of {v['n']})")
    tiers = by_tier(results, qc)
    for t in sorted(tiers):
        c = tiers[t]
        print(f"  tier {t}: {c['hits']}/{c['n']} right, {c['abstained']} abstained, misses {c['misses']}")
    if a.fit:
        # (hits + 1) / (n + 2): 11 of 11 is evidence for "very often right", not proof of "always right"
        TABLE.write_text(json.dumps({t: {"n": c["n"], "hits": c["hits"], "rate": round((c["hits"] + 1) / (c["n"] + 2), 3)}
                                     for t, c in tiers.items() if c["n"] and t in ("A", "B", "C")}, indent=1))
        print(f"wrote {TABLE}")


if __name__ == "__main__":
    main()
