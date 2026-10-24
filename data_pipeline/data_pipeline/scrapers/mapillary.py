"""Mapillary street-level photos in Kanton Schwyz (modern references, CC BY-SA 4.0).

    python -m data_pipeline.scrapers.mapillary count               # list + thin, nothing downloaded
    python -m data_pipeline.scrapers.mapillary fetch --limit 50    # test
    python -m data_pipeline.scrapers.mapillary fetch               # full run (resumable)

Why: Commons has only ~4,400 geotagged canton photos. Mapillary has thousands per town (Schwyz, Brunnen,
Arth, Lachen: 1,500 to 2,000 per km²), taken from the street, with GPS and compass heading. That is what
the challenge photos look like (street and village views), so MegaLoc gets close modern neighbours.

- Listing: graph.mapillary.com/images with a bbox grid over the canton box. A cell that hits the 2,000
  cap (or that Mapillary answers with HTTP 500, which it does for dense cells) is split into four, down
  to about 200 m. Responses are cached in data/raw/mapillary/api, so a rerun resumes. Only points inside the canton polygon are kept.
- Thinning: street sequences take a photo every few metres. Keep one photo per ~30 m cell and 90° heading
  bucket (the oldest, closest to the 2003 to 2013 challenge photos). Panoramas are skipped (equirectangular,
  MegaLoc expects a normal view).
- location = computed_geometry (Mapillary's SfM-corrected position), method `mapillary_gps`, about 10 m;
  camera = {lat, lon, azimuth}. Image: the 1024 px thumbnail.

Needs MAPILLARY_TOKEN (a client token "MLY|...") in the environment or the repo .env.
"""

import argparse
import hashlib
import io
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
from PIL import Image

from .. import geo
from ..http import PoliteClient
from ..jsonl import read_jsonl
from ..paths import IMAGES, RAW, RECORDS, REPO_ROOT, ensure

API = "https://graph.mapillary.com/images"
FIELDS = "id,captured_at,compass_angle,computed_compass_angle,geometry,computed_geometry,is_pano,creator,thumb_1024_url,sequence"
BBOX = [8.38, 46.88, 9.03, 47.22]  # W, S, E, N (same box as commons and smapshot)
CAP = 2000
START = 0.01  # about 0.75 x 1.1 km start cells (bigger dense cells get HTTP 500)
MIN_SPAN = 0.0025  # about 200 m: below this a capped cell is taken as is
CELL = (0.00027, 0.0004)  # lat, lon degrees: about 30 x 30 m thinning cell
MAX_EDGE = 1024

RECORDS_FILE = RECORDS / "mapillary.jsonl"
IMG_DIR = IMAGES / "mapillary"
LIST_FILE = RAW / "mapillary" / "images.json"
_local = threading.local()


def token() -> str:
    t = os.environ.get("MAPILLARY_TOKEN")
    if not t and (REPO_ROOT / ".env").exists():
        for line in (REPO_ROOT / ".env").read_text().splitlines():
            if line.startswith("MAPILLARY_TOKEN="):
                t = line.split("=", 1)[1].strip()
    if not t:
        raise SystemExit("MAPILLARY_TOKEN is not set")
    return t


def _cell(w: float, s: float, e: float, n: float) -> list[dict] | None:
    """Images in a bbox, or None when Mapillary gives up on it (HTTP 500 on dense cells: split and retry)."""
    url = f"{API}?fields={FIELDS}&bbox={w:.5f},{s:.5f},{e:.5f},{n:.5f}&limit={CAP}"
    cache = RAW / "mapillary" / "api" / f"{hashlib.sha1(url.encode()).hexdigest()}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    for attempt in range(3):
        try:
            r = httpx.get(url, headers={"Authorization": f"OAuth {token()}"}, timeout=90)
        except httpx.HTTPError:
            time.sleep(5)
            continue
        if r.status_code >= 500:
            return None
        r.raise_for_status()
        data = r.json().get("data", [])
        ensure(cache.parent)
        cache.write_text(json.dumps(data))
        return data
    return None


def _point(im: dict) -> tuple[float, float]:
    lon, lat = (im.get("computed_geometry") or im["geometry"])["coordinates"]
    return lat, lon


def list_images() -> list[dict]:
    """Thinned, in-canton, non-panorama images: [{id, lat, lon, heading, captured_at, creator, sequence, thumb}]."""
    if LIST_FILE.exists():
        return json.loads(LIST_FILE.read_text())
    w0, s0, e0, n0 = BBOX
    cells = [(w0 + i * START, s0 + j * START, min(e0, w0 + (i + 1) * START), min(n0, s0 + (j + 1) * START))
             for i in range(int((e0 - w0) / START) + 1) for j in range(int((n0 - s0) / START) + 1)]
    # skip start cells with no canton land at all (corners of the box)
    cells = [c for c in cells if any(geo.municipality_at(c[1] + (c[3] - c[1]) * y, c[0] + (c[2] - c[0]) * x)
                                     for x in (0.1, 0.5, 0.9) for y in (0.1, 0.5, 0.9))]
    found: dict[str, dict] = {}
    lock = threading.Lock()
    done = [0]

    def walk(c):
        todo = [c]
        while todo:
            w, s, e, n = todo.pop()
            hits = _cell(w, s, e, n)
            if hits is None and (e - w) <= MIN_SPAN:
                print(f"  gave up on cell {w:.4f},{s:.4f}", flush=True)
                continue
            if hits is None or (len(hits) >= CAP and (e - w) > MIN_SPAN):
                mx, my = (w + e) / 2, (s + n) / 2
                todo += [(w, s, mx, my), (mx, s, e, my), (w, my, mx, n), (mx, my, e, n)]
                continue
            with lock:
                for h in hits:
                    if not h.get("is_pano") and h.get("thumb_1024_url"):
                        found[h["id"]] = h
        with lock:
            done[0] += 1
            if done[0] % 25 == 0:
                print(f"  {done[0]}/{len(cells)} cells, {len(found)} images", flush=True)

    print(f"{len(cells)} start cells", flush=True)
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(walk, cells))
    best: dict[tuple, dict] = {}
    for h in found.values():
        lat, lon = _point(h)
        heading = h.get("computed_compass_angle") or h.get("compass_angle") or 0
        key = (round(lat / CELL[0]), round(lon / CELL[1]), int(heading % 360 // 90))
        if key not in best or h["captured_at"] < best[key]["captured_at"]:
            best[key] = h
    out = []
    for h in best.values():
        lat, lon = _point(h)
        if not geo.municipality_at(lat, lon):
            continue
        out.append({"id": h["id"], "lat": round(lat, 6), "lon": round(lon, 6),
                    "heading": round(h.get("computed_compass_angle") or h.get("compass_angle") or 0, 1),
                    "captured_at": h["captured_at"], "creator": (h.get("creator") or {}).get("username"),
                    "sequence": h.get("sequence"), "thumb": h["thumb_1024_url"]})
    out.sort(key=lambda r: r["id"])
    ensure(LIST_FILE.parent)
    LIST_FILE.write_text(json.dumps(out))
    print(f"{len(found)} non-panorama images listed, {len(best)} after thinning, {len(out)} inside the canton", flush=True)
    return out


def record(m: dict) -> dict:
    muni = geo.municipality_at(m["lat"], m["lon"])
    when = datetime.fromtimestamp(m["captured_at"] / 1000, timezone.utc)
    who = m.get("creator") or "unknown"
    return {
        "id": f"mapillary:{m['id']}", "source": "mapillary", "source_id": m["id"],
        "source_url": f"https://www.mapillary.com/app/?pKey={m['id']}", "signature": None, "collection": "Mapillary",
        "kind": "ground", "title": f"Mapillary {muni['name'] if muni else ''} {when:%Y-%m-%d}".replace("  ", " "),
        "date": {"raw": when.strftime("%Y-%m-%d"), "year_from": when.year, "year_to": when.year, "approximate": False},
        "places": [], "municipality": muni["name"] if muni else None,
        "location": {"lat": m["lat"], "lon": m["lon"], "method": "mapillary_gps", "precision_m": 10},
        "camera": {"lat": m["lat"], "lon": m["lon"], "altitude_m": None, "azimuth": m["heading"], "tilt": None,
                   "roll": None, "focal": None},
        "photographer": who,
        "license": {"code": "CC-BY-SA-4.0", "credit": f"{who}, Mapillary, CC BY-SA 4.0",
                    "url": "https://creativecommons.org/licenses/by-sa/4.0/"},
        "image": None, "parent_id": None, "crop_bbox": None, "split": "reference",
        "raw": {"sequence": m.get("sequence"), "captured_at": m["captured_at"]},
    }


def _image(m: dict) -> dict:
    if not hasattr(_local, "t"):
        _local.t = PoliteClient(min_interval=0.05, cache_dir=None)
    img = Image.open(io.BytesIO(_local.t.get(m["thumb"], cache=False))).convert("RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    path = IMG_DIR / f"{m['id']}.jpg"
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    path.write_bytes(buf.getvalue())
    return {"path": f"images/mapillary/{path.name}", "width": img.width, "height": img.height,
            "sha1": hashlib.sha1(buf.getvalue()).hexdigest()}


def fetch(limit: int | None = None, workers: int = 8) -> dict:
    ensure(IMG_DIR, RECORDS)
    items = list_images()
    done = {r["source_id"] for r in read_jsonl(RECORDS_FILE)}
    todo = [m for m in items if m["id"] not in done][:limit]
    print(f"{len(items)} images, {len(done)} done, {len(todo)} to fetch", flush=True)
    kept, failed, t0 = 0, 0, time.monotonic()
    lock = threading.Lock()
    with RECORDS_FILE.open("a", encoding="utf-8") as out, ThreadPoolExecutor(workers) as ex:
        def one(m: dict) -> None:
            nonlocal kept, failed
            rec = record(m)
            try:
                rec["image"] = _image(m)
            except Exception as e:  # an expired or broken thumbnail should not stop the run
                with lock:
                    failed += 1
                print(f"  image failed {rec['id']}: {e}", flush=True)
                return
            with lock:
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                kept += 1
                if kept % 500 == 0:
                    print(f"  {kept}/{len(todo)} ({kept / (time.monotonic() - t0):.1f}/s, {failed} failed)", flush=True)

        list(ex.map(one, todo))
    return {"kept": kept, "failed": failed, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["count", "fetch"])
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    if a.cmd == "count":
        print(len(list_images()), "images to fetch")
    else:
        print(fetch(a.limit))


if __name__ == "__main__":
    main()
