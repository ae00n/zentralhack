"""photos_near: reference photos taken at a candidate spot (the GeoGuessr "walk around" step).

similar_images asks "what looks like this photo?"; photos_near asks "what does the place I suspect look
like?". It returns the reference photos whose camera position is near a point (Commons, E-Pics/Smapshot
and LUBIS carry positions to within about 100 m) and shows the nearest as thumbnails, so the model can
compare buildings and skyline itself.
"""

import math
from functools import lru_cache

import data_pipeline as dp

from .base import ToolContext, ToolOutput, base_id, image_block, year_span

MAX_PRECISION_M = 150   # only references whose position is known this well
DEFAULT_RADIUS, MAX_RADIUS = 300, 2000
LIMIT, THUMBS, THUMB_PX = 8, 4, 384

DEFINITION = {
    "name": "photos_near",
    "description": (
        "Reference photos taken near a candidate spot (camera position within radius_m), nearest first, "
        "the nearest 4 shown as images. Use it to check a hypothesis: go to the place you suspect (e.g. the "
        "coordinates of a building or a viewpoint_search spot) and compare what the references show with "
        "the photo. A reference that shows the same buildings or the same skyline is evidence of kind "
        "similar_image with its ref_id; a reference that only shows the same area is not."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "radius_m": {"type": "integer", "description": "default 300, max 2000"},
        },
        "required": ["lat", "lon"],
        "additionalProperties": False,
    },
}


def _dist_m(lat1, lon1, lat2, lon2) -> float:
    k = math.pi / 180
    x = (lon2 - lon1) * k * math.cos((lat1 + lat2) / 2 * k)
    return 6371000 * math.hypot(x, (lat2 - lat1) * k)


@lru_cache(maxsize=1)
def _index() -> tuple:
    """(lat, lon, record) of every reference photo with a precise camera position."""
    from ..server import catalogue

    out = []
    seen = set()
    for r in catalogue.all_records():
        loc = r.get("location") or {}
        if r["id"] in seen or r.get("source") in ("challenge", "upload") or r.get("split") == "challenge":
            continue
        if loc.get("lat") is None or (loc.get("precision_m") or 1e9) > MAX_PRECISION_M:
            continue
        seen.add(r["id"])
        out.append((loc["lat"], loc["lon"], r))
    return tuple(out)


def run(ctx: ToolContext, lat: float, lon: float, radius_m: int = DEFAULT_RADIUS) -> ToolOutput:
    radius = max(50, min(int(radius_m or DEFAULT_RADIUS), MAX_RADIUS))
    excluded = ctx.excluded_bases()
    hits = []
    for rlat, rlon, rec in _index():
        if abs(rlat - lat) > 0.02 or abs(rlon - lon) > 0.03:  # cheap box before the distance
            continue
        if base_id(rec["id"]) in excluded or (rec.get("parent_id") and base_id(rec["parent_id"]) in excluded):
            continue
        d = _dist_m(lat, lon, rlat, rlon)
        if d <= radius:
            hits.append((d, rec))
    hits.sort(key=lambda h: h[0])
    data, images = [], []
    for i, (d, rec) in enumerate(hits[:LIMIT], 1):
        item = {"rank": i, "id": rec["id"], "distance_m": round(d), "source": rec.get("source"),
                "title": rec.get("title"), "municipality": rec.get("municipality"),
                "places": (rec.get("places") or [])[:5], "year": year_span(rec)}
        data.append({k: v for k, v in item.items() if v not in (None, [], "")})
        # a reference at a known position that the model compared itself may be cited as a source
        ctx.verified_refs.update({rec["id"], base_id(rec["id"])})
        if i <= THUMBS:
            try:
                path = dp.image_file(rec)
            except Exception:
                path = None
            if path and path.exists():
                label = f"Foto {i}: {rec['id']}, {round(d)} m, {rec.get('title') or 'ohne Titel'}"
                images += [{"type": "text", "text": label}, image_block(path, THUMB_PX, 80)]
    out = {"center": {"lat": lat, "lon": lon}, "radius_m": radius, "n": len(hits), "photos": data}
    return ToolOutput(out, _summary(data, radius, len(hits)), images)


def _summary(photos: list[dict], radius: int, n: int) -> str:
    if not photos:
        return f"Fotos vor Ort: keine Referenzfotos im Umkreis von {radius} m"
    first = photos[0]
    return f"Fotos vor Ort: {n} im Umkreis von {radius} m, nächstes {first.get('title') or first['id']} ({first['distance_m']} m)"
