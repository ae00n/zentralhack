"""The challenge photos handed out at the event (SG.CIV.17, about 600 uncatalogued 21st-century photos).

    python -m data_pipeline.scrapers.challenge          # reads data/challenge/, writes records/challenge.jsonl

Input: the unpacked SharePoint zip in data/challenge/ ("Bilder Prio 1/" = the 50 photos Ralph Ruch
picked first, "Nice to have/" = the rest). Each file is named by its signature, e.g. SG.CIV.17.3.jpg.

- id `challenge:SG.CIV.17.3`, source `challenge`, split `challenge`, raw.priority 1 or 2.
- No catalogue entry exists yet, so title, places and municipality stay null (that is the task).
- date from EXIF DateTimeOriginal (exact day, every photo has one), raw.exif keeps camera data.
- GPS only where EXIF has real coordinates (1 of 603); empty GPS blocks are ignored.
- raw.session: other challenge ids shot with the same camera within SESSION_GAP_MIN minutes.
  Photos from one session usually show the same place, so one answer can support the others.
- Image: EXIF orientation applied, downscaled to 1024 px long edge (images/challenge/<signature>.jpg).
  These images are not openly licensed: never publish them or put them in git.
"""

import hashlib
import re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from .. import geo
from ..jsonl import write_jsonl
from ..paths import DATA_DIR, IMAGES, RECORDS, ensure

SRC_DIR = DATA_DIR / "challenge"
FOLDERS = {"Bilder Prio 1": 1, "Nice to have": 2}
IMG_DIR = IMAGES / "challenge"
RECORDS_FILE = RECORDS / "challenge.jsonl"
MAX_EDGE = 1024
SESSION_GAP_MIN = 30
SIG_RE = re.compile(r"^(SG\.CIV\.\d+\.\d+)")


def _dms(v, ref) -> float:
    d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
    return -d if ref in ("S", "W") else d


def _exif(im: Image.Image) -> dict:
    ex = im.getexif()
    sub = ex.get_ifd(0x8769)
    gps = ex.get_ifd(0x8825)
    out = {
        "datetime": sub.get(36867) or ex.get(306),
        "make": (ex.get(271) or "").strip() or None,
        "model": (ex.get(272) or "").strip() or None,
        "focal_mm": float(sub[37386]) if sub.get(37386) else None,
        "focal_35mm": sub.get(41989),
        "lat": None, "lon": None,
    }
    if gps and 2 in gps and 4 in gps:
        out["lat"], out["lon"] = round(_dms(gps[2], gps.get(1, "N")), 6), round(_dms(gps[4], gps.get(3, "E")), 6)
    return out


def _date(dt: str | None) -> dict:
    if not dt:
        return {"raw": None, "year_from": None, "year_to": None, "approximate": False}
    d = datetime.strptime(str(dt).strip()[:19], "%Y:%m:%d %H:%M:%S")
    return {"raw": d.strftime("%d.%m.%Y"), "year_from": d.year, "year_to": d.year, "approximate": False}


def _sessions(recs: list[dict]) -> None:
    for r in recs:
        r["raw"]["session"] = []
    timed = sorted((r for r in recs if r["raw"]["exif"]["datetime"]),
                   key=lambda r: (r["raw"]["exif"]["model"] or "", r["raw"]["exif"]["datetime"]))
    groups, cur = [], []
    for r in timed:
        t = datetime.strptime(r["raw"]["exif"]["datetime"][:19], "%Y:%m:%d %H:%M:%S")
        if cur:
            pt = datetime.strptime(cur[-1]["raw"]["exif"]["datetime"][:19], "%Y:%m:%d %H:%M:%S")
            if r["raw"]["exif"]["model"] != cur[-1]["raw"]["exif"]["model"] or (t - pt).total_seconds() > SESSION_GAP_MIN * 60:
                groups.append(cur)
                cur = []
        cur.append(r)
    if cur:
        groups.append(cur)
    for g in groups:
        ids = [r["id"] for r in g]
        for r in g:
            r["raw"]["session"] = [i for i in ids if i != r["id"]]


def build() -> int:
    ensure(IMG_DIR, RECORDS)
    recs = []
    for folder, prio in FOLDERS.items():
        for f in sorted((SRC_DIR / folder).glob("*.jpg")):
            m = SIG_RE.match(f.name)
            if not m:
                continue
            sig = m.group(1)
            with Image.open(f) as im:
                exif = _exif(im)
                full = ImageOps.exif_transpose(im).convert("RGB")
            out = IMG_DIR / f"{sig}.jpg"
            small = full.copy()
            small.thumbnail((MAX_EDGE, MAX_EDGE))
            if not out.exists():
                small.save(out, quality=88)
            loc = None
            if exif["lat"] is not None:
                loc = {"lat": exif["lat"], "lon": exif["lon"], "method": "exif_gps", "precision_m": 50}
            mun = geo.municipality_at(exif["lat"], exif["lon"])
            recs.append({
                "id": f"challenge:{sig}", "source": "challenge", "source_id": sig, "source_url": None,
                "signature": sig, "collection": "SG.CIV.17", "kind": "ground", "title": None,
                "date": _date(exif["datetime"]), "places": [],
                "municipality": mun["name"] if mun else None, "location": loc, "camera": None,
                "photographer": None,
                "license": {"code": "stasz-private", "credit": f"Staatsarchiv Schwyz, {sig}", "url": None},
                "image": {"path": str(out.relative_to(DATA_DIR)), "width": small.width, "height": small.height,
                          "sha1": hashlib.sha1(out.read_bytes()).hexdigest()},
                "parent_id": None, "crop_bbox": None, "split": "challenge",
                "raw": {"file_name": f.name, "folder": folder, "priority": prio,
                        "original_size": [full.width, full.height], "exif": exif},
            })
    _sessions(recs)
    recs.sort(key=lambda r: (r["raw"]["priority"], int(r["signature"].rsplit(".", 1)[1])))
    return write_jsonl(RECORDS_FILE, recs)


if __name__ == "__main__":
    n = build()
    print(f"{n} challenge records -> {RECORDS_FILE}")
