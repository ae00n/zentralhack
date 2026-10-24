"""aerial_view and skyline: look at a candidate spot from above, and at the mountains seen from it.

Both wrap data_pipeline functions (Dijar): aerial_image (swisstopo SWISSIMAGE, as of a year) and horizon
(the skyline rendered from terrain tiles, with the named peaks). The pictures go to the model as images, so
it compares them with the photo itself, like a GeoGuessr player switching to satellite view or matching the
mountain outline.
"""

from pathlib import Path

import data_pipeline as dp

from .. import config
from . import sun
from .base import ToolContext, ToolOutput, image_block
from .viewpoint import DEFAULT_FOCAL, field_of_view

AERIAL_PX, SKYLINE_PX = 768, 1024
MAX_CANDIDATES = 4

AERIAL_VIEW = {
    "name": "aerial_view",
    "description": (
        "Aerial photo (swisstopo SWISSIMAGE, north up, red cross = the point) around 1 to 4 candidate spots, "
        "as of the photo's capture year when available. Compare roof shapes, wings, courtyards, harbour "
        "basins, roads, slopes and neighbouring buildings with the photo to decide which candidate it is. "
        "radius_m 30 to 300 (default 70 for a building, larger for a harbour or a village part)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "candidates": {"type": "array", "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "lat": {"type": "number"}, "lon": {"type": "number"}},
                "required": ["name", "lat", "lon"], "additionalProperties": False}},
            "radius_m": {"type": "integer"},
        },
        "required": ["candidates"],
        "additionalProperties": False,
    },
}

SKYLINE = {
    "name": "skyline",
    "description": (
        "The mountain skyline a camera at a candidate spot would see when looking towards heading_deg "
        "(0 = north, 90 = east), drawn to scale with the named peaks, plus where the sun stood at the capture "
        "time (EXIF). The field of view comes from the EXIF focal length. Compare the outline and the peaks "
        "with the photo, and the sun side with the shadows and lit faces in the photo, to accept or reject "
        "the spot and the viewing direction. Use it for views with mountains on the horizon."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"lat": {"type": "number"}, "lon": {"type": "number"},
                       "heading_deg": {"type": "number", "description": "direction the camera looked"}},
        "required": ["lat", "lon", "heading_deg"],
        "additionalProperties": False,
    },
}


def _file(rel: str) -> Path | None:
    """Pictures from data_pipeline are relative to DATA_DIR (the stub's to the fixtures)."""
    from data_pipeline.paths import DATA_DIR

    for base in (Path(DATA_DIR), config.FIXTURES):
        p = base / rel
        if p.exists():
            return p
    return None


def run_aerial(ctx: ToolContext, candidates: list[dict], radius_m: int = 70) -> ToolOutput:
    cands = [c for c in candidates or [] if c.get("lat") is not None and c.get("lon") is not None][:MAX_CANDIDATES]
    if not cands:
        return ToolOutput({"error": "give 1 to 3 candidates with lat and lon"}, "Luftbild: keine Koordinaten",
                          is_error=True)
    radius = max(30, min(int(radius_m or 70), 300))
    data, images = [], []
    for i, c in enumerate(cands, 1):
        try:
            a = dp.aerial_image(c["lat"], c["lon"], radius_m=radius, year=ctx.year)
        except Exception as e:  # one failed tile fetch must not cost the other candidates
            data.append({"name": c["name"], "error": f"{type(e).__name__}"})
            continue
        path = _file(a.get("path") or "")
        item = {"name": c["name"], "lat": c["lat"], "lon": c["lon"], "flight_year": a.get("year"),
                "meters_per_pixel": a.get("meters_per_pixel"), "radius_m": radius}
        data.append(item)
        if path:
            label = f"Luftbild {i}: {c['name']}, {2 * radius} m breit, Norden oben, Stand {a.get('year') or 'aktuell'}"
            images += [{"type": "text", "text": label}, image_block(path, AERIAL_PX, 85)]
    ok = [d for d in data if "error" not in d]
    summary = (f"Luftbilder: {', '.join(d['name'] for d in ok)} (Stand {ok[0]['flight_year'] or 'aktuell'})"
               if ok else "Luftbild: nicht verfügbar")
    return ToolOutput({"candidates": data, "capture_year": ctx.year}, summary, images)


def run_skyline(ctx: ToolContext, lat: float, lon: float, heading_deg: float) -> ToolOutput:
    import math

    fov = math.degrees(field_of_view(ctx.focal_35mm or DEFAULT_FOCAL, ctx.portrait))
    h = dp.horizon(lat, lon, heading_deg, fov_deg=fov)
    data = {"camera_height_m": h.get("camera_height_m"), "heading_deg": h.get("heading_deg"),
            "fov_deg": round(fov, 1), "fov_source": "exif" if ctx.focal_35mm else "assumed",
            "peaks": (h.get("peaks") or [])[:10]}
    when = sun.parse_exif(ctx.captured)
    if when:
        az, el = sun.position(lat, lon, when)
        data["sun"] = {"azimuth_deg": round(az, 1), "elevation_deg": round(el, 1),
                       "as_seen_by_camera": sun.relative(az, heading_deg) if el > 0 else "Sonne unter dem Horizont",
                       "capture_time": ctx.captured}
    images = []
    path = _file(h.get("path") or "")
    if path:
        images = [{"type": "text", "text": f"Skyline von {lat:.4f}, {lon:.4f} Richtung {round(heading_deg)}°, "
                                           f"Blickfeld {round(fov)}°"}, image_block(path, SKYLINE_PX, 85)]
    visible = [p["name"] for p in data["peaks"] if p.get("visible")][:4]
    sun_txt = f", {data['sun']['as_seen_by_camera']}" if "sun" in data else ""
    summary = f"Skyline Richtung {round(heading_deg)}°: {', '.join(visible) or 'keine benannten Gipfel'}{sun_txt}"
    return ToolOutput(data, summary, images)
