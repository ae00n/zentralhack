"""The AnalysisResult field block (CONTRACTS section 3) and the image block sent to Claude."""

import base64
import io
import json
from pathlib import Path

import data_pipeline as dp

from .config import FIXTURES

# the archive's priority (Ortschaft, Gemeinde, Gebaeude, See/Fluss/Berg, Strasse), then the map pin
FIELD_NAMES = ["locality", "municipality", "buildings", "landscape_features", "street", "coordinates"]


def empty_fields() -> dict:
    return {n: {"value": [] if n in ("buildings", "landscape_features") else None,
                "confidence": 0.0, "evidence": []} for n in FIELD_NAMES}


def municipalities() -> list[str]:
    """The canonical Gemeinde names (data_pipeline gazetteer, else the contract fixture)."""
    try:
        names = [g["name"] for g in dp.gazetteer()]
    except Exception:
        names = []
    if not names:
        names = [g["name"] for g in json.loads((FIXTURES / "gemeinden.json").read_text(encoding="utf-8"))]
    return sorted(set(names))


def image_block(path: str | Path, max_px: int = 1024, quality: int = 88) -> dict:
    """Base64 JPEG image block, long edge at most max_px."""
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg",
                       "data": base64.standard_b64encode(buf.getvalue()).decode("ascii")}}
