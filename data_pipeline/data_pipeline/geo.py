"""Point-in-municipality lookup for Kanton Schwyz, done locally.

The 30 municipality polygons (WGS84) are fetched once from swisstopo
(ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill, timeInstant=2025) and cached in
data/gazetteer/gemeinden_polygons.json, so tagging thousands of photos costs no requests.
"""

import json

from .http import PoliteClient
from .paths import GAZETTEER, RAW, ensure

URL = (
    "https://api3.geo.admin.ch/rest/services/all/MapServer/identify?geometryType=esriGeometryEnvelope"
    "&geometry=8.30,46.85,9.10,47.30&sr=4326&layers=all:ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill"
    "&tolerance=0&mapExtent=8.30,46.85,9.10,47.30&imageDisplay=1000,800,96&returnGeometry=true"
    "&geometryFormat=geojson&limit=200&timeInstant=2025"
)
POLY_FILE = GAZETTEER / "gemeinden_polygons.json"

_polys: list[dict] | None = None


def polygons() -> list[dict]:
    """[{name, bfs_nr, bbox, rings}] where rings is a list of [(lon, lat), ...] (outer and holes)."""
    global _polys
    if _polys is not None:
        return _polys
    if not POLY_FILE.exists():
        ensure(GAZETTEER, RAW / "geoadmin")
        res = json.loads(PoliteClient(cache_dir=RAW / "geoadmin").get(URL, suffix=".json"))["results"]
        out = []
        for r in res:
            p = r["properties"]
            if not 1300 <= p.get("gde_nr", 0) < 1400:
                continue
            g = r["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            rings = [ring for poly in polys for ring in poly]
            lons = [c[0] for ring in rings for c in ring]
            lats = [c[1] for ring in rings for c in ring]
            out.append({"name": p["gemname"], "bfs_nr": p["gde_nr"],
                        "bbox": [min(lons), min(lats), max(lons), max(lats)], "rings": rings})
        POLY_FILE.write_text(json.dumps(out))
    _polys = json.loads(POLY_FILE.read_text())
    return _polys


def _inside(lon: float, lat: float, rings: list) -> bool:
    # even-odd rule over all rings handles holes
    inside = False
    for ring in rings:
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
    return inside


def municipality_at(lat: float | None, lon: float | None) -> dict | None:
    """{name, bfs_nr} of the Schwyz municipality containing the point, or None if outside the canton."""
    if lat is None or lon is None:
        return None
    for p in polygons():
        x0, y0, x1, y1 = p["bbox"]
        if x0 <= lon <= x1 and y0 <= lat <= y1 and _inside(lon, lat, p["rings"]):
            return {"name": p["name"], "bfs_nr": p["bfs_nr"]}
    return None


def canton_wkt(max_points: int = 150) -> str:
    """Rough WKT outline of the canton (convex-ish hull of all municipality outer points), for API filters."""
    pts = [tuple(c) for p in polygons() for ring in p["rings"] for c in ring]
    pts = sorted(set((round(x, 4), round(y, 4)) for x, y in pts))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    step = max(1, len(hull) // max_points)
    hull = hull[::step]
    hull.append(hull[0])
    return "POLYGON((" + ",".join(f"{x} {y}" for x, y in hull) + "))"
