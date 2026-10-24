"""terrain_check: is a target (peak, church, landmark) visible from a candidate viewpoint?

Uses the swisstopo height profile between the two points (free, no key; same disk cache and rate limit
as swisstopo_search) and compares the elevation angle of the target with the highest terrain in between,
corrected for earth curvature and refraction. A blocked line of sight rejects the viewpoint.
"""

import json
import math
from urllib.parse import urlencode

import httpx

from ..server.lv95 import wgs84_to_lv95
from .base import ToolContext, ToolOutput
from .swisstopo import cached_get

PROFILE_URL = "https://api3.geo.admin.ch/rest/services/profile.json"
NB_POINTS = 200
EYE_M = 2.0             # photographer's eye above ground
EARTH_R = 6_371_000.0
REFRACTION_K = 0.13     # standard terrestrial refraction
NEAR_TARGET = 0.05      # the last 5% of the line belongs to the target (its summit and flank)
MIN_M, MAX_M = 50, 80_000

DEFINITION = {
    "name": "terrain_check",
    "description": (
        "Check the line of sight from a candidate viewpoint to a target (e.g. a peak or church you see in the "
        "photo, with coordinates from swisstopo_search). Returns both heights, distance, compass direction "
        "from the viewpoint, and whether terrain blocks the view. Use it to reject viewpoints from which a "
        "visible landmark could not be seen, or to confirm the viewing direction."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "from_lat": {"type": "number", "description": "viewpoint latitude (WGS84)"},
            "from_lon": {"type": "number", "description": "viewpoint longitude (WGS84)"},
            "to_lat": {"type": "number", "description": "target latitude (WGS84)"},
            "to_lon": {"type": "number", "description": "target longitude (WGS84)"},
        },
        "required": ["from_lat", "from_lon", "to_lat", "to_lon"],
        "additionalProperties": False,
    },
    "strict": True,
}

_COMPASS = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"]


def profile_url(a: tuple[float, float], b: tuple[float, float]) -> str:
    geom = json.dumps({"type": "LineString", "coordinates": [[round(a[0]), round(a[1])], [round(b[0]), round(b[1])]]},
                      separators=(",", ":"))
    return PROFILE_URL + "?" + urlencode({"geom": geom, "sr": 2056, "nb_points": NB_POINTS})


def _drop(d: float) -> float:
    """Apparent height loss from earth curvature minus refraction at distance d (m)."""
    return d * d / (2 * EARTH_R) * (1 - REFRACTION_K)


def _angle(dh: float, d: float) -> float:
    return math.degrees(math.atan2(dh - _drop(d), d))


def line_of_sight(points: list[dict]) -> dict:
    """points: swisstopo profile items [{dist, alts: {COMB}, easting, northing}] from viewpoint to target."""
    h0 = points[0]["alts"]["COMB"] + EYE_M
    total = points[-1]["dist"]
    # The target is the highest point near the end of the line, so coordinates slightly off a summit
    # still compare against the summit and not against its flank.
    near = [p for p in points if p["dist"] >= total * (1 - NEAR_TARGET)] or points[-1:]
    top = max(near, key=lambda p: _angle(p["alts"]["COMB"] - h0, max(p["dist"], 1.0)))
    target_h = top["alts"]["COMB"]
    target_angle = _angle(target_h - h0, max(top["dist"], 1.0))
    worst, worst_angle = None, -90.0
    for p in points[1:-1]:
        if p["dist"] <= 0 or p["dist"] >= total * (1 - NEAR_TARGET):
            continue
        a = _angle(p["alts"]["COMB"] - h0, p["dist"])
        if a > worst_angle:
            worst, worst_angle = p, a
    visible = worst is None or worst_angle <= target_angle
    out = {"visible": visible, "target_height_m": round(target_h), "target_elevation_angle_deg": round(target_angle, 2),
           "max_terrain_angle_deg": round(worst_angle, 2) if worst else None}
    if not visible:
        out["blocked_at"] = {"dist_km": round(worst["dist"] / 1000, 2), "height_m": round(worst["alts"]["COMB"]),
                             "E_LV95": round(worst["easting"]), "N_LV95": round(worst["northing"])}
    return out


def run(ctx: ToolContext, from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> ToolOutput:
    a, b = wgs84_to_lv95(from_lat, from_lon), wgs84_to_lv95(to_lat, to_lon)
    de, dn = b[0] - a[0], b[1] - a[1]
    dist = math.hypot(de, dn)
    if not MIN_M <= dist <= MAX_M:
        return ToolOutput({"error": f"distance {dist / 1000:.2f} km outside {MIN_M} m to {MAX_M // 1000} km"},
                          "Geländeprüfung: Distanz ausserhalb des Bereichs", is_error=True)
    url = profile_url(a, b)
    try:
        points = cached_get(url)
    except (httpx.HTTPError, ValueError) as e:
        return ToolOutput({"error": f"swisstopo not reachable: {type(e).__name__}"},
                          "swisstopo-Höhenprofil nicht erreichbar", is_error=True)
    if not isinstance(points, list) or len(points) < 2:
        return ToolOutput({"error": "empty profile"}, "Höhenprofil leer", is_error=True)
    azimuth = math.degrees(math.atan2(de, dn)) % 360
    data = {
        "viewpoint_height_m": round(points[0]["alts"]["COMB"]),
        "distance_km": round(dist / 1000, 2),
        "azimuth_deg": round(azimuth),
        "direction": _COMPASS[round(azimuth / 45) % 8],
        **line_of_sight(points),
        "url": url,
    }
    return ToolOutput(data, _summary(data))


def _summary(d: dict) -> str:
    where = f"{d['distance_km']} km Richtung {d['direction']} ({d['azimuth_deg']}°)"
    if d["visible"]:
        return f"Sichtlinie frei: Ziel auf {d['target_height_m']} m, {where}"
    blk = d["blocked_at"]
    return f"Sicht verdeckt: Gelände auf {blk['height_m']} m nach {blk['dist_km']} km, Ziel {where}"
