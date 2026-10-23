"""WGS84 to Swiss LV95 (swisstopo approximate formulas, about 1 m accuracy)."""


def wgs84_to_lv95(lat: float, lon: float) -> tuple[float, float]:
    """(E, N) in metres."""
    p = (lat * 3600 - 169028.66) / 10000
    l = (lon * 3600 - 26782.5) / 10000
    e = 2600072.37 + 211455.93 * l - 10938.51 * l * p - 0.36 * l * p ** 2 - 44.54 * l ** 3
    n = (1200147.07 + 308807.95 * p + 3745.25 * l ** 2 + 76.63 * p ** 2
         - 194.56 * l ** 2 * p + 119.79 * p ** 3)
    return e, n


def lv95_to_wgs84(e: float, n: float) -> tuple[float, float]:
    """(lat, lon) in degrees, the inverse swisstopo approximate formulas."""
    y, x = (e - 2600000) / 1e6, (n - 1200000) / 1e6
    lon = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y ** 3
    lat = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x ** 3
    return lat * 100 / 36, lon * 100 / 36
