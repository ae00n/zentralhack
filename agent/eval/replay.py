"""Fast eval: every agent version against the hand check, in seconds and without API calls.

    python -m agent.eval.replay                # score v3, v5, v6 results side by side
    python -m agent.eval.replay --rerun        # re-run v6 on the hand-checked photos from caches only
    python -m agent.eval.replay --rerun --fit  # and write the measured confidence table (agent/v6_confidence.json)

--rerun uses the cached Claude answers (agent/.cache/v6) and the precomputed matches (data/matches), so a
change to the resolve rules or the registers is measured in seconds for $0. A photo whose Claude answer is
not cached yet is left out and named.

Hit rate = hits / answered (a null answer is an abstention, not a miss); coverage = answered / checked.
"""

import argparse
import json
import os

from data_pipeline.jsonl import read_jsonl
from data_pipeline.metrics import CHALLENGE_FIELDS, _same, load_results, score_challenge
from data_pipeline.paths import DATA_DIR
from data_pipeline.qc import QC_FILE

VERSIONS = {"v3": DATA_DIR / "results_v3", "v5": DATA_DIR / "results_v5", "v6": DATA_DIR / "results_v6"}


def table(scores: dict[str, dict]) -> None:
    names = list(scores)
    print(f"{'field':<13}" + "".join(f"{n:>22}" for n in names))
    for f in CHALLENGE_FIELDS:
        cells = []
        for n in names:
            m = scores[n]["fields"][f]
            cells.append(f"{m['hits']}/{m['answered']} hit, {m['answered']}/{m['n']} ans" if m["n"] else "-")
        print(f"{f:<13}" + "".join(f"{c:>22}" for c in cells))
    print("scored photos: " + ", ".join(f"{n} {s['n_scored']}" for n, s in scores.items()))


def rerun(qc: list[dict]) -> tuple[list[dict], list[str]]:
    os.environ["AGENT_CACHE_ONLY"] = "1"
    from .. import v6
    v6.CACHE_ONLY = True
    out, missing = [], []
    for t in qc:
        r = v6.analyze(t["id"])
        (out if r["settings"]["answer"] else missing).append(r if r["settings"]["answer"] else t["id"])
    return out, missing


def fit(res: list[dict], qc: list[dict]) -> dict:
    """{bucket: {field: {n, hits, rate}}}, rate = (hits + 1) / (n + 2) (one pseudo hit and miss, so 3 of 3
    reads 0.8, not 1.0). Only answered fields with a checked truth count."""
    from .. import v6
    truth = {t["id"]: t for t in qc}
    cells: dict = {}
    for r in res:
        b = r["settings"]["bucket"]
        for f in (*CHALLENGE_FIELDS, "coordinates"):
            key = "municipality" if f == "coordinates" else f  # the point is right when its Gemeinde is
            v = (r["fields"].get(key) or {}).get("value")
            t = truth[r["photo_id"]].get(key)
            if v in (None, [], "") or t in (None, []):
                continue
            c = cells.setdefault(b, {}).setdefault(f, {"n": 0, "hits": 0})
            c["n"] += 1
            c["hits"] += _same(key, v, t)
    for b in cells.values():
        for c in b.values():
            c["rate"] = round((c["hits"] + 1) / (c["n"] + 2), 3)
    v6.CONFIDENCE_FILE.write_text(json.dumps(cells, ensure_ascii=False, indent=1))
    return cells


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rerun", action="store_true")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--misses", action="store_true", help="list every wrong v6 field")
    a = ap.parse_args()
    if not QC_FILE.exists():
        raise SystemExit(f"no hand check yet: {QC_FILE} (fill it on https://zhfront.vatra.sh/qc/)")
    qc = list(read_jsonl(QC_FILE))
    scores = {n: score_challenge(load_results(d), qc) for n, d in VERSIONS.items() if d.exists()}
    if a.rerun:
        res, missing = rerun(qc)
        scores["v6 rerun"] = score_challenge(res, qc)
        if missing:
            print(f"not cached, left out: {', '.join(missing)}")
        if a.fit:
            cells = fit(res, qc)
            print("confidence table:", json.dumps(cells, ensure_ascii=False))
    print(f"{len(qc)} hand-checked photos")
    table(scores)
    if a.misses:
        last = scores.get("v6 rerun") or scores.get("v6")
        for x in last["misses"]:
            print(f"  miss {x['id']} {x['field']}: {x['agent']!r} vs {x['truth']!r}")


if __name__ == "__main__":
    main()
