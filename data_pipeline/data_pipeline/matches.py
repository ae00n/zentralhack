"""Precomputed reference matches for the challenge photos: data/matches/<photo_id>.json.

    python -m data_pipeline.matches build [--priority 1] [--limit N]   # skips photos already done for this index
    python -m data_pipeline.matches show challenge:SG.CIV.17.3

Retrieval (MegaLoc top 20) and the geometric check (LightGlue on the top 10, ~1 s per pair on CPU) are
the slow part of every agent run and give the same answer every time, so they run once per index
version. The agent reads `matches(photo_id)` instead of searching again; an eval replays in seconds.

File: {photo_id, index: {model, n, created_at}, hits: [{id, source, score, inliers, verified, lat, lon,
precision_m, municipality, title, year, heading, image}]}, verified first (most inliers first), then score.
verified means inliers >= VERIFY_MIN (30: 84% share the place; 100 and more is strong).
"""

import argparse
import json
from datetime import datetime, timezone

from .api import get_record, image_file, similar_images
from .jsonl import read_jsonl
from .paths import DATA_DIR, INDEX, RECORDS, ensure

MATCHES = DATA_DIR / "matches"
K_VERIFY = 10
K_WIDE = 20
VERIFY_MIN = 30


def index_version() -> dict:
    meta = json.loads((INDEX / "megaloc.meta.json").read_text())
    return {"model": "megaloc", "n": meta["n"], "created_at": meta["created_at"]}


def _hit(h: dict) -> dict:
    rec = h["record"]
    loc = rec.get("location") or {}
    return {"id": rec["id"], "source": rec["source"], "score": round(h["score"], 4),
            "inliers": h.get("inliers"), "verified": (h.get("inliers") or 0) >= VERIFY_MIN,
            "lat": loc.get("lat"), "lon": loc.get("lon"), "precision_m": loc.get("precision_m"),
            "municipality": rec.get("municipality"), "title": rec.get("title"),
            "year": (rec.get("date") or {}).get("year_from"),
            "heading": (rec.get("camera") or {}).get("azimuth"), "image": (rec.get("image") or {}).get("path")}


def _path(photo_id: str):
    return MATCHES / f"{photo_id.replace(':', '_')}.json"


def compute(photo_id: str) -> dict:
    rec = get_record(photo_id)
    img = str(image_file(rec))
    checked = similar_images(img, k=K_VERIFY, model="megaloc", verify=True, exclude_ids=[photo_id])
    seen = {h["id"] for h in checked}
    wide = [h for h in similar_images(img, k=K_WIDE, model="megaloc", exclude_ids=[photo_id]) if h["id"] not in seen]
    return {"photo_id": photo_id, "index": index_version(),
            "hits": [_hit(h) for h in checked] + [_hit(h) for h in wide][:K_WIDE - len(checked)],
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def matches(photo_id: str) -> dict | None:
    """The cached matches of a challenge photo, or None when not computed for the current index."""
    p = _path(photo_id)
    if not p.exists():
        return None
    m = json.loads(p.read_text())
    return m if m.get("index") == index_version() else None


def build(priority: int | None = None, limit: int | None = None) -> dict:
    ensure(MATCHES)
    recs = sorted(read_jsonl(RECORDS / "challenge.jsonl"),
                  key=lambda r: ((r.get("raw") or {}).get("priority") != 1, int(r["source_id"].rsplit(".", 1)[1])))
    if priority is not None:
        recs = [r for r in recs if (r.get("raw") or {}).get("priority") == priority]
    todo = [r["id"] for r in recs if matches(r["id"]) is None][:limit]
    print(f"{len(recs)} photos, {len(todo)} to compute against index {index_version()}", flush=True)
    for i, pid in enumerate(todo, 1):
        m = compute(pid)
        tmp = _path(pid).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(m, ensure_ascii=False))
        tmp.replace(_path(pid))
        v = [h for h in m["hits"] if h["verified"]]
        print(f"  {i}/{len(todo)} {pid}: {len(v)} verified, best {v[0]['inliers'] if v else 0} inliers", flush=True)
    return {"computed": len(todo)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "show"])
    ap.add_argument("photo_id", nargs="?")
    ap.add_argument("--priority", type=int)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    if a.cmd == "build":
        print(build(a.priority, a.limit))
    else:
        print(json.dumps(matches(a.photo_id), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
