"""viewpoint_search: where was the camera, given the landmarks it shows? (what GeoGuessr players do by eye)

The model names 2 or more landmarks it sees (peaks, a church tower, an island) with their coordinates and
their horizontal position in the photo. The field of view follows from the EXIF focal length, so the angle
between two landmarks in the photo is known. A grid search finds the spots from which the landmarks lie in
the same left/right order and at the same angles; the best spots are then checked for a free line of sight
on the swisstopo height profile. With 2 landmarks the fit is a curve, with 3 or more it is a point.
"""

import math

import data_pipeline as dp
import httpx
import numpy as np

from ..server.lv95 import lv95_to_wgs84, wgs84_to_lv95
from .base import ToolContext, ToolOutput
from .swisstopo import cached_get
from .terrain import line_of_sight, profile_url

DEFAULT_FOCAL = 35.0
# search area: Kanton Schwyz with a margin (LV95), and the finer grid around a given candidate place
REGION = (2670000, 2735000, 1180000, 1240000)
REGION_STEP = 250
MIN_DIST_M, MAX_DIST_M = 300, 60000
GOOD_FIT_DEG = 2.0
CHECK_SPOTS = 6
SPACING_M = 1000

DEFINITION = {
    "name": "viewpoint_search",
    "description": (
        "Find where the camera stood from 2 or more landmarks visible in the photo (peaks, church towers, "
        "islands, a lake end). For each landmark give its coordinates (from swisstopo_search or "
        "named_buildings) and its horizontal position x in the photo (0 = left edge, 0.5 = centre, "
        "1 = right edge). Uses the EXIF focal length for the field of view, searches the canton (or the "
        "area around 'near') for spots that see the landmarks at the same angles, and checks the line of "
        "sight. Returns the best spots with Ortschaft and Gemeinde. Use it for landscape and lake views, "
        "and to decide between candidate places. 3 landmarks pin a point; 2 give a curve, so add 'near'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "landmarks": {
                "type": "array",
                "items": {"type": "object",
                          "properties": {"name": {"type": "string"}, "lat": {"type": "number"},
                                         "lon": {"type": "number"},
                                         "x": {"type": "number", "description": "0 left edge .. 1 right edge"}},
                          "required": ["name", "lat", "lon", "x"], "additionalProperties": False},
            },
            "near": {"type": ["object", "null"],
                     "properties": {"lat": {"type": "number"}, "lon": {"type": "number"},
                                    "radius_m": {"type": "number"}},
                     "required": ["lat", "lon", "radius_m"], "additionalProperties": False,
                     "description": "optional: only search around this candidate place"},
        },
        "required": ["landmarks"],
        "additionalProperties": False,
    },
}

_COMPASS = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"]


def field_of_view(focal_35mm: float, portrait: bool = False) -> float:
    """Horizontal field of view in radians (35 mm frame: 36 x 24 mm)."""
    width = 24.0 if portrait else 36.0
    return 2 * math.atan(width / (2 * focal_35mm))


def image_angle(x: float, fov: float) -> float:
    """Angle right of the image centre for horizontal position x (rectilinear lens), radians."""
    return math.atan((x - 0.5) * 2 * math.tan(fov / 2))


def fit(landmarks_lv95: list[tuple[float, float]], angles: list[float], e: np.ndarray, n: np.ndarray):
    """For candidate camera points (arrays e, n): RMS angle error (deg) and camera heading (deg)."""
    d = []
    for (le, ln), th in zip(landmarks_lv95, angles):
        bearing = np.arctan2(le - e, ln - n)  # clockwise from north, radians
        d.append(bearing - th)                # heading the camera would need for this landmark
    d = np.stack(d)                           # (L, points)
    heading = np.arctan2(np.sin(d).mean(0), np.cos(d).mean(0))
    resid = np.angle(np.exp(1j * (d - heading)))
    err = np.degrees(np.sqrt((resid ** 2).mean(0)))
    return err, np.degrees(heading) % 360


def _grid(near: dict | None):
    if near:
        ce, cn = wgs84_to_lv95(near["lat"], near["lon"])
        r = max(300.0, min(float(near.get("radius_m") or 3000), 15000.0))
        step = max(50.0, r / 60)
        es, ns = np.arange(ce - r, ce + r + 1, step), np.arange(cn - r, cn + r + 1, step)
    else:
        es = np.arange(REGION[0], REGION[1] + 1, REGION_STEP)
        ns = np.arange(REGION[2], REGION[3] + 1, REGION_STEP)
    e, n = np.meshgrid(es, ns)
    return e.ravel().astype(float), n.ravel().astype(float)


def _spots(e, n, err, k: int):
    """The k best points, at least SPACING_M apart (otherwise all winners sit in one cluster)."""
    out = []
    for i in np.argsort(err):
        if not np.isfinite(err[i]):
            break
        if all(math.hypot(e[i] - a, n[i] - b) >= SPACING_M for a, b, _ in out):
            out.append((float(e[i]), float(n[i]), float(err[i])))
        if len(out) == k:
            break
    return out


def run(ctx: ToolContext, landmarks: list[dict], near: dict | None = None) -> ToolOutput:
    marks = [m for m in landmarks or [] if m.get("lat") is not None and m.get("lon") is not None]
    if len(marks) < 2:
        return ToolOutput({"error": "need at least 2 landmarks with coordinates and x"},
                          "Blickpunktsuche: mindestens 2 Orientierungspunkte nötig", is_error=True)
    focal = ctx.focal_35mm or DEFAULT_FOCAL
    fov = field_of_view(focal, ctx.portrait)
    angles = [image_angle(min(1.0, max(0.0, float(m["x"]))), fov) for m in marks]
    lv = [wgs84_to_lv95(m["lat"], m["lon"]) for m in marks]
    e, n = _grid(near)
    err, heading = fit(lv, angles, e, n)
    dist = np.stack([np.hypot(le - e, ln - n) for le, ln in lv])
    err[(dist.min(0) < MIN_DIST_M) | (dist.max(0) > MAX_DIST_M)] = np.inf
    spots = _spots(e, n, err, CHECK_SPOTS)

    out = []
    for se, sn, se_err in spots:
        idx = int(np.argmin((e - se) ** 2 + (n - sn) ** 2))
        lat, lon = lv95_to_wgs84(se, sn)
        seen = {}
        for m, (le, ln) in zip(marks[:3], lv[:3]):
            try:
                pts = cached_get(profile_url((se, sn), (le, ln)))
                seen[m["name"]] = bool(line_of_sight(pts)["visible"]) if isinstance(pts, list) and len(pts) > 1 else None
            except (httpx.HTTPError, ValueError):
                seen[m["name"]] = None
        out.append({"lat": round(lat, 5), "lon": round(lon, 5), "error_deg": round(se_err, 2),
                    "heading_deg": round(float(heading[idx])), "direction": _COMPASS[round(heading[idx] / 45) % 8],
                    "visible": seen,
                    "distance_km": {m["name"]: round(float(dist[k, idx]) / 1000, 1) for k, m in enumerate(marks)}})
    # spots that see every checked landmark first, then by fit
    out.sort(key=lambda s: (any(v is False for v in s["visible"].values()), s["error_deg"]))
    for s in out[:3]:
        try:
            a = dp.address_lookup(s["lat"], s["lon"], radius_m=200, limit=1)
            s["ortschaft"], s["municipality"], s["in_canton"] = a.get("ortschaft"), a.get("municipality"), a.get("in_canton")
        except Exception:
            pass
    data = {"focal_35mm": focal, "focal_source": "exif" if ctx.focal_35mm else "assumed",
            "field_of_view_deg": round(math.degrees(fov), 1), "landmarks": len(marks),
            "spots": out[:3], "good_fit_deg": GOOD_FIT_DEG,
            "note": ("2 landmarks fit a curve: the spots are only as good as 'near' or a third landmark"
                     if len(marks) == 2 else "3 or more landmarks: the best spot is a point fit")}
    return ToolOutput(data, _summary(out[:3]))


def _summary(spots: list[dict]) -> str:
    if not spots:
        return "Blickpunktsuche: kein passender Standort"
    best = spots[0]
    where = best.get("ortschaft") or best.get("municipality") or f"{best['lat']}, {best['lon']}"
    fit_word = "passt" if best["error_deg"] <= GOOD_FIT_DEG else "passt schlecht"
    blocked = [k for k, v in best["visible"].items() if v is False]
    tail = f", verdeckt: {', '.join(blocked)}" if blocked else ""
    nxt = f"; danach {spots[1].get('ortschaft') or spots[1].get('municipality')} ({spots[1]['error_deg']}°)" if len(spots) > 1 else ""
    return f"Blickpunkt: {where} {fit_word} (Abweichung {best['error_deg']}°, Blick nach {best['direction']}{tail}){nxt}"
