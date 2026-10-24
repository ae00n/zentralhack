"""Automatic eval: v6 on Wikimedia Commons photos with a known position, scored without a hand check.

    python -m agent.eval.commons [--n 100] [--seed 7]    # ~$0.03 per photo, a few minutes
    python -m agent.eval.commons --score                 # rescore the saved runs, no API calls

Commons photos from 2003 to 2013 inside the canton look like the challenge photos (modern colour views
of villages and buildings). Truth: Gemeinde = the polygon at the Commons position, Ortschaft = the PLZ
locality of the nearest GWR entrance, street = that entrance's street when it is within 50 m. Claude
sees only the image and the date, never the Commons title or categories. No reference matches are given
(they would contain the photo itself), so this measures the Claude + registers part of v6.

Limits: a Commons position marks the camera or sometimes the subject (precision about 100 m), so a
street "miss" can be a near miss; Gemeinde and Ortschaft are robust to that.
"""

import argparse
import json
import random
import statistics
from concurrent.futures import ThreadPoolExecutor

import data_pipeline as dp
from data_pipeline.jsonl import read_jsonl
from data_pipeline.metrics import score_challenge
from data_pipeline.paths import DATA_DIR, RECORDS
from data_pipeline.places import _haversine_m

OUT = DATA_DIR / "eval_commons"
FULL = DATA_DIR / "images" / "commons_full"  # originals, read by v6.original()


def sample(n: int, seed: int) -> list[dict]:
    recs = [r for r in read_jsonl(RECORDS / "commons.jsonl")
            if 2003 <= ((r.get("date") or {}).get("year_from") or 0) <= 2013 and r.get("municipality")
            and (r.get("image") or {}).get("path")]
    random.Random(seed).shuffle(recs)
    return recs[:n]


def originals(recs: list[dict]) -> int:
    """Download the Commons originals (max 3000 px) for the sample, so v6 sees them as it sees the
    challenge originals. Returns how many are on disk."""
    import io

    import httpx
    from PIL import Image
    FULL.mkdir(parents=True, exist_ok=True)
    import re

    from data_pipeline.http import USER_AGENT
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
    for r in recs:
        p, url = FULL / f"{r['source_id']}.jpg", (r.get("raw") or {}).get("thumb_url")
        if p.exists() or not url:
            continue
        try:
            # the original file, not the thumbnail renderer (which refuses bulk requests)
            m = re.match(r"https://[^/]+/wikipedia/commons/thumb/(\w/\w\w/[^/]+)/", url)
            r_ = client.get(f"https://upload.wikimedia.org/wikipedia/commons/{m.group(1)}" if m else url)
            r_.raise_for_status()
            im = Image.open(io.BytesIO(r_.content)).convert("RGB")
        except Exception as e:  # a missing original only means v6 gets the 1024 px copy
            print(f"  original failed {r['id']}: {e}", flush=True)
            continue
        im.thumbnail((3000, 3000))
        im.save(p, "JPEG", quality=90)
    return sum((FULL / f"{r['source_id']}.jpg").exists() for r in recs)


def truth(rec: dict) -> dict:
    loc = rec["location"]
    a = dp.address_at(loc["lat"], loc["lon"], 50, limit=1)
    near = (a.get("addresses") or [None])[0]
    return {"id": rec["id"], "municipality": rec["municipality"], "locality": a.get("ortschaft"),
            "street": near["street"] if near else None, "buildings": None, "lat": loc["lat"], "lon": loc["lon"]}


def run(recs: list[dict], workers: int) -> None:
    from .. import v6
    OUT.mkdir(parents=True, exist_ok=True)

    def one(rec):
        p = OUT / f"{rec['id'].replace(':', '_')}.json"
        if p.exists():
            return
        r = v6.analyze(rec["id"])
        p.write_text(json.dumps(r, ensure_ascii=False))
        print(f"{rec['id']}: {r['trace'][-1]['text']}", flush=True)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, recs))


def score(recs: list[dict]) -> dict:
    truths = [truth(r) for r in recs]
    res = [json.loads(p.read_text()) for r in recs if (p := OUT / f"{r['id'].replace(':', '_')}.json").exists()]
    s = score_challenge(res, truths)
    by_t = {t["id"]: t for t in truths}
    d = [_haversine_m(c["lat"], c["lon"], by_t[r["photo_id"]]["lat"], by_t[r["photo_id"]]["lon"])
         for r in res if (c := (r["fields"].get("coordinates") or {}).get("value"))]
    s["distance_m"] = {"n": len(d), "median": round(statistics.median(d)) if d else None,
                       "within_500m": round(sum(x <= 500 for x in d) / len(d), 3) if d else None}
    paths: dict = {}
    for r in res:
        t, v = by_t[r["photo_id"]], r["fields"]["municipality"]["value"]
        c = paths.setdefault(r["settings"]["bucket"], {"n": 0, "gemeinde_hits": 0})
        c["n"] += 1
        c["gemeinde_hits"] += bool(v) and dp.registers._gem(v) == dp.registers._gem(t["municipality"])
    s["by_bucket"] = paths
    return s


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--score", action="store_true", help="only rescore the saved runs")
    ap.add_argument("--out", default="eval_commons", help="folder under data/ for this run's results")
    a = ap.parse_args()
    global OUT
    OUT = DATA_DIR / a.out
    recs = sample(a.n, a.seed)
    if not a.score:
        print(originals(recs), "originals on disk", flush=True)
        run(recs, a.workers)
    s = score(recs)
    print(f"{s['n_scored']} of {len(recs)} Commons photos scored")
    for f, m in s["fields"].items():
        if m["n"]:
            print(f"{f:<13} {m['hits']}/{m['answered']} right of answered, answered {m['answered']}/{m['n']}")
    print("distance to truth:", s["distance_m"])
    for b, c in sorted(s["by_bucket"].items()):
        print(f"  {b:<24} Gemeinde {c['gemeinde_hits']}/{c['n']}")
    (OUT / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
