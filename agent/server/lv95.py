"""WGS84 to Swiss LV95 (swisstopo approximate formulas, about 1 m accuracy)."""


def wgs84_to_lv95(lat: float, lon: float) -> tuple[float, float]:
    """(E, N) in metres."""
    p = (lat * 3600 - 169028.66) / 10000
    l = (lon * 3600 - 26782.5) / 10000
    e = 2600072.37 + 211455.93 * l - 10938.51 * l * p - 0.36 * l * p ** 2 - 44.54 * l ** 3
    n = (1200147.07 + 308807.95 * p + 3745.25 * l ** 2 + 76.63 * p ** 2
         - 194.56 * l ** 2 * p + 119.79 * p ** 3)
    return e, n
