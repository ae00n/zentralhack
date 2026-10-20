"""Smapshot (HEIG-VD) collector: georeferenced historical photos with full camera pose.

    python -m data_pipeline.scrapers.smapshot fetch --limit 50     # test
    python -m data_pipeline.scrapers.smapshot fetch                # full run (run epics.py full first)

API docs: https://smapshot.heig-vd.ch/api/v1/docs/
- /images with bbox[] (the Schwyz box), state[]=validated, date_shot_max=1969-12-31.
  (wkt_roi returns HTTP 500 on the server as of 2026-10-20, so we filter by bbox and tag the
  municipality locally from the camera point; raw.in_canton says whether it is inside Schwyz.)
- /images/{id}/attributes per image for pose, license, owner, collection, photographers.

Images:
- ETH Library (owner 4): original_id is the E-Pics file name, so we take E-Pics' "Screen"
  derivation (shared file data/images/epics/<file>.jpg, nothing is downloaded twice).
- other owners: Smapshot's own thumbnail (about 200 px). With --dzi-px N the image is
  stitched from Deep Zoom tiles at the level whose long edge is <= N (many tile requests).

1 request per second, resumable (skips ids already in data/records/smapshot.jsonl).
"""

import argparse
import hashlib
import io
import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from PIL import Image

from .. import geo
from ..http import PoliteClient
from ..paths import IMAGES, RAW, RECORDS, ensure
from . import epics

API = "https://smapshot.heig-vd.ch/api/v1"
BBOX = [8.38, 46.88, 9.03, 47.22]  # W, S, E, N
DATE_MAX = "1969-12-31"
PAGE = 500
MAX_EDGE = 1024
ETH_OWNER = 4

RECORDS_FILE = RECORDS / "smapshot.jsonl"
IMG_DIR = IMAGES / "smapshot"

client = PoliteClient(min_interval=1.0, cache_dir=RAW / "smapshot" / "http")


def license_code(text: str | None, owner_slug: str | None) -> str | None:
    """Map Smapshot's free-text license line to a code; None = not allowed for our use."""
    t = (text or "").lower()
    if "public domain" in t or "no known restrictions" in t:
        return "PDM"
    if re.search(r"cc[ -]by[ -]sa", t):
        return "CC-BY-SA"
    if re.search(r"cc[ -]by\b(?![ -]n)", t):
        return "CC-BY"
    if owner_slug == "swisstopo" or "swisstopo" in t:
        return "swisstopo-OGD"  # free geodata, attribution "© swisstopo" required
    return None


def list_images() -> list[dict]:
    rows, offset = [], 0
    while True:
        params = {"bbox[]": BBOX, "state[]": "validated", "date_shot_max": DATE_MAX,
                  "limit": PAGE, "offset": offset}
        data = json.loads(client.get(f"{API}/images", params=params, suffix=".json"))
        rows += data["rows"]
        print(f"  listed {len(rows)}/{data['count']}", flush=True)
        offset += PAGE
        if offset >= data["count"] or not data["rows"]:
            return rows


def _save(im: Image.Image, path) -> dict:
    im = im.convert("RGB")
    im.thumbnail((MAX_EDGE, MAX_EDGE))
    ensure(path.parent)
    im.save(path, "JPEG", quality=90)
    return {"path": str(path.relative_to(IMAGES.parent)), "width": im.width, "height": im.height,
            "sha1": hashlib.sha1(path.read_bytes()).hexdigest()}


def dzi_image(dzi_url: str, max_px: int) -> Image.Image:
    xml = ET.fromstring(client.get(dzi_url, suffix=".xml"))
    ns = {"d": "http://schemas.microsoft.com/deepzoom/2008"}
    size = xml.find("d:Size", ns)
    w, h = int(size.get("Width")), int(size.get("Height"))
    tile, overlap = int(xml.get("TileSize")), int(xml.get("Overlap"))
    max_level = math.ceil(math.log2(max(w, h)))
    level = max_level - max(0, math.ceil(math.log2(max(w, h) / max_px)))
    scale = 2 ** (max_level - level)
    lw, lh = math.ceil(w / scale), math.ceil(h / scale)
    canvas = Image.new("RGB", (lw, lh))
    base = dzi_url[: -len(".dzi")] + f"_files/{level}"
    for ty in range(math.ceil(lh / tile)):
        for tx in range(math.ceil(lw / tile)):
            t = Image.open(io.BytesIO(client.get(f"{base}/{tx}_{ty}.jpg", suffix=".jpg")))
            canvas.paste(t, (tx * tile - (overlap if tx else 0), ty * tile - (overlap if ty else 0)))
    return canvas


def fetch_image(row: dict, attrs: dict, dzi_px: int) -> dict | None:
    if attrs["owner"]["id"] == ETH_OWNER and attrs.get("original_id"):
        stem = attrs["original_id"]
        path = IMAGES / "epics" / f"{stem}.jpg"
        if path.exists():
            with Image.open(path) as im:
                return {"path": str(path.relative_to(IMAGES.parent)), "width": im.width, "height": im.height,
                        "sha1": hashlib.sha1(path.read_bytes()).hexdigest()}
        item = epics.find_by_file_name(stem)
        if item:
            img = epics.screen_image(item["identifier"], stem)
            if img:
                return img
    path = IMG_DIR / f"{row['id']}.jpg"
    if dzi_px and attrs.get("media", {}).get("tiles"):
        return _save(dzi_image(attrs["media"]["tiles"]["url"], dzi_px), path)
    url = (attrs.get("media") or row.get("media") or {}).get("image_url")
    if not url:
        return None
    return _save(Image.open(io.BytesIO(client.get(url, suffix=".jpg"))), path)


def build_record(row: dict, a: dict, lic: str, image: dict | None) -> dict:
    pose = a.get("pose") or {}
    lat, lon = pose.get("latitude", row.get("latitude")), pose.get("longitude", row.get("longitude"))
    muni = geo.municipality_at(lat, lon)
    y0 = int(a["date_shot_min"][:4]) if a.get("date_shot_min") else None
    y1 = int(a["date_shot_max"][:4]) if a.get("date_shot_max") else None
    photographers = ", ".join(p["name"] for p in a.get("photographers") or [] if p.get("name")) or None
    view = a.get("view_type")
    return {
        "id": f"smapshot:{row['id']}",
        "source": "smapshot",
        "source_id": str(row["id"]),
        "source_url": f"{API}/images/{row['id']}/attributes",
        "signature": a.get("original_id"),
        "collection": (a.get("collection") or {}).get("name"),
        "kind": "ground" if view == "terrestrial" else ("aerial" if view else "unknown"),
        "title": a.get("title"),
        "date": {"raw": f"{a.get('date_shot_min')}..{a.get('date_shot_max')}", "year_from": y0, "year_to": y1,
                 "approximate": y0 != y1},
        "places": [],
        "municipality": muni["name"] if muni else None,
        "location": {"lat": lat, "lon": lon, "method": "smapshot_pose", "precision_m": 50} if lat is not None else None,
        "camera": {"lat": lat, "lon": lon, "altitude_m": pose.get("altitude"), "azimuth": pose.get("azimuth"),
                   "tilt": pose.get("tilt"), "roll": pose.get("roll"), "focal": pose.get("focal")} if pose else None,
        "photographer": photographers,
        "license": {"code": lic, "credit": a.get("license"), "url": a.get("link") or a.get("download_link")},
        "image": image,
        "parent_id": None,
        "crop_bbox": None,
        "split": "reference",
        "raw": {
            "original_id": a.get("original_id"),
            "owner": (a.get("owner") or {}).get("name"),
            "owner_id": (a.get("owner") or {}).get("id"),
            "view_type": view,
            "caption": a.get("caption"),
            "doi": a.get("link"),
            "in_canton": muni is not None,
            "municipality_method": "camera_point",
        },
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def fetch(limit: int | None, dzi_px: int, spread: bool = False) -> None:
    ensure(RECORDS)
    done = set()
    if RECORDS_FILE.exists():
        done = {json.loads(l)["source_id"] for l in RECORDS_FILE.read_text().splitlines() if l.strip()}
    skip_file = RAW / "smapshot" / "skipped_license.jsonl"
    ensure(skip_file.parent)
    skipped = {json.loads(l)["id"] for l in skip_file.read_text().splitlines()} if skip_file.exists() else set()
    rows = list_images()
    todo = [r for r in rows if str(r["id"]) not in done and str(r["id"]) not in skipped]
    if limit and spread:
        todo = todo[:: max(1, len(todo) // limit)]
    print(f"{len(rows)} listed, {len(done)} done, {len(skipped)} skipped earlier, {len(todo)} to fetch", flush=True)
    kept = 0
    with RECORDS_FILE.open("a") as out, skip_file.open("a") as skip:
        for row in todo:
            a = json.loads(client.get(f"{API}/images/{row['id']}/attributes", suffix=".json"))
            lic = license_code(a.get("license"), (a.get("owner") or {}).get("slug"))
            if not lic:
                skip.write(json.dumps({"id": str(row["id"]), "license": a.get("license")}, ensure_ascii=False) + "\n")
                continue
            rec = build_record(row, a, lic, fetch_image(row, a, dzi_px))
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            kept += 1
            if kept % 10 == 0:
                print(f"  {kept} kept; last {rec['id']} {rec['date']['raw']} {rec['license']['code']} -> {rec['municipality']}", flush=True)
            if limit and kept >= limit:
                break
    print(f"done: {kept} kept this run", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dzi-px", type=int, default=0, help="non-ETH images: stitch Deep Zoom tiles up to this long edge")
    ap.add_argument("--spread", action="store_true", help="with --limit: sample evenly across the list")
    a = ap.parse_args()
    fetch(a.limit, a.dzi_px, a.spread)


if __name__ == "__main__":
    main()
