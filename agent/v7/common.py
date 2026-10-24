"""Shared helpers for v7: paths, the photo at full resolution, image blocks, distances, a JSON cache."""

import base64
import hashlib
import io
import json
import math
import os
import re
from pathlib import Path

import data_pipeline as dp

from ..config import CACHE_DIR, DATA_DIR

V7_DIR = DATA_DIR / "v7"
CLAUDE_CACHE = CACHE_DIR / "v7"
CACHE_ONLY = os.environ.get("AGENT_CACHE_ONLY") == "1"
IMAGE_PX = 1568  # the API's largest size without downscaling
TILE_PX = 1024
SURE = ("sicher", "wahrscheinlich", "vermutet")


def original(rec: dict) -> Path:
    """The photo at full resolution (data/challenge/<folder>/<file>), else the 1024 px copy."""
    raw = rec.get("raw") or {}
    if raw.get("folder") and raw.get("file_name"):
        p = DATA_DIR / "challenge" / raw["folder"] / raw["file_name"]
        if p.exists():
            return p
    return Path(dp.image_file(rec))


def jpeg(path: Path | str, max_px: int, quality: int = 88, box: tuple | None = None) -> bytes:
    """The image (or the box (x0, y0, x1, y1) of it, as fractions) as JPEG, long edge at most max_px."""
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        if box:
            w, h = im.size
            x0, y0, x1, y1 = (max(0.0, min(1.0, float(v))) for v in box)
            if x1 - x0 < 0.02 or y1 - y0 < 0.02:
                raise ValueError("box too small")
            im = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def block(data: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(data).decode("ascii")}}


def image(path: Path | str, max_px: int = 512, box: tuple | None = None) -> dict:
    return block(jpeg(path, max_px, 85, box))


def quarters(path: Path) -> list[dict]:
    """The four overlapping quarters of a large photo, so small text stays readable."""
    from PIL import Image
    with Image.open(path) as im:
        if max(im.size) <= IMAGE_PX * 1.2:
            return []
    return [image(path, TILE_PX, (x, y, x + 0.55, y + 0.55)) for x, y in ((0, 0), (0.45, 0), (0, 0.45), (0.45, 0.45))]


def dist_m(a: dict, b: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def gem(s: str | None) -> str:
    """Gemeinde key: "Küssnacht (SZ)" and "Küssnacht" compare equal."""
    return re.sub(r"\s*\(SZ\)\s*$", "", s or "").strip().casefold()


def key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, default=str).encode()).hexdigest()[:24]


def cached(name: str) -> dict | None:
    p = CLAUDE_CACHE / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def store(name: str, value: dict) -> None:
    CLAUDE_CACHE.mkdir(parents=True, exist_ok=True)
    (CLAUDE_CACHE / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False))
