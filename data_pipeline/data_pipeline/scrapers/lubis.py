"""swisstopo LUBIS terrestrial photos (ch.swisstopo.lubis-terrestrische_aufnahmen): exact-dated
ground photos with a surveyed camera station, used as reference and eval ground truth.

    python -m data_pipeline.scrapers.lubis fetch --limit 20     # test
    python -m data_pipeline.scrapers.lubis fetch                # full run

API (geo.admin.ch REST, checked 2026-10-21):
- /MapServer/identify with an LV95 envelope (the Schwyz box). It matches the photo's viewshed
  polygon, not the station, and returns at most 50 per call. `offset` pages, but its order is
  not stable on big result sets, so the box is split in 4 whenever a tile is full, and only
  tiles below 4 km are paged. We keep features whose camera station (attributes x/y, the
  CSV E/N, "Zentrumskoordinate") lies inside the box; the identify point is the view target.
- featureattachments/<layer>/<id>/<id>.csv: per-photo metadata incl. CAMERA, FOCAL_LENGTH,
  OMEGA, KAPPA, E, N, Z. KAPPA matches the bearing from the station to the view centre, so it is
  stored as the azimuth (degrees from north, clockwise); OMEGA is stored as tilt.
- featureattachments/<layer>/<id>/<id>.tif: cloud-optimized GeoTIFF (about 7000 px, JPEG tiles,
  with overviews). The .jpg attachment is only a 150 px thumbnail, so we read the smallest
  overview with a long edge >= 1024 via HTTP range requests (about 0.4 MB instead of 8 MB).

Terms: free use with attribution "© swisstopo". geo.admin REST allows about 40 requests/min,
so API calls wait 1.6 s; attachment downloads (S3) wait 1 s.
Resumable: skips ids already in data/records/lubis.jsonl.
"""

import argparse
import hashlib
import io
import json
import struct
import time
from datetime import datetime, timezone

from PIL import Image

from .. import geo
from ..http import PoliteClient
from ..paths import IMAGES, RAW, RECORDS, ensure

LAYER = "ch.swisstopo.lubis-terrestrische_aufnahmen"
API = "https://api3.geo.admin.ch/rest/services/api/MapServer"
ATTACH = f"https://api3.geo.admin.ch/featureattachments/{LAYER}"
BBOX = (2670000, 1185000, 2735000, 1240000)  # LV95 xmin, ymin, xmax, ymax
PAGE = 50
MAX_EDGE = 1024

RECORDS_FILE = RECORDS / "lubis.jsonl"
IMG_DIR = IMAGES / "lubis"

api = PoliteClient(min_interval=1.6, cache_dir=RAW / "lubis" / "http")
files = PoliteClient(min_interval=1.0, cache_dir=RAW / "lubis" / "http")


def lv95_to_wgs84(e: float, n: float) -> tuple[float, float]:
    """swisstopo approximate formula (about 1 m accurate). Returns (lat, lon)."""
    y, x = (e - 2600000) / 1e6, (n - 1200000) / 1e6
    lon = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y**3
    lat = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x**3
    return round(lat * 100 / 36, 6), round(lon * 100 / 36, 6)


MIN_TILE = 4000  # m; below this, page with offset instead of splitting further


def _identify(box: tuple, offset: int = 0) -> list[dict]:
    params = {"geometryType": "esriGeometryEnvelope", "geometry": ",".join(map(str, box)), "sr": 2056,
              "layers": f"all:{LAYER}", "tolerance": 0, "returnGeometry": "true",
              "limit": PAGE, "offset": offset}
    return json.loads(api.get(f"{API}/identify", params=params, suffix=".json"))["results"]


def _tile(box: tuple, out: dict) -> None:
    """Split a full tile in 4; small tiles page with offset (the offset order is not stable on
    big result sets, so paging the whole box alone misses features)."""
    res = _identify(box)
    out.update((r["id"], r) for r in res)
    if len(res) < PAGE:
        return
    x0, y0, x1, y1 = box
    if x1 - x0 > MIN_TILE:
        mx, my = (x0 + x1) // 2, (y0 + y1) // 2
        for sub in ((x0, y0, mx, my), (mx, y0, x1, my), (x0, my, mx, y1), (mx, my, x1, y1)):
            _tile(sub, out)
        return
    offset = PAGE
    while True:
        res = _identify(box, offset)
        out.update((r["id"], r) for r in res)
        if len(res) < PAGE:
            return
        offset += PAGE


def list_features() -> list[dict]:
    """All features whose viewshed touches the box, deduplicated, station inside the box."""
    found: dict = {}
    _tile(BBOX, found)
    rows = list(found.values())
    x0, y0, x1, y1 = BBOX
    inside = [r for r in rows if x0 <= (r["attributes"].get("x") or 0) <= x1 and y0 <= (r["attributes"].get("y") or 0) <= y1]
    print(f"  {len(rows)} features touch the box, {len(inside)} with the station inside", flush=True)
    return inside


def metadata_csv(fid: str) -> dict:
    try:
        text = files.get(f"{ATTACH}/{fid}/{fid}.csv", suffix=".csv").decode("utf-8-sig", errors="replace")
    except FileNotFoundError:
        return {}
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return {}
    meta = dict(zip(lines[0].split(";"), lines[1].split(";")))
    meta.pop("SHAPE_LV95", None)  # a Python repr from their export, useless
    return {k: (None if v in ("N/A", "") else v) for k, v in meta.items()}


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --- cloud-optimized GeoTIFF overview via range requests ---

def _range(url: str, start: int, length: int) -> bytes:
    for attempt in range(5):
        files._wait()
        files.requests += 1
        try:
            r = files.client.get(url, headers={"Range": f"bytes={start}-{start + length - 1}"})
        except Exception as e:  # network error: back off and retry
            err = str(e)
        else:
            if r.status_code == 206:
                return r.content
            if r.status_code == 200:  # server ignored Range
                return r.content[start:start + length]
            if r.status_code in (404, 410):
                raise FileNotFoundError(f"{r.status_code} {url}")
            err = f"HTTP {r.status_code}"
        backoff = 10 * 2**attempt
        print(f"  retry {attempt + 1}/5 in {backoff}s ({err}) {url}", flush=True)
        time.sleep(backoff)
    raise RuntimeError(f"giving up on {url}")


class _Reader:
    """Byte access to a remote file: the head is fetched once, anything else on demand."""

    def __init__(self, url: str, head: int = 65536):
        self.url = url
        self.head = _range(url, 0, head)

    def read(self, off: int, n: int) -> bytes:
        if off + n <= len(self.head):
            return self.head[off:off + n]
        return _range(self.url, off, n)


_TYPES = {1: ("B", 1), 2: ("B", 1), 3: ("H", 2), 4: ("I", 4), 7: ("B", 1), 16: ("Q", 8)}


def _ifds(rd: _Reader) -> list[dict]:
    if rd.head[:4] != b"II*\x00":
        raise ValueError("not a little-endian classic TIFF")
    out, off = [], struct.unpack("<I", rd.head[4:8])[0]
    while off:
        n = struct.unpack("<H", rd.read(off, 2))[0]
        ents = rd.read(off + 2, n * 12 + 4)
        tags = {}
        for i in range(n):
            tag, typ, cnt, val = struct.unpack("<HHI4s", ents[i * 12:i * 12 + 12])
            if typ not in _TYPES:
                continue
            fmt, size = _TYPES[typ]
            raw = val if cnt * size <= 4 else rd.read(struct.unpack("<I", val)[0], cnt * size)
            vals = struct.unpack(f"<{cnt}{fmt}", raw[:cnt * size])
            tags[tag] = raw[:cnt * size] if typ == 7 else (vals[0] if cnt == 1 and tag not in (324, 325) else vals)
        out.append(tags)
        off = struct.unpack("<I", ents[n * 12:n * 12 + 4])[0]
    return out


def cog_overview(url: str) -> Image.Image:
    rd = _Reader(url)
    levels = [t for t in _ifds(rd) if 256 in t and 324 in t]
    big = [t for t in levels if max(t[256], t[257]) >= MAX_EDGE]
    t = min(big, key=lambda t: t[256]) if big else max(levels, key=lambda t: t[256])
    if t.get(259) != 7:
        raise ValueError(f"unsupported TIFF compression {t.get(259)}")
    w, h, tw, th = t[256], t[257], t[322], t[323]
    offs, counts = t[324], t[325]
    tables = t.get(347, b"")
    lo, hi = min(offs), max(o + c for o, c in zip(offs, counts))
    blob = rd.read(lo, hi - lo)  # overview tiles are contiguous in a COG: one request
    mode = "L" if t.get(277, 1) == 1 else "RGB"
    canvas = Image.new(mode, (w, h))
    across = -(-w // tw)
    for i, (o, c) in enumerate(zip(offs, counts)):
        if not c:
            continue
        data = blob[o - lo:o - lo + c]
        if tables:  # abbreviated JPEG: splice the shared tables in after SOI
            data = tables[:-2] + data[2:]
        tile = Image.open(io.BytesIO(data))
        if t.get(262) == 6:  # YCbCr in the TIFF, libjpeg may need the hint
            tile.draft("RGB", tile.size)
        canvas.paste(tile.convert(mode), ((i % across) * tw, (i // across) * th))
    return canvas


def _save(im: Image.Image, path) -> dict:
    im = im.convert("RGB")
    im.thumbnail((MAX_EDGE, MAX_EDGE))
    ensure(path.parent)
    im.save(path, "JPEG", quality=90)
    return {"path": str(path.relative_to(IMAGES.parent)), "width": im.width, "height": im.height,
            "sha1": hashlib.sha1(path.read_bytes()).hexdigest()}


def fetch_image(fid: str, inv: str) -> dict | None:
    try:
        im = cog_overview(f"{ATTACH}/{fid}/{fid}.tif")
    except FileNotFoundError:
        return None
    except Exception as e:  # odd TIFF layout: fall back to the 150 px thumbnail
        print(f"  {fid}: overview failed ({e}), using thumbnail", flush=True)
        try:
            im = Image.open(io.BytesIO(files.get(f"{ATTACH}/{fid}/{fid}.jpg", suffix=".jpg")))
        except FileNotFoundError:
            return None
    return _save(im, IMG_DIR / f"{inv}.jpg")


def build_record(row: dict, meta: dict, image: dict | None) -> dict:
    a = row["attributes"]
    fid, inv = row["id"], str(a["inventarnummer"])
    lat, lon = lv95_to_wgs84(a["x"], a["y"])
    muni = geo.municipality_at(lat, lon)
    d = a.get("flugdatum") or ""
    year = int(d[:4]) if d[:4].isdigit() else a.get("bgdi_flugjahr")
    iso = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else None
    return {
        "id": f"lubis:{inv}",
        "source": "lubis",
        "source_id": inv,
        "source_url": f"https://map.geo.admin.ch?{LAYER}={fid}&lang=de",
        "signature": fid,
        "collection": meta.get("SERIES") or "Terrestrische Aufnahmen swisstopo",
        "kind": "ground",
        "title": f"{a.get('ort')} (Station {a.get('station')})" if a.get("station") else a.get("ort"),
        "date": {"raw": iso or d, "year_from": year, "year_to": year, "approximate": False},
        "places": [p.strip() for p in (meta.get("PLACE") or a.get("ort") or "").split("|") if p.strip()],
        "municipality": muni["name"] if muni else None,
        "location": {"lat": lat, "lon": lon, "method": "lubis_station", "precision_m": 50},
        "camera": {"lat": lat, "lon": lon, "altitude_m": _num(meta.get("Z")), "azimuth": _num(meta.get("KAPPA")),
                   "tilt": _num(meta.get("OMEGA")), "roll": _num(meta.get("PHI")), "focal": _num(meta.get("FOCAL_LENGTH"))},
        "photographer": None,
        "license": {"code": "swisstopo-OGD", "credit": "© swisstopo, LUBIS",
                    "url": "https://www.swisstopo.admin.ch/de/nutzungsbedingungen-kostenlose-geodaten-und-geodienste"},
        "image": image,
        "parent_id": None,
        "crop_bbox": None,
        "split": "reference",
        "raw": {
            **a,
            "feature_id": fid,
            "view_point_lv95": [row.get("geometry", {}).get("x"), row.get("geometry", {}).get("y")],
            "csv": meta,
            "in_canton": muni is not None,
            "municipality_method": "camera_point",
        },
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def fetch(limit: int | None) -> None:
    ensure(RECORDS)
    done = set()
    if RECORDS_FILE.exists():
        done = {json.loads(l)["source_id"] for l in RECORDS_FILE.read_text().splitlines() if l.strip()}
    rows = list_features()
    todo = [r for r in rows if str(r["attributes"]["inventarnummer"]) not in done]
    print(f"{len(rows)} listed, {len(done)} done, {len(todo)} to fetch", flush=True)
    kept = 0
    with RECORDS_FILE.open("a") as out:
        for row in todo:
            fid, inv = row["id"], str(row["attributes"]["inventarnummer"])
            rec = build_record(row, metadata_csv(fid), fetch_image(fid, inv))
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            kept += 1
            if kept % 10 == 0:
                print(f"  {kept} kept; last {rec['id']} {rec['date']['raw']} -> {rec['municipality']}", flush=True)
            if limit and kept >= limit:
                break
    print(f"done: {kept} kept this run", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch"])
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    fetch(a.limit)


if __name__ == "__main__":
    main()
