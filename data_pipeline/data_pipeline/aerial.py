"""Aerial photo around a point: what a candidate building looks like from above (roof, wings, parking).

    from data_pipeline import aerial_image
    aerial_image(47.0216, 8.6573, radius_m=80, year=2005)
    python -m data_pipeline.aerial 47.0216 8.6573 --radius 80 --year 2005

swisstopo SWISSIMAGE over WMTS (free, no key). With a year, the time series layer
`ch.swisstopo.swissimage-product` returns the latest flight up to that year (flights since 1987 in this
area, about every 3 years), so a 2005 photo is compared with the 2005 state, including buildings that no
longer stand. Without a year: the current image.

The image is north up, centred on the point, with a small red cross on the point. Tiles are cached under
data/tiles/<layer>/<time>/<z>/<x>/<y>.jpeg (same layout as tiles.py), the stitched image under
data/tiles/aerial/. Repeated calls cost no requests; offline, cached areas still work.
"""

import argparse
import io
import math

from PIL import Image, ImageDraw

from .http import PoliteClient
from .paths import DATA_DIR, ensure

WMTS = "https://wmts.geo.admin.ch/1.0.0"
CURRENT, SERIES = "ch.swisstopo.swissimage", "ch.swisstopo.swissimage-product"
TILES = DATA_DIR / "tiles"
OUT = TILES / "aerial"
MAX_RADIUS_M = 400
TILE = 256

_client: PoliteClient | None = None


def _http() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient(min_interval=0.1)
    return _client


def _zoom(radius_m: float, lat: float) -> int:
    """Highest zoom (max 19, about 0.2 m/px) at which the square fits in about 1024 px."""
    for z in range(19, 13, -1):
        mpp = 156543.03 * math.cos(math.radians(lat)) / 2 ** z
        if 2 * radius_m / mpp <= 1024:
            return z
    return 14


def _tile(layer: str, time: str, z: int, x: int, y: int) -> Image.Image:
    path = TILES / layer / time / str(z) / str(x) / f"{y}.jpeg"
    if not path.exists():
        data = _http().get(f"{WMTS}/{layer}/default/{time}/3857/{z}/{x}/{y}.jpeg", cache=False)
        ensure(path.parent)
        path.write_bytes(data)
    return Image.open(path).convert("RGB")


def aerial_image(lat: float, lon: float, radius_m: float = 80, year: int | None = None) -> dict:
    """{path, year, meters_per_pixel, width, height, radius_m} for a north-up aerial photo of the square
    2 * radius_m wide around the point (red cross = the point). path is relative to DATA_DIR, like
    PhotoRecord.image.path. year: the state as of that year (latest flight up to it), else current."""
    radius_m = max(20.0, min(float(radius_m), MAX_RADIUS_M))
    layer, time = (SERIES, str(int(year))) if year else (CURRENT, "current")
    z = _zoom(radius_m, lat)
    n = 2 ** z
    fx = (lon + 180) / 360 * n * TILE
    fy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * TILE
    mpp = 156543.03 * math.cos(math.radians(lat)) / n
    half = radius_m / mpp
    x0, y0, x1, y1 = fx - half, fy - half, fx + half, fy + half
    tx0, ty0, tx1, ty1 = int(x0 // TILE), int(y0 // TILE), int(x1 // TILE), int(y1 // TILE)
    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            canvas.paste(_tile(layer, time, z, tx, ty), ((tx - tx0) * TILE, (ty - ty0) * TILE))
    img = canvas.crop((round(x0 - tx0 * TILE), round(y0 - ty0 * TILE), round(x1 - tx0 * TILE), round(y1 - ty0 * TILE)))
    c, s = img.width / 2, max(6, img.width // 60)
    d = ImageDraw.Draw(img)
    d.line((c - s, c, c + s, c), fill=(255, 0, 0), width=2)
    d.line((c, c - s, c, c + s), fill=(255, 0, 0), width=2)
    name = f"{lat:.5f}_{lon:.5f}_{int(radius_m)}_{time}.jpg"
    ensure(OUT)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    (OUT / name).write_bytes(buf.getvalue())
    return {"path": f"tiles/aerial/{name}", "year": int(year) if year else None, "meters_per_pixel": round(mpp, 3),
            "width": img.width, "height": img.height, "radius_m": radius_m}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lat", type=float)
    ap.add_argument("lon", type=float)
    ap.add_argument("--radius", type=float, default=80)
    ap.add_argument("--year", type=int)
    a = ap.parse_args()
    print(aerial_image(a.lat, a.lon, a.radius, a.year))


if __name__ == "__main__":
    main()
