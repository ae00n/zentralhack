"""Stub of the section 4 interface: every function answers from contracts/fixtures/.

Active when env DATA_PIPELINE_STUB=1 (see data_pipeline/__init__.py). Same signatures as api.py,
so Agent can build before the real index exists. Image paths resolve against the fixtures folder.
"""

import json
from functools import lru_cache
from pathlib import Path

from .paths import REPO_ROOT

FIXTURES = REPO_ROOT / "contracts" / "fixtures"


@lru_cache(maxsize=None)
def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _record() -> dict:
    return _load("photo_record.json")


def reload() -> None:
    _load.cache_clear()


def image_file(record: dict) -> Path | None:
    p = (record.get("image") or {}).get("path")
    return FIXTURES / p if p else None


def get_record(photo_id: str) -> dict | None:
    r = _record()
    return r if photo_id.split("#", 1)[0] == r["id"] else None


def eval_ids() -> frozenset[str]:
    return frozenset()


def gazetteer() -> list[dict]:
    return _load("gemeinden.json")


def similar_images(image_path: str, k: int = 8, model: str = "best",
                   exclude_ids: list[str] = (), sources: list[str] | None = None) -> list[dict]:
    r = _record()
    if r["id"] in {i.split("#", 1)[0] for i in exclude_ids}:
        return []
    if sources and r["source"] not in sources:
        return []
    return [{"id": r["id"], "score": 0.91, "record": r}][:k]


def archive_lookup(place: str | None = None, municipality: str | None = None,
                   year_from: int | None = None, year_to: int | None = None, limit: int = 20) -> list[dict]:
    return [_record()][:limit]


def split_composite(image_path: str) -> list[dict]:
    from PIL import Image

    with Image.open(image_path) as im:
        w, h = im.size
    return [{"bbox": [0, 0, w, h], "path": str(image_path)}]


def timeline(lat: float, lon: float, radius_m: int = 1000) -> list[dict]:
    t = _load("timeline.json")
    return [{"id": p["id"], "year_from": p["year_from"], "year_to": p["year_to"],
             "distance_m": p["distance_m"], "image_path": "sample.jpg"} for p in t["photos"]]


def date_hints(photo_id: str | None = None, image_path: str | None = None, exclude_ids=()) -> list[dict]:
    return _load("date_hints.json")


def address_lookup(lat: float, lon: float, radius_m: int = 100, limit: int = 10) -> dict:
    return _load("address_lookup.json")


def named_buildings(lat: float | None = None, lon: float | None = None, radius_m: int = 500,
                    name: str | None = None, kinds: list[str] | None = None, limit: int = 20) -> list[dict]:
    return _load("named_buildings.json")[:limit]


def photos_near(lat: float, lon: float, radius_m: int = 500, max_precision_m: int = 500,
                sources: list[str] | None = None, exclude_ids: list[str] = (), limit: int = 12) -> list[dict]:
    r = _record()
    if r["id"] in {i.split("#", 1)[0] for i in exclude_ids}:
        return []
    return [{"id": r["id"], "source": r["source"], "title": r.get("title"), "year": r["date"]["year_from"],
             "distance_m": 120, "precision_m": 50, "heading_deg": 135, "image_path": r["image"]["path"]}][:limit]


def aerial_image(lat: float, lon: float, radius_m: float = 80, year: int | None = None) -> dict:
    return {"path": "sample.jpg", "year": year, "meters_per_pixel": 0.2, "width": 800, "height": 800,
            "radius_m": radius_m}


def horizon(lat: float, lon: float, heading_deg: float, fov_deg: float = 60) -> dict:
    return {"path": "sample.jpg", "camera_height_m": 440, "heading_deg": heading_deg, "fov_deg": fov_deg,
            "azimuths_deg": [heading_deg], "elevation_deg": [5.0],
            "peaks": [{"name": "Grosser Mythen", "azimuth_deg": heading_deg, "offset_deg": 0.0, "distance_km": 3.0,
                       "elevation_deg": 25.0, "ele_m": 1898, "visible": True}]}
