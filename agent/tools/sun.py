"""Sun position for a place and a moment (NOAA solar position algorithm, about 0.1 degree; no library).

Used by the skyline tool: with the EXIF capture time the model knows where the sun stood, so the shadows
and the lit sides in the photo tell which way the camera looked. EXIF times are local Swiss time.
"""

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SWISS = ZoneInfo("Europe/Zurich")


def parse_exif(value: str | None) -> datetime | None:
    """'2008:05:03 10:21:00' (local Swiss time) -> aware UTC datetime, or None."""
    if not value:
        return None
    try:
        local = datetime.strptime(value.strip()[:19], "%Y:%m:%d %H:%M:%S").replace(tzinfo=SWISS)
    except ValueError:
        return None
    return local.astimezone(timezone.utc)


def position(lat: float, lon: float, when: datetime) -> tuple[float, float]:
    """(azimuth degrees clockwise from north, elevation degrees) of the sun."""
    when = when.astimezone(timezone.utc)
    jd = when.timestamp() / 86400 + 2440587.5
    t = (jd - 2451545.0) / 36525
    l0 = (280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    mr = math.radians(m)
    c = (math.sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t)) + math.sin(2 * mr) * (0.019993 - 0.000101 * t)
         + math.sin(3 * mr) * 0.000289)
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    eps0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    eps = math.radians(eps0 + 0.00256 * math.cos(math.radians(omega)))
    decl = math.asin(math.sin(eps) * math.sin(math.radians(app_long)))
    y = math.tan(eps / 2) ** 2
    l0r = math.radians(l0)
    eq_time = 4 * math.degrees(y * math.sin(2 * l0r) - 2 * e * math.sin(mr) + 4 * e * y * math.sin(mr) * math.cos(2 * l0r)
                               - 0.5 * y * y * math.sin(4 * l0r) - 1.25 * e * e * math.sin(2 * mr))
    minutes = when.hour * 60 + when.minute + when.second / 60
    hour_angle = math.radians(((minutes + eq_time + 4 * lon) / 4) - 180)
    latr = math.radians(lat)
    cos_zen = math.sin(latr) * math.sin(decl) + math.cos(latr) * math.cos(decl) * math.cos(hour_angle)
    zen = math.acos(max(-1.0, min(1.0, cos_zen)))
    az = math.degrees(math.atan2(math.sin(hour_angle),
                                 math.cos(hour_angle) * math.sin(latr) - math.tan(decl) * math.cos(latr))) + 180
    return az % 360, 90 - math.degrees(zen)


def relative(sun_az: float, heading: float) -> str:
    """Where the sun stands as seen by a camera looking towards heading (German, for the model and trace)."""
    off = (sun_az - heading + 180) % 360 - 180
    if abs(off) <= 30:
        return "Sonne vor der Kamera (Gegenlicht, Schatten zur Kamera hin)"
    if abs(off) >= 150:
        return "Sonne im Rücken der Kamera (Vorderseiten beleuchtet, Schatten vom Betrachter weg)"
    side = "rechts" if off > 0 else "links"
    back = " hinten" if abs(off) > 90 else ""
    return f"Sonne von {side}{back} (Schatten fallen nach {'links' if off > 0 else 'rechts'})"
