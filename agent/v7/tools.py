"""Client tools for an attempt: zoom into the original, geo.admin search, the offline registers.

Every point a tool returns is remembered in `Session.points`, so an answer's subject point can be checked
against what the tools really said (Claude never types coordinates of its own).
"""

import json
import re
from pathlib import Path

import data_pipeline as dp
import httpx
from data_pipeline import geo

from .common import IMAGE_PX, V7_DIR, block, jpeg, key

SEARCH_URL = "https://api3.geo.admin.ch/rest/services/ech/SearchServer"
SEARCH_CACHE = V7_DIR / "geosearch"
NOT_PLACES = {"Berg", "See/Gewässer", "Fluss", "Bach", "Natur", "Ort", "Areal", "Park"}

SPECS = [
    {"name": "zoom", "description": "A part of the original photo at full resolution, to read small text "
                                    "(signs, house names, posters) or see details. Box as fractions 0..1 of width/height.",
     "input_schema": {"type": "object", "properties": {
         "x0": {"type": "number"}, "y0": {"type": "number"}, "x1": {"type": "number"}, "y1": {"type": "number"}},
         "required": ["x0", "y0", "x1", "y1"]}},
    {"name": "find_building", "description": "Named buildings and places in Kanton Schwyz by name (OSM, GWR building "
                                             "register, KGS heritage inventory), with official address, Gemeinde and point. "
                                             "Use a distinctive part of the name ('Acherhof', 'Waldstätterhof').",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"},
                                                       "gemeinde": {"type": ["string", "null"]}}, "required": ["name"]}},
    {"name": "find_address", "description": "Official entrances (GWR) on a street, optionally a house number and Gemeinde.",
     "input_schema": {"type": "object", "properties": {"street": {"type": "string"}, "number": {"type": ["string", "null"]},
                                                       "gemeinde": {"type": ["string", "null"]}}, "required": ["street"]}},
    {"name": "buildings_near", "description": "Named buildings within radius_m of a point (proper names only), nearest first.",
     "input_schema": {"type": "object", "properties": {"lat": {"type": "number"}, "lon": {"type": "number"},
                                                       "radius_m": {"type": "integer"}}, "required": ["lat", "lon"]}},
    {"name": "place_search", "description": "swisstopo search (geo.admin.ch): place names of swissNAMES3D (hamlets, "
                                            "alps, mountains, lakes, stops), addresses and Gemeinden anywhere in Switzerland.",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "address_at", "description": "What is at a point: Ortschaft, Gemeinde and the official addresses within 80 m.",
     "input_schema": {"type": "object", "properties": {"lat": {"type": "number"}, "lon": {"type": "number"}},
                      "required": ["lat", "lon"]}},
]


class Session:
    """Tool state of one attempt: the original photo and every point the tools returned."""

    def __init__(self, original: Path):
        self.original = original
        self.points: list[dict] = []  # {lat, lon, label, source, building?, address?, municipality?}
        self.calls: list[dict] = []

    def run(self, name: str, args: dict) -> list[dict] | str:
        """Tool result content (text JSON, or an image for zoom). Errors come back as text, never raise."""
        try:
            out = getattr(self, f"_{name}")(**args)
        except Exception as e:  # a bad argument must not end the attempt
            out = f"Fehler: {e}"
        self.calls.append({"tool": name, "input": args,
                           "output": out if isinstance(out, str) else f"{len(out)} Treffer"})
        if name == "zoom" and not isinstance(out, str):
            return out
        return json.dumps(out, ensure_ascii=False) if not isinstance(out, str) else out

    def _keep(self, rows: list[dict], source: str) -> list[dict]:
        for r in rows:
            if r.get("lat") is not None:
                r["point_id"] = f"{source}:{len(self.points)}"
                self.points.append({**r, "source": source})
        return rows

    def _zoom(self, x0, y0, x1, y1):
        return [block(jpeg(self.original, IMAGE_PX, 90, (x0, y0, x1, y1)))]

    def _find_building(self, name, gemeinde=None):
        hits = [h for h in dp.find_building(name, gemeinde or None, limit=8)]
        rows = [{"name": h["name"], "kind": h["kind"], "address": h["address"], "ortschaft": h["ortschaft"],
                 "gemeinde": h["municipality"], "lat": h["lat"], "lon": h["lon"], "register": h["source"],
                 "is_place": h["kind"] not in NOT_PLACES} for h in hits]
        return self._keep(rows, "building") or "Kein Treffer. Anderen Namensteil oder ohne Gemeinde versuchen."

    def _find_address(self, street, number=None, gemeinde=None):
        hits = dp.find_address(street, number or None, gemeinde or None, limit=6)
        rows = [{"address": h["address"], "ortschaft": h["ortschaft"], "gemeinde": h["municipality"],
                 "building": h.get("building"), "lat": h["lat"], "lon": h["lon"]} for h in hits]
        return self._keep(rows, "address") or "Keine solche Adresse im Register."

    def _buildings_near(self, lat, lon, radius_m=300):
        from data_pipeline.places import named_buildings
        hits = [b for b in named_buildings(lat=lat, lon=lon, radius_m=min(int(radius_m), 2000), limit=40)
                if not b.get("generic")][:15]
        rows = [{"name": b["name"], "kind": b["kind"], "address": b.get("address"), "gemeinde": b.get("municipality"),
                 "distance_m": b["distance_m"], "lat": b["lat"], "lon": b["lon"]} for b in hits]
        return self._keep(rows, "building") or "Keine benannten Gebäude in der Nähe."

    def _place_search(self, text):
        SEARCH_CACHE.mkdir(parents=True, exist_ok=True)
        p = SEARCH_CACHE / f"{key(text.casefold())}.json"
        if p.exists():
            res = json.loads(p.read_text())["r"]
        else:
            r = httpx.get(SEARCH_URL, params={"searchText": text, "type": "locations", "sr": "4326", "limit": 12,
                                              "origins": "gazetteer,address,gg25,zipcode"}, timeout=30)
            r.raise_for_status()
            res = r.json().get("results", [])
            p.write_text(json.dumps({"q": text, "r": res}, ensure_ascii=False))
        rows = []
        for x in res:
            a = x.get("attrs") or {}
            if a.get("lat") is None:
                continue
            m = geo.municipality_at(a["lat"], a["lon"])
            rows.append({"label": re.sub(r"<[^>]+>", "", a.get("label") or ""), "origin": a.get("origin"),
                         "lat": round(a["lat"], 6), "lon": round(a["lon"], 6),
                         "gemeinde_sz": (m or {}).get("name")})
        return self._keep(rows, "search") or "Kein Treffer."

    def _address_at(self, lat, lon):
        a = dp.address_at(lat, lon, 80, limit=5)
        return {"ortschaft": a.get("ortschaft"), "gemeinde": a.get("municipality"), "in_canton": a.get("in_canton"),
                "addresses": [{"address": x["address"], "building": x.get("building"), "distance_m": x["distance_m"]}
                              for x in a.get("addresses") or []]}

    def point(self, point_id: str | None) -> dict | None:
        """The tool point an answer refers to, or None."""
        if not point_id:
            return None
        return next((p for p in self.points if p.get("point_id") == point_id), None)
