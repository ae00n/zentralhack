"""Check a candidate against photos taken there: Mapillary and Commons within 200 m, LightGlue vs the photo.

Pass: at least PASS_INLIERS geometrically consistent points (below ~100 a match is noise on these photos).
A precomputed strong match within 300 m of the candidate counts as a pass too (it was checked the same way).
"""

import math

import data_pipeline as dp

from ..config import DATA_DIR
from .common import dist_m

PASS_INLIERS = 100
WEAK_INLIERS = 60
RADIUS_M = 200
N_PHOTOS = 8


def _bearing(a: dict, b: dict) -> float:
    y = math.sin(math.radians(b["lon"] - a["lon"])) * math.cos(math.radians(b["lat"]))
    x = (math.cos(math.radians(a["lat"])) * math.sin(math.radians(b["lat"]))
         - math.sin(math.radians(a["lat"])) * math.cos(math.radians(b["lat"])) * math.cos(math.radians(b["lon"] - a["lon"])))
    return math.degrees(math.atan2(y, x)) % 360


def nearby(c: dict) -> list[dict]:
    """Photos within RADIUS_M, the ones looking at the candidate first (camera turned towards it within 45
    degrees, 10 m or more away); photos without a heading (Commons) count as looking at it."""
    def score(p: dict) -> float:
        if p["heading_deg"] is None:
            return 0.5 + p["distance_m"] / RADIUS_M
        r = dp.get_record(p["id"])["location"]
        off = abs((p["heading_deg"] - _bearing(r, c) + 180) % 360 - 180)
        if off > 45 or p["distance_m"] < 10:
            return 9.0
        return off / 45 + p["distance_m"] / RADIUS_M
    pool = dp.photos_near(c["lat"], c["lon"], RADIUS_M, max_precision_m=100, sources=["mapillary", "commons"], limit=300)
    return [p for p in sorted(pool, key=score) if score(p) < 9][:N_PHOTOS]


def check(photo_path: str, c: dict, strong: list[dict]) -> dict:
    """{best_inliers, pass, weak, photos: [{id, title, distance_m, inliers, image_path}]}."""
    if c.get("lat") is None:
        return {"best_inliers": 0, "pass": False, "weak": False, "photos": [], "by_match": None}
    from data_pipeline.verify import verify
    photos = nearby(c)
    res = verify(photo_path, [DATA_DIR / p["image_path"] for p in photos]) if photos else []
    rows = [{"id": p["id"], "title": p.get("title"), "distance_m": p["distance_m"], "inliers": r["inliers"],
             "image_path": p["image_path"]} for p, r in zip(photos, res)]
    rows.sort(key=lambda r: -r["inliers"])
    by_match = next((h for h in strong if dist_m(h, c) <= 300), None)
    best = max([r["inliers"] for r in rows] + [(by_match or {}).get("inliers") or 0])
    return {"best_inliers": best, "pass": best >= PASS_INLIERS, "weak": WEAK_INLIERS <= best < PASS_INLIERS,
            "photos": rows[:4], "by_match": by_match and {k: by_match[k] for k in ("id", "inliers", "title")}}
