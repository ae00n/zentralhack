"""Skyline from a candidate spot: the mountain horizon a camera there would see, as data and as a picture.

    from data_pipeline import horizon
    horizon(46.9958, 8.6066, heading_deg=110, fov_deg=60)
    python -m data_pipeline.horizon 46.9958 8.6066 --heading 110 --fov 60

GeoGuessr players compare mountain outlines; this draws the outline from a terrain model so the agent can
compare it with the photo (Brunnen vs Gersau vs Immensee). Rays every 0.25 degrees out to 60 km, the
highest elevation angle per ray (earth curvature and refraction included) is the horizon. Named peaks
(OSM peaks in data/gazetteer/buildings.json) inside the view are labelled, `visible` when they lie on the
skyline rather than behind a nearer ridge.

Terrain: AWS Terrain Tiles (Terrarium PNG, open data, no key; about 26 m per pixel at z12 near the camera,
z11 beyond 15 km), cached under data/tiles/terrarium/. Picture: data/tiles/horizon/, sky above, terrain
below, a degree scale and the peak names.
"""

import argparse
import io
import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from .http import PoliteClient
from .paths import DATA_DIR, ensure

TERRARIUM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
CACHE = DATA_DIR / "tiles" / "terrarium"
OUT = DATA_DIR / "tiles" / "horizon"
EARTH_R = 6371000.0
REFRACTION = 0.13
MAX_DIST_M = 60000
NEAR_M = 15000
STEP_DEG = 0.25
EYE_M = 1.7
PEAK_TOLERANCE_DEG = 0.3

_client: PoliteClient | None = None


def _http() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient(min_interval=0.05)
    return _client


@lru_cache(maxsize=512)
def _tile(z: int, x: int, y: int) -> np.ndarray:
    path = CACHE / str(z) / str(x) / f"{y}.png"
    if not path.exists():
        data = _http().get(TERRARIUM.format(z=z, x=x, y=y), cache=False)
        ensure(path.parent)
        path.write_bytes(data)
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768


def height(lat: float, lon: float, z: int = 12) -> float:
    """Terrain height in metres (nearest pixel of the Terrarium tile)."""
    n = 2 ** z
    fx = (lon + 180) / 360 * n
    fy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    t = _tile(z, int(fx), int(fy))
    return float(t[min(255, int((fy % 1) * 256)), min(255, int((fx % 1) * 256))])


def _dest(lat: float, lon: float, az_deg: float, d: float) -> tuple[float, float]:
    """Point d metres from (lat, lon) towards azimuth az (flat approximation, fine within 60 km)."""
    a = math.radians(az_deg)
    dlat = d * math.cos(a) / 111320
    dlon = d * math.sin(a) / (111320 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def _distances() -> np.ndarray:
    d, out = 60.0, []
    while d < MAX_DIST_M:
        out.append(d)
        d += max(25.0, d * 0.008)
    return np.array(out)


def _ray(lat: float, lon: float, h0: float, az: float, dists: np.ndarray) -> tuple[float, float]:
    """(horizon elevation angle in degrees, distance in m of the point that forms it) for one azimuth."""
    best, best_d = -90.0, 0.0
    for d in dists:
        la, lo = _dest(lat, lon, az, d)
        h = height(la, lo, 12 if d < NEAR_M else 11)
        drop = d * d / (2 * EARTH_R) * (1 - REFRACTION)
        ang = math.degrees(math.atan2(h - drop - h0, d))
        if ang > best:
            best, best_d = ang, d
    return best, best_d


def _bearing(lat: float, lon: float, la: float, lo: float) -> tuple[float, float]:
    dy = (la - lat) * 111320
    dx = (lo - lon) * 111320 * math.cos(math.radians(lat))
    return math.degrees(math.atan2(dx, dy)) % 360, math.hypot(dx, dy)


def _peaks(lat: float, lon: float, h0: float, azs: np.ndarray, elev: np.ndarray, heading: float, fov: float) -> list[dict]:
    from .places import _buildings
    out = []
    for b in _buildings():
        if b.get("kind") != "Berg":
            continue
        az, d = _bearing(lat, lon, b["lat"], b["lon"])
        off = (az - heading + 180) % 360 - 180
        if abs(off) > fov / 2 or d < 500 or d > MAX_DIST_M:
            continue
        try:
            h = float(str((b.get("tags") or {}).get("ele", "")).split()[0].replace(",", "."))
        except (ValueError, IndexError):  # no or odd "ele" tag: take it from the terrain
            h = height(b["lat"], b["lon"], 12)
        drop = d * d / (2 * EARTH_R) * (1 - REFRACTION)
        ang = math.degrees(math.atan2(h - drop - h0, d))
        sky = float(np.interp(off, azs - heading, elev))
        out.append({"name": b["name"], "azimuth_deg": round(az, 1), "offset_deg": round(off, 1),
                    "distance_km": round(d / 1000, 1), "elevation_deg": round(ang, 2), "ele_m": round(h),
                    "visible": ang >= sky - PEAK_TOLERANCE_DEG})
    out.sort(key=lambda p: (not p["visible"], -p["elevation_deg"]))
    return out[:15]


def _draw(azs: np.ndarray, elev: np.ndarray, heading: float, fov: float, peaks: list[dict], w: int = 1024) -> Image.Image:
    """Same scale on both axes (1 degree wide = 1 degree high), so the outline looks like it does in a photo."""
    lo, hi = min(-2.0, float(elev.min()) - 1), max(5.0, float(elev.max()) + 4)
    h = int(min(900, max(200, (hi - lo) * (w - 1) / fov)))
    hi = lo + (h - 1) * fov / (w - 1)
    img = Image.new("RGB", (w, h), (205, 225, 245))
    d = ImageDraw.Draw(img)
    xs = (azs - (heading - fov / 2)) / fov * (w - 1)
    ys = (hi - elev) / (hi - lo) * (h - 1)
    d.polygon([(0, h)] + list(zip(xs.tolist(), ys.tolist())) + [(w - 1, h)], fill=(70, 80, 70))
    for a in range(int(math.ceil((heading - fov / 2) / 10) * 10), int(heading + fov / 2) + 1, 10):
        x = (a - (heading - fov / 2)) / fov * (w - 1)
        d.line((x, h - 12, x, h), fill=(255, 255, 255))
        d.text((x + 2, h - 24), f"{a % 360}°", fill=(255, 255, 255))
    for p in [p for p in peaks if p["visible"]][:8]:
        x = (p["offset_deg"] + fov / 2) / fov * (w - 1)
        y = (hi - p["elevation_deg"]) / (hi - lo) * (h - 1)
        d.line((x, y - 4, x, max(2, y - 18)), fill=(150, 0, 0))
        d.text((max(2, min(w - 120, x - 20)), max(2, y - 32)), p["name"][:22], fill=(120, 0, 0))
    return img


def horizon(lat: float, lon: float, heading_deg: float, fov_deg: float = 60) -> dict:
    """{path, camera_height_m, heading_deg, fov_deg, azimuths_deg, elevation_deg, peaks} for a camera at
    (lat, lon) looking towards heading_deg (0 = north, 90 = east) with a horizontal field of view fov_deg.
    path (relative to DATA_DIR) is a picture of the skyline with a degree scale and the visible peaks.
    elevation_deg: horizon elevation angle per azimuth; peaks: named peaks in view, visible ones first."""
    fov = max(10.0, min(float(fov_deg), 120.0))
    h0 = height(lat, lon, 12) + EYE_M
    azs = np.arange(heading_deg - fov / 2, heading_deg + fov / 2 + 1e-9, STEP_DEG)
    dists = _distances()
    elev = np.array([_ray(lat, lon, h0, a % 360, dists)[0] for a in azs])
    peaks = _peaks(lat, lon, h0, azs, elev, heading_deg % 360, fov)
    img = _draw(azs, elev, heading_deg, fov, peaks)
    ensure(OUT)
    name = f"{lat:.5f}_{lon:.5f}_{round(heading_deg) % 360}_{round(fov)}.png"
    buf = io.BytesIO()
    img.save(buf, "PNG")
    (OUT / name).write_bytes(buf.getvalue())
    return {"path": f"tiles/horizon/{name}", "camera_height_m": round(h0), "heading_deg": round(heading_deg % 360, 1),
            "fov_deg": fov, "azimuths_deg": [round(a % 360, 2) for a in azs[::4]],
            "elevation_deg": [round(float(e), 2) for e in elev[::4]], "peaks": peaks}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lat", type=float)
    ap.add_argument("lon", type=float)
    ap.add_argument("--heading", type=float, required=True)
    ap.add_argument("--fov", type=float, default=60)
    a = ap.parse_args()
    out = horizon(a.lat, a.lon, a.heading, a.fov)
    print(out["path"], out["camera_height_m"], [(p["name"], p["visible"]) for p in out["peaks"][:8]])


if __name__ == "__main__":
    main()
