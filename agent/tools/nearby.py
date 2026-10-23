"""photos_near: reference photos taken at a candidate spot (the GeoGuessr "walk around" step).

similar_images asks "what looks like this photo?"; photos_near asks "what does the place I suspect look
like?". data_pipeline.photos_near returns the reference photos whose camera position is near a point
(Commons, E-Pics/Smapshot, LUBIS, ...), nearest first, with the camera direction where a pose is known.
The nearest are shown as thumbnails, so the model can compare buildings and skyline itself.
"""

import data_pipeline as dp

from .base import ToolContext, ToolOutput, base_id, image_block

DEFAULT_RADIUS, MAX_RADIUS = 300, 2000
LIMIT, THUMBS, THUMB_PX = 8, 4, 384
_COMPASS = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"]

DEFINITION = {
    "name": "photos_near",
    "description": (
        "Reference photos taken near a candidate spot (camera position within radius_m), nearest first, "
        "with the camera direction where known; the nearest 4 are shown as images. Use it to check a "
        "hypothesis: go to the place you suspect (e.g. the coordinates of a building or a viewpoint_search "
        "spot) and compare what the references show with the photo. A reference that shows the same "
        "buildings or the same skyline is evidence of kind similar_image with its ref_id; a reference that "
        "only shows the same area is not."
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


def run(ctx: ToolContext, lat: float, lon: float, radius_m: int = DEFAULT_RADIUS) -> ToolOutput:
    radius = max(50, min(int(radius_m or DEFAULT_RADIUS), MAX_RADIUS))
    excluded = ctx.excluded_bases()
    raw = dp.photos_near(lat, lon, radius_m=radius, exclude_ids=list(ctx.exclude_ids), limit=LIMIT + 4)
    hits = [h for h in raw if base_id(h["id"]) not in excluded][:LIMIT]  # leakage guard, independent of data_pipeline
    data, images = [], []
    for i, h in enumerate(hits, 1):
        item = {"rank": i, "id": h["id"], "distance_m": h.get("distance_m"), "source": h.get("source"),
                "title": h.get("title"), "year": h.get("year"), "heading_deg": h.get("heading_deg"),
                "looking": _COMPASS[round(h["heading_deg"] / 45) % 8] if h.get("heading_deg") is not None else None}
        data.append({k: v for k, v in item.items() if v not in (None, [], "")})
        # a reference at a known position that the model compared itself may be cited as a source
        ctx.verified_refs.update({h["id"], base_id(h["id"])})
        if i <= THUMBS:
            try:
                path = dp.image_file(dp.get_record(h["id"]))
            except Exception:
                path = None
            if path and path.exists():
                looking = f", Blick nach {item['looking']}" if item.get("looking") else ""
                label = f"Foto {i}: {h['id']}, {h.get('distance_m')} m{looking}, {h.get('title') or 'ohne Titel'}"
                images += [{"type": "text", "text": label}, image_block(path, THUMB_PX, 80)]
    out = {"center": {"lat": lat, "lon": lon}, "radius_m": radius, "n": len(hits), "photos": data}
    return ToolOutput(out, _summary(data, radius, len(hits)), images)


def _summary(photos: list[dict], radius: int, n: int) -> str:
    if not photos:
        return f"Fotos vor Ort: keine Referenzfotos im Umkreis von {radius} m"
    first = photos[0]
    return f"Fotos vor Ort: {n} im Umkreis von {radius} m, nächstes {first.get('title') or first['id']} ({first['distance_m']} m)"
