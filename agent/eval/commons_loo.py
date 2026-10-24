"""Leave-one-out eval of agent.pipeline on modern Wikimedia Commons photos (free ground truth).

Each sampled Commons photo is located with itself and every photo by the same photographer hidden
(no near-duplicates from one uploader). The truth comes from the official registers at the photo's
own Commons coordinate, so it is scored on the same names the challenge export uses.

    python -m agent.eval.commons_loo [--n 300] [--workers 1] [--threads 6]   # resumable, appends to the jsonl
    python -m agent.eval.commons_loo --table                   # hit rates from what is there

Output: agent/.cache/v5/commons_loo.jsonl, one line per photo (truth, prediction, features). It is
also the training set for agent.calibration.
"""

import argparse
import json
import random
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

import data_pipeline as dp

from .. import pipeline
from ..config import CACHE_DIR

OUT = CACHE_DIR / "v5" / "commons_loo.jsonl"
SEED = 24


def _commons() -> list[dict]:
    from data_pipeline.api import _records  # one pass over all records, already cached by data_pipeline

    return [r for r in _records().values() if r["source"] == "commons"
            and ((r.get("date") or {}).get("year_from") or 0) >= 2000 and (r.get("location") or {}).get("lat")]


def sample(n: int) -> tuple[list[dict], dict[str, list[str]]]:
    recs = _commons()
    by_author = defaultdict(list)
    for r in recs:
        by_author[r.get("photographer") or "?"].append(r["id"])
    rng = random.Random(SEED)
    return rng.sample(recs, min(n, len(recs))), by_author


def one(rec: dict, hide: list[str]) -> dict:
    lat, lon = rec["location"]["lat"], rec["location"]["lon"]
    truth = pipeline.names(lat, lon)
    res = pipeline.locate(str(dp.image_file(rec)), exclude_ids=hide)
    dist = None
    if res["point"]:
        dist = round(pipeline.haversine_m((lat, lon), (res["point"]["lat"], res["point"]["lon"])))
    return {"id": rec["id"], "truth": {k: truth.get(k) for k in ("locality", "municipality", "street", "building")},
            "pred": res["names"], "decided_by": res["decided_by"], "dist_m": dist, "features": res["features"],
            "top_hits": [{k: h[k] for k in ("id", "source", "score", "inliers")} for h in res["hits"][:5]]}


def _done() -> set[str]:
    if not OUT.exists():
        return set()
    return {json.loads(l)["id"] for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()}


def run(n: int, workers: int, threads: int) -> None:
    recs, by_author = sample(n)
    done = _done()
    todo = [r for r in recs if r["id"] not in done]
    print(f"{len(todo)} to run ({len(done)} done)", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(workers, initializer=pipeline.set_threads, initargs=(threads,)) as ex, OUT.open("a", encoding="utf-8") as f:
        futs = {ex.submit(one, r, by_author[r.get("photographer") or "?"]): r["id"] for r in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                row = fut.result()
            except Exception as e:  # one bad image must not stop the run
                print(f"{futs[fut]}: {e!r}", flush=True)
                continue
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            if i % 10 == 0:
                print(f"{i}/{len(todo)}", flush=True)


def _same(a, b) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def rows() -> list[dict]:
    return [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]


def table() -> None:
    rs = rows()
    n = len(rs)
    print(f"{n} Commons photos, leave-one-out (same photographer hidden)\n")
    for mode in ("match", "municipality", None):
        part = [r for r in rs if r["decided_by"] == mode]
        print(f"decided_by={mode}: {len(part)} ({len(part) / n:.0%})")
    print()
    print(f"{'field':14} {'answered':>9} {'correct':>9} {'precision':>10} {'of all':>7}")
    for field in ("municipality", "locality", "street", "building"):
        answered = [r for r in rs if (r["pred"] or {}).get(field)]
        correct = [r for r in answered if _same(r["pred"][field], r["truth"].get(field))]
        prec = len(correct) / len(answered) if answered else 0
        print(f"{field:14} {len(answered):9} {len(correct):9} {prec:10.0%} {len(correct) / n:7.0%}")
    d = sorted(r["dist_m"] for r in rs if r["dist_m"] is not None)
    if d:
        q = lambda p: d[min(len(d) - 1, int(p * len(d)))]
        print(f"\ndistance to truth (matched only, n={len(d)}): median {q(.5)} m, p75 {q(.75)} m, p90 {q(.9)} m,"
              f" within 300 m {sum(x <= 300 for x in d) / len(d):.0%}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--threads", type=int, default=6, help="torch threads per worker (keep the box usable)")
    ap.add_argument("--table", action="store_true")
    a = ap.parse_args()
    if not a.table:
        run(a.n, a.workers, a.threads)
    table()


if __name__ == "__main__":
    main()
