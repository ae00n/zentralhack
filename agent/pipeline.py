"""v5: a fixed retrieval pipeline instead of a free tool loop (plan: plan.vatra.sh/v4o20bssdwli).

    1. retrieve   MegaLoc nearest neighbours over every reference collection
    2. verify     ALIKED + LightGlue inlier counts on the top hits, verified hits clustered by place
    3. decide     only when no place verifies: one Claude call (agent.decide), not in this module
    4. names      winner coordinate -> Ortschaft, Gemeinde, street, building from the official registers
    5. score      agent.calibration turns the match features into a probability per field

Stages 1, 2 and 4 make no model call and give the same answer on every run.

    python -m agent.pipeline <photo_id> [<photo_id> ...]
"""

import json
import logging
import math
import re
import sys
from collections import Counter
from functools import lru_cache

import data_pipeline as dp

log = logging.getLogger(__name__)

K_VERIFY = 10       # hits that get the geometric check (about 1.5 s each on CPU)
K_RETRIEVE = 20     # hits used for the agreement feature
MIN_INLIERS = 30    # data_pipeline.verify: >= 30 inliers share the place 84% of the time, >= 50: 96%
CLUSTER_M = 300     # verified hits closer than this count as one place
PRECISE_M = 500     # refs with a coarser location (municipality-level cards) only vote for the Gemeinde
BUILDING_KINDS = None  # every named place counts for the building field


def set_threads(n: int) -> None:
    """For worker processes: load the matcher, then cap torch threads (data_pipeline.verify takes up
    to 16, which oversubscribes the CPU when several workers run)."""
    import torch
    from data_pipeline import verify

    verify._models()
    torch.set_num_threads(n)


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _loc(rec: dict) -> tuple[float, float, float] | None:
    """(lat, lon, precision_m) of a reference, or None."""
    loc = rec.get("location") or {}
    if loc.get("lat") is None:
        return None
    return loc["lat"], loc["lon"], float(loc.get("precision_m") or 5000)


def _hit(h: dict) -> dict:
    rec = h["record"]
    loc = _loc(rec)
    return {
        "id": rec["id"], "source": rec["source"], "score": round(h["score"], 4),
        "inliers": h.get("inliers"), "verified": bool(h.get("inliers") is not None and h["inliers"] >= MIN_INLIERS),
        "lat": loc[0] if loc else None, "lon": loc[1] if loc else None, "precision_m": loc[2] if loc else None,
        "municipality": rec.get("municipality"), "title": rec.get("title"), "places": rec.get("places") or [],
        "year": (rec.get("date") or {}).get("year_from"), "image": (rec.get("image") or {}).get("path"),
    }


def retrieve(image_path: str, exclude_ids: list[str] = ()) -> dict:
    """Stages 1 and 2: {hits (top K_RETRIEVE, verified first), verified (only those)}."""
    checked = dp.similar_images(image_path, k=K_VERIFY, verify=True, exclude_ids=list(exclude_ids))
    wide = dp.similar_images(image_path, k=K_RETRIEVE, exclude_ids=list(exclude_ids))
    seen = {h["id"] for h in checked}
    hits = [_hit(h) for h in checked] + [_hit(h) for h in wide if h["id"] not in seen]
    return {"hits": hits, "verified": [h for h in hits if h["verified"]]}


def clusters(verified: list[dict]) -> list[dict]:
    """Verified hits with a precise location, grouped by place; strongest group first.

    Each group: {lat, lon, inliers (sum), members, best (the hit with most inliers)}.
    The group's point is its best hit's location, not a mean (one good pose beats an average)."""
    groups: list[dict] = []
    for h in sorted((h for h in verified if h["lat"] is not None and h["precision_m"] <= PRECISE_M),
                    key=lambda h: -h["inliers"]):
        g = next((g for g in groups if haversine_m((g["lat"], g["lon"]), (h["lat"], h["lon"])) <= CLUSTER_M), None)
        if g is None:
            groups.append({"lat": h["lat"], "lon": h["lon"], "inliers": h["inliers"], "members": [h], "best": h})
        else:
            g["inliers"] += h["inliers"]
            g["members"].append(h)
    return sorted(groups, key=lambda g: -g["inliers"])


def _municipality_vote(verified: list[dict]) -> tuple[str | None, int]:
    """The Gemeinde most verified hits name (by summed inliers), for refs placed only at municipality level."""
    votes: dict[str, int] = {}
    for h in verified:
        if h["municipality"]:
            votes[h["municipality"]] = votes.get(h["municipality"], 0) + h["inliers"]
    if not votes:
        return None, 0
    name = max(votes, key=votes.get)
    return name, votes[name]


def features(r: dict, groups: list[dict]) -> dict:
    """Numbers the confidence model is fitted on (agent.calibration). All cheap, all deterministic."""
    v = r["verified"]
    top = groups[0] if groups else None
    total = sum(h["inliers"] for h in v) or 1
    agree = 0
    if top:
        agree = sum(1 for h in r["hits"][:10] if h["lat"] is not None and h["precision_m"] <= PRECISE_M
                    and haversine_m((top["lat"], top["lon"]), (h["lat"], h["lon"])) <= 1000)
    scores = sorted((h["score"] for h in r["hits"]), reverse=True)
    return {
        "top_inliers": top["best"]["inliers"] if top else 0,
        "group_inliers": top["inliers"] if top else 0,
        "group_share": round(top["inliers"] / total, 3) if top else 0.0,
        "n_verified": len(v),
        "n_groups": len(groups),
        "agree10": agree,
        "top_score": scores[0] if scores else 0.0,
        "score_gap": round(scores[0] - scores[1], 4) if len(scores) > 1 else 0.0,
    }


_GENERIC = re.compile(r"\b(in|of|from|by|switzerland|schweiz|kanton|canton|photographs|images|files|views?|"
                      r"taken|uploaded|quality|cc-by|license)\b", re.I)


@lru_cache(maxsize=1)
def _generic_names() -> set[str]:
    """Building names used 3+ times in the gazetteer ("Einfamilienhaus", "Garage" from the GWR): types, not names."""
    counts = Counter(b["name"].lower() for b in dp.named_buildings(limit=10**6))
    return {n for n, c in counts.items() if c >= 3}


def _building(lat: float, lon: float, refs: list[dict]) -> tuple[str | None, str | None]:
    """(name, reason): a named building near the point whose name the matching refs mention,
    else the nearest named building within 60 m. None when nothing fits."""
    near = dp.named_buildings(lat=lat, lon=lon, radius_m=400, kinds=BUILDING_KINDS, limit=30)
    generic = _generic_names()
    near = [b for b in near if b.get("kind") not in ("Ort", "Berg", "See/Gewässer", "Fluss")
            and b["name"].lower() not in generic]
    text = " ".join([*(h["title"] or "" for h in refs), *(p for h in refs for p in h["places"])]).lower()
    for b in near:
        names = [b["name"], *b.get("alt_names", [])]
        if any(len(n) >= 5 and n.lower() in text for n in names):
            return b["name"], f"Referenzfoto nennt {b['name']} ({b['distance_m']} m vom Punkt)"
    close = [b for b in near if b["distance_m"] <= 60]
    if close:
        return close[0]["name"], f"nächstes benanntes Gebäude, {close[0]['distance_m']} m vom Punkt"
    return None, None


def names(lat: float, lon: float, refs: list[dict] = ()) -> dict:
    """Stage 4: {locality, municipality, canton, in_canton, street, egid, building, building_reason}."""
    a = dp.address_lookup(lat, lon, radius_m=150, limit=1)
    addr = (a.get("addresses") or [None])[0] or {}
    building, why = _building(lat, lon, list(refs))
    return {
        "locality": a.get("ortschaft"), "municipality": a.get("municipality"), "canton": a.get("canton"),
        "in_canton": a.get("in_canton"), "street": addr.get("street"), "egid": addr.get("egid"),
        "address": addr.get("address"), "address_distance_m": addr.get("distance_m"),
        "building": building, "building_reason": why,
    }


def locate(image_path: str, exclude_ids: list[str] = ()) -> dict:
    """Stages 1, 2, 4 for one image. {point, names, groups (top 3), hits, features, municipality_vote, decided_by}.

    decided_by: "match" (a verified group with a location), "municipality" (only coarse refs verified;
    names.municipality comes from their vote) or None (nothing verified: stage 3 has to decide)."""
    r = retrieve(image_path, exclude_ids)
    groups = clusters(r["verified"])
    vote, vote_inliers = _municipality_vote(r["verified"])
    out = {"hits": r["hits"], "groups": [{k: g[k] for k in ("lat", "lon", "inliers")} | {
        "members": [m["id"] for m in g["members"]]} for g in groups[:3]],
        "features": features(r, groups), "municipality_vote": vote, "municipality_vote_inliers": vote_inliers,
        "point": None, "names": None, "decided_by": None}
    if groups:
        g = groups[0]
        out["point"] = {"lat": g["lat"], "lon": g["lon"], "radius_m": g["best"]["precision_m"]}
        out["names"] = names(g["lat"], g["lon"], g["members"])
        out["decided_by"] = "match"
    elif vote:
        out["names"] = {"locality": None, "municipality": vote, "street": None, "building": None}
        out["decided_by"] = "municipality"
    return out


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    for pid in sys.argv[1:]:
        rec = dp.get_record(pid)
        path = str(dp.image_file(rec))
        res = locate(path, exclude_ids=[pid])
        res["hits"] = [{k: h[k] for k in ("id", "score", "inliers", "municipality", "title")} for h in res["hits"][:6]]
        print(json.dumps({"photo_id": pid, **res}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
