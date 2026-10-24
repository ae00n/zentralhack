"""Records, images, uploads, demo list and map years for the HTTP layer.

Everything archive-related goes through data_pipeline. Where data_pipeline has no public function
yet (listing records, the demo list, map years), the gap is handled here in one place.
"""

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import data_pipeline as dp
from PIL import Image

from .. import config

UPLOAD_PREFIX = "upload:"
# fallback when no tile manifest exists: a subset of the real zeitreihen TIME values
FALLBACK_MAP_YEARS = [18641231, 18781231, 18901231, 19041231, 19141231, 19241231,
                      19401231, 19561231, 19701231, 19851231, 20001231, 20211231]


def uploads_dir() -> Path:
    return config.CACHE_DIR / "uploads"


def _stub() -> bool:
    return os.environ.get("DATA_PIPELINE_STUB") == "1"


# ---------- records ----------

def all_records() -> list[dict]:
    """Every PhotoRecord. Uses a public data_pipeline lister if one exists."""
    for name in ("records", "all_records", "list_records"):
        fn = getattr(dp, name, None)
        if callable(fn):
            return list(fn())
    if _stub():
        rec = json.loads((config.FIXTURES / "photo_record.json").read_text(encoding="utf-8"))
        return [rec]
    # stopgap until Data exposes a public lister: the private record cache of data_pipeline.api
    from data_pipeline import api
    try:
        return list(api._records().values())
    except FileNotFoundError:
        return []


def _unique(records: list[dict]) -> list[dict]:
    # merged Smapshot aliases map to the same record object; list each record once
    seen, out = set(), []
    for r in records:
        if r["id"] not in seen:
            seen.add(r["id"])
            out.append(r)
    return out


def _natural(r: dict) -> tuple:
    """Prio 1 first, then by signature with numbers compared as numbers (SG.CIV.17.3 before SG.CIV.17.10)."""
    prio = (r.get("raw") or {}).get("priority")
    key = re.split(r"(\d+)", r.get("signature") or r["id"])
    return (prio if isinstance(prio, int) else 9, [int(x) if x.isdigit() else x for x in key])


def list_records(split: str | None = None, municipality: str | None = None, q: str | None = None,
                 priority: int | None = None) -> list[dict]:
    out = []
    ql = q.casefold() if q else None
    for r in _unique(all_records()):
        if split and r.get("split") != split:
            continue
        if priority is not None and (r.get("raw") or {}).get("priority") != priority:
            continue
        if municipality and (r.get("municipality") or "").casefold() != municipality.casefold():
            continue
        if ql:
            hay = " ".join([r["id"], r.get("title") or "", r.get("signature") or "",
                            " ".join(r.get("places") or []), r.get("municipality") or ""]).casefold()
            if ql not in hay:
                continue
        out.append(r)
    if split == "challenge" or priority is not None:
        out.sort(key=_natural)
    return out


def get_record(photo_id: str) -> dict | None:
    if photo_id.startswith(UPLOAD_PREFIX):
        return upload_record(photo_id)
    return dp.get_record(photo_id)


def image_path(photo_id: str) -> Path | None:
    if photo_id.startswith(UPLOAD_PREFIX):
        p = uploads_dir() / (photo_id[len(UPLOAD_PREFIX):] + ".jpg")
        return p if p.exists() else None
    rec = dp.get_record(photo_id)
    if rec is None:
        return None
    p = dp.image_file(rec)
    return Path(p) if p and Path(p).exists() else None


# ---------- uploads ----------

def save_upload(data: bytes, filename: str | None = None) -> str:
    """Store an uploaded image as JPEG (max 1024 px) and return its id `upload:<sha1[:12]>`."""
    sha = hashlib.sha1(data).hexdigest()
    key = sha[:12]
    d = uploads_dir()
    d.mkdir(parents=True, exist_ok=True)
    jpg = d / f"{key}.jpg"
    if not jpg.exists():
        import io
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            im.thumbnail((1024, 1024))
            im.save(jpg, "JPEG", quality=90)
    with Image.open(jpg) as im:
        w, h = im.size
    meta = {"filename": filename, "sha1": sha, "width": w, "height": h}
    (d / f"{key}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return UPLOAD_PREFIX + key


def upload_record(photo_id: str) -> dict | None:
    key = photo_id[len(UPLOAD_PREFIX):]
    meta_p = uploads_dir() / f"{key}.json"
    if not meta_p.exists():
        return None
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    return {
        "id": photo_id, "source": "upload", "source_id": key, "source_url": None,
        "signature": None, "collection": None, "kind": "unknown",
        "title": meta.get("filename") or "Hochgeladenes Foto",
        "date": {"raw": None, "year_from": None, "year_to": None, "approximate": False},
        "places": [], "municipality": None, "location": None, "camera": None, "photographer": None,
        "license": {"code": "upload", "credit": "Hochgeladen", "url": None},
        "image": {"path": f"uploads/{key}.jpg", "width": meta["width"], "height": meta["height"],
                  "sha1": meta["sha1"]},
        "parent_id": None, "crop_bbox": None, "split": "none", "raw": {},
    }


# ---------- images ----------

@lru_cache(maxsize=256)
def _resized(path: str, mtime: float, w: int) -> bytes:
    import io
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > w:
            im = im.resize((w, max(1, round(im.height * w / im.width))), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return buf.getvalue()


def image_bytes(path: Path, w: int | None) -> bytes:
    if not w:
        if path.suffix.lower() in (".jpg", ".jpeg"):
            return path.read_bytes()
        w = 10 ** 6  # re-encode as JPEG without resizing
    return _resized(str(path), path.stat().st_mtime, w)


# ---------- demo, timeline, tiles ----------

def demo() -> list[dict]:
    """[{id, why, record}] in pitch order. Needs a data_pipeline demo() function for real data."""
    fn = getattr(dp, "demo", None) or getattr(dp, "demo_cards", None)
    if callable(fn):
        items = list(fn())
    elif _stub():
        rec = all_records()[0]
        items = [{"id": rec["id"], "why": "Testkarte aus den Fixtures"}]
    else:
        items = []
    out = []
    for it in items:
        rec = it.get("record") or dp.get_record(it["id"])
        if rec:
            out.append({"id": it["id"], "why": it.get("why"), "record": rec})
    return out


def tiles_dir() -> Path:
    from data_pipeline import tiles
    return tiles.TILES


def tile_manifest() -> dict:
    p = tiles_dir() / "manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def map_years() -> list[int]:
    years = tile_manifest().get("map_years")
    return [int(y) for y in years] if years else list(FALLBACK_MAP_YEARS)


def image_url(photo_id: str) -> str:
    return "/images/" + quote(photo_id, safe=":")


def timeline(lat: float, lon: float, radius_m: int) -> list[dict]:
    return [{"id": p["id"], "year_from": p["year_from"], "year_to": p["year_to"],
             "distance_m": p["distance_m"], "image_url": image_url(p["id"])}
            for p in dp.timeline(lat, lon, radius_m)]
