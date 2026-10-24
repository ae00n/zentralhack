"""An attempt's answer -> a candidate place, with every name taken from the registers at the subject point.

The point is the subject's register entry (building, address, search hit), never a reference photo's camera
position. Gemeinde = the polygon at that point; Ortschaft = an entrance of the same Gemeinde nearby.
"""

import re

import data_pipeline as dp
from data_pipeline import geo

from .common import dist_m, gem
from .tools import NOT_PLACES

RADIUS = {"building": 50, "address": 30, "search": 300, "gemeinde": 3000}


def official_locality(name: str | None) -> str | None:
    """Claude's Ortschaft in the official PLZ spelling ("Seewen" -> "Seewen SZ"), else None."""
    from data_pipeline.qc import _norm, official_names
    if not name:
        return None
    ort = official_names()["locality"]
    return ort.get(_norm(name)) or ort.get(re.sub(r"\s+sz$", "", _norm(name)))


def _center(municipality: str | None) -> dict | None:
    g = next((g for g in dp.gazetteer() if gem(g["name"]) == gem(municipality)), None) if municipality else None
    return {"lat": g["lat"], "lon": g["lon"]} if g else None


def _subject(a: dict, point: dict | None) -> tuple[dict | None, str]:
    """(point, anchor): the attempt's chosen tool point, else its building or street looked up again."""
    if point and point.get("lat") is not None:
        if point["source"] == "building" and point.get("kind") in NOT_PLACES:
            return point, "search"  # a summit or lake: a place, not a building
        return point, point["source"]
    if a.get("building"):
        hits = [h for h in dp.find_building(a["building"], a.get("municipality")) if h["kind"] not in NOT_PLACES]
        if hits and (a.get("municipality") or len({h["municipality"] for h in hits}) == 1):
            h = hits[0]
            return {"lat": h["lat"], "lon": h["lon"], "name": h["name"], "address": h["address"]}, "building"
    if a.get("street") and a.get("municipality"):
        m = re.match(r"^(.*?)\s*(\d+\w*)?$", a["street"].strip())
        hits = dp.find_address(m.group(1), m.group(2), a["municipality"])
        if hits:
            h = hits[0]
            exact = bool(m.group(2) and (h["number"] or "").startswith(m.group(2)))
            return {"lat": h["lat"], "lon": h["lon"], "address": h["address"]}, "address" if exact else "search"
    c = _center(a.get("municipality"))
    return (c, "gemeinde") if c else (None, "none")


def candidate(attempt: dict) -> dict | None:
    """{lat, lon, radius_m, anchor, municipality, locality, building, street, outside, attempt} or None."""
    a = attempt.get("answer") or {}
    if not a:
        return None
    p, anchor = _subject(a, attempt.get("point"))
    out = {"anchor": anchor, "attempt": attempt["variant"], "outside": a.get("outside_canton"),
           "claude_municipality": a.get("municipality"), "landmarks": a.get("landmarks") or [],
           "municipality": None, "locality": None, "building": None, "street": None, "lat": None, "lon": None,
           "radius_m": None}
    if p is None:
        return out if a.get("outside_canton") else None
    mun = geo.municipality_at(p["lat"], p["lon"])
    if mun is None:  # outside the canton
        out["outside"] = out["outside"] or "ausserhalb Kanton Schwyz"
        return {**out, "lat": p["lat"], "lon": p["lon"], "radius_m": RADIUS.get(anchor, 300)}
    at = dp.address_at(p["lat"], p["lon"], 40, limit=3)
    out.update(lat=p["lat"], lon=p["lon"], radius_m=RADIUS.get(anchor, 300), municipality=mun["name"])
    out["locality"] = at.get("ortschaft") if anchor != "gemeinde" else official_locality(a.get("locality"))
    if anchor == "building":
        out["building"] = p.get("name")
        out["street"] = p.get("address") or next((x["address"] for x in at.get("addresses") or []), None)
    elif anchor == "address":
        out["street"] = p.get("address")
        out["building"] = p.get("building") or _named(a, p)
    else:
        out["building"] = _named(a, p) if anchor != "gemeinde" else None
    return out


def _named(a: dict, p: dict) -> str | None:
    """Claude's building name when the register has it within 150 m of the point."""
    if not a.get("building"):
        return None
    for h in dp.find_building(a["building"], a.get("municipality")):
        if h["kind"] not in NOT_PLACES and dist_m(h, p) <= 150:
            return h["name"]
    return None


def same_place(c1: dict, c2: dict, m: float = 150) -> bool:
    if c1.get("lat") is None or c2.get("lat") is None:
        return False
    return dist_m(c1, c2) <= m
