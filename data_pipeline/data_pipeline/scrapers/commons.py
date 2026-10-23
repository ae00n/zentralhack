"""Wikimedia Commons: geotagged, openly licensed photos taken in Kanton Schwyz (modern references).

    python -m data_pipeline.scrapers.commons count                 # how many files, nothing downloaded
    python -m data_pipeline.scrapers.commons fetch --limit 50      # test
    python -m data_pipeline.scrapers.commons fetch                 # full run (resumable)

Why: the challenge photos are from 2003 to 2013, but almost all other references are older than 1990.
Commons has thousands of geotagged canton photos from that era (many from Panoramio, 2005 to 2014),
often with the building and address in the file name ("Strehlgasse 4 in Schwyz SZ.jpg") and in the
categories ("Pfarrkirche St. Martin (Schwyz)").

- Files: list=geosearch with gsbbox over the canton box. A box that hits the 500-result cap is split
  into four, down to about 250 m. Only files whose point lies inside the canton polygon are kept.
- Metadata: prop=imageinfo (extmetadata, 1024 px thumbnail URL, sha1) + prop=coordinates, 50 per call.
- location = the Commons file coordinate (usually the camera position), method `commons_geo`.
- Only free licences (CC0, PD, CC-BY, CC-BY-SA); title, categories, date and author kept for credit.
- Images: the Commons thumbnail at 1024 px.

Commons wants a User-Agent with a contact URL; API calls 1/s, thumbnails with 4 workers (each about 1/s,
the thumbnail renderer is the bottleneck).
"""

import argparse
import threading
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import re
import time
from datetime import datetime, timezone

from PIL import Image

from .. import geo
from ..http import PoliteClient
from ..jsonl import read_jsonl
from ..paths import IMAGES, RAW, RECORDS, ensure
from .nb_commons import UA, api, strip

BBOX = [8.38, 46.88, 9.03, 47.22]  # W, S, E, N (same box as smapshot)
CAP = 500
MIN_SPAN = 0.003  # about 250 m: below this a capped box is taken as is
MAX_EDGE = 1024
FREE = re.compile(r"^(cc0|public domain|pd\b|cc[ -]by(-sa)?[ -]\d)", re.I)

RECORDS_FILE = RECORDS / "commons.jsonl"
IMG_DIR = IMAGES / "commons"
LIST_FILE = RAW / "commons" / "files.json"
_local = threading.local()


def _thumbs() -> PoliteClient:
    if not hasattr(_local, "c"):
        _local.c = PoliteClient(min_interval=0.25, cache_dir=None, headers={"User-Agent": UA})
    return _local.c


def _geosearch(w: float, s: float, e: float, n: float) -> list[dict]:
    for attempt in range(8):
        try:
            d = api({"action": "query", "list": "geosearch", "gsbbox": f"{n}|{w}|{s}|{e}", "gslimit": CAP,
                     "gsnamespace": 6})
            return d.get("query", {}).get("geosearch", [])
        except RuntimeError as e:
            if "too-busy" not in str(e):
                raise
            print(f"  search busy, waiting {15 * (attempt + 1)}s", flush=True)
            time.sleep(15 * (attempt + 1))
    raise RuntimeError("Commons geosearch stayed busy")


def list_files() -> list[dict]:
    """[{pageid, title, lat, lon}] for every geotagged file in the canton box (deduped)."""
    if LIST_FILE.exists():
        return json.loads(LIST_FILE.read_text())
    found: dict[int, dict] = {}
    todo = [tuple(BBOX)]
    # gsbbox spans at most 10 km per side: start from a grid of about 0.1 degree cells
    w0, s0, e0, n0 = BBOX
    todo = [(w0 + i * 0.1, s0 + j * 0.08, min(e0, w0 + (i + 1) * 0.1), min(n0, s0 + (j + 1) * 0.08))
            for i in range(int((e0 - w0) / 0.1) + 1) for j in range(int((n0 - s0) / 0.08) + 1)]
    while todo:
        w, s, e, n = todo.pop()
        if w >= e or s >= n:
            continue
        hits = _geosearch(w, s, e, n)
        if len(hits) >= CAP and (e - w) > MIN_SPAN:
            mx, my = (w + e) / 2, (s + n) / 2
            todo += [(w, s, mx, my), (mx, s, e, my), (w, my, mx, n), (mx, my, e, n)]
            continue
        for h in hits:
            found[h["pageid"]] = {"pageid": h["pageid"], "title": h["title"], "lat": h["lat"], "lon": h["lon"]}
    files = [f for f in found.values() if geo.municipality_at(f["lat"], f["lon"])]
    files.sort(key=lambda f: f["pageid"])
    ensure(LIST_FILE.parent)
    LIST_FILE.write_text(json.dumps(files))
    print(f"{len(found)} files in the box, {len(files)} inside the canton", flush=True)
    return files


def _meta(pageids: list[int]) -> dict[int, dict]:
    d = api({"action": "query", "pageids": "|".join(map(str, pageids)), "prop": "imageinfo|categories",
             "iiprop": "url|extmetadata|size|sha1|mime", "iiurlwidth": MAX_EDGE, "cllimit": "max",
             "clshow": "!hidden"})
    return {p["pageid"]: p for p in d.get("query", {}).get("pages", []) if not p.get("missing")}


def _date(em: dict) -> dict:
    raw = strip((em.get("DateTimeOriginal") or {}).get("value"))
    m = re.search(r"\b(1[89]\d\d|20\d\d)\b", raw or "")
    y = int(m.group(1)) if m else None
    return {"raw": raw or "keine Angabe", "year_from": y, "year_to": y, "approximate": False}


def _title(t: str) -> str:
    t = re.sub(r"^File:", "", t)
    return re.sub(r"\.(jpe?g|png|tiff?)$", "", t, flags=re.I).replace("_", " ")


def record(f: dict, page: dict) -> dict | None:
    ii = (page.get("imageinfo") or [{}])[0]
    if ii.get("mime") != "image/jpeg" or min(ii.get("width", 0), ii.get("height", 0)) < 300:
        return None
    em = ii.get("extmetadata") or {}
    lic = strip((em.get("LicenseShortName") or {}).get("value")) or ""
    if not FREE.match(lic):
        return None
    cats = [c["title"].removeprefix("Category:") for c in page.get("categories", [])]
    muni = geo.municipality_at(f["lat"], f["lon"])
    return {
        "id": f"commons:{f['pageid']}", "source": "commons", "source_id": str(f["pageid"]),
        "source_url": ii.get("descriptionurl"), "signature": None, "collection": "Wikimedia Commons",
        "kind": "ground", "title": _title(f["title"]), "date": _date(em),
        "places": cats, "municipality": muni["name"] if muni else None,
        "location": {"lat": f["lat"], "lon": f["lon"], "method": "commons_geo", "precision_m": 100},
        "camera": None, "photographer": strip((em.get("Artist") or {}).get("value")),
        "license": {"code": lic, "credit": f"{strip((em.get('Artist') or {}).get('value')) or 'unknown'}, "
                                          f"Wikimedia Commons, {lic}",
                    "url": strip((em.get("LicenseUrl") or {}).get("value"))},
        "image": None, "parent_id": None, "crop_bbox": None, "split": "reference",
        "raw": {"commons_title": f["title"], "categories": cats, "thumb_url": ii.get("thumburl"),
                "description": strip((em.get("ImageDescription") or {}).get("value"))[:500] or None,
                "original_size": [ii.get("width"), ii.get("height")]},
    }


def _image(rec: dict) -> dict | None:
    data = _thumbs().get(rec["raw"]["thumb_url"], cache=False)
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    path = IMG_DIR / f"{rec['source_id']}.jpg"
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    path.write_bytes(buf.getvalue())
    return {"path": f"images/commons/{path.name}", "width": img.width, "height": img.height,
            "sha1": hashlib.sha1(buf.getvalue()).hexdigest()}


def fetch(limit: int | None = None, workers: int = 4) -> dict:
    ensure(IMG_DIR, RECORDS)
    files = list_files()
    done = {r["source_id"] for r in read_jsonl(RECORDS_FILE)}
    todo = [f for f in files if str(f["pageid"]) not in done][:limit]
    print(f"{len(files)} files, {len(done)} done, {len(todo)} to fetch", flush=True)
    kept = skipped = 0
    lock = threading.Lock()
    with RECORDS_FILE.open("a", encoding="utf-8") as out, ThreadPoolExecutor(workers) as ex:
        def one(rec: dict) -> None:
            nonlocal kept
            try:
                rec["image"] = _image(rec)
            except Exception as e:  # a broken thumbnail should not stop the run
                print(f"  image failed {rec['id']}: {e}", flush=True)
                return
            with lock:
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                kept += 1

        for i in range(0, len(todo), 50):
            batch = todo[i:i + 50]
            meta = _meta([f["pageid"] for f in batch])
            recs = [record(f, meta.get(f["pageid"], {})) for f in batch]
            skipped += sum(r is None for r in recs)
            list(ex.map(one, [r for r in recs if r]))
            print(f"  {i + len(batch)}/{len(todo)} ({kept} kept, {skipped} skipped: licence or not a photo)",
                  flush=True)
    return {"kept": kept, "skipped": skipped, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["count", "fetch"])
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    if a.cmd == "count":
        files = list_files()
        print(len(files), "files inside the canton")
    else:
        print(fetch(a.limit))


if __name__ == "__main__":
    main()
