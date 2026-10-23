"""Reverse geocoding and named buildings for the challenge fields Ortschaft, Gemeinde, Gebaeude, Strasse.

    from data_pipeline import address_lookup, named_buildings

address_lookup: swisstopo identify (api3.geo.admin.ch, no key) on three layers:
- ch.swisstopo-vd.ortschaftenverzeichnis_plz: the official Ortschaft (PLZ locality) at the point
- ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill (timeInstant 2025): the political municipality
- ch.swisstopo.amtliches-gebaeudeadressverzeichnis: official building addresses near the point
Responses are cached on disk (data/raw/geoadmin/places), so repeated calls cost no requests.

named_buildings: named OSM features in Kanton Schwyz (churches, hotels, schools, stations, care homes,
huts, lakes, peaks ...), downloaded once with Overpass, plus the named buildings of the federal building
register GWR (data/raw/gwr/data.sqlite from https://public.madd.bfs.admin.ch/sz.zip: building name GBEZ,
class GKLAS, year built, official entrance address). Both go into data/gazetteer/buildings.json
(`python -m data_pipeline.places build`). Offline after that. A GWR building already in OSM (same
name within 60 m) is not added twice. Every item has `source` "osm" or "gwr".
"""

import argparse
import json
import math
import re
import unicodedata
from functools import lru_cache

from .http import PoliteClient
from .paths import GAZETTEER, RAW, ensure

IDENTIFY = "https://api3.geo.admin.ch/rest/services/api/MapServer/identify"
ADDR_LAYER = "ch.swisstopo.amtliches-gebaeudeadressverzeichnis"
ORT_LAYER = "ch.swisstopo-vd.ortschaftenverzeichnis_plz"
GEM_LAYER = "ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill"
BUILDINGS_FILE = GAZETTEER / "buildings.json"
OSM_FILE = RAW / "osm" / "schwyz_named.json"
GWR_FILE = RAW / "gwr" / "data.sqlite"
GWR_URL = "https://api3.geo.admin.ch/rest/services/ech/MapServer/ch.bfs.gebaeude_wohnungs_register/{}_0"
# GWR building class (GKLAS) -> the kind labels of the OSM side
GWR_KINDS = {1130: "Soziale Einrichtung", 1211: "Hotel", 1212: "Hotel", 1220: "Büro/Verwaltung", 1230: "Geschäft",
             1231: "Restaurant", 1241: "Bauwerk", 1261: "Freizeit", 1262: "Museum", 1263: "Schule", 1264: "Spital",
             1265: "Sportanlage", 1272: "Kirche/Kapelle", 1275: "Soziale Einrichtung"}
NOT_A_BUILDING = {"Brücke", "Bauwerk", "Station", "Bergbahnstation", "Schiffstation", "Hafen", "Bach",
                  "Natur", "Park", "Areal", "Ort"}  # mountains and lakes asked by name keep their rank
CARE = re.compile(r"alters|pflege|senior|betagt", re.I)
ADDRESS_LIKE = re.compile(r"^[^,]+, ?\d")  # "Acher, 1, 6442, 0": an address in the name field, not a name

_client: PoliteClient | None = None


def _http() -> PoliteClient:
    global _client
    if _client is None:
        ensure(RAW / "geoadmin" / "places")
        _client = PoliteClient(min_interval=0.3, cache_dir=RAW / "geoadmin" / "places")
    return _client


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _identify(lat: float, lon: float, layer: str, radius_m: int = 0, extra: str = "") -> list[dict]:
    dlat = radius_m / 111320
    dlon = radius_m / (111320 * math.cos(math.radians(lat)))
    if radius_m:
        geom = f"geometryType=esriGeometryEnvelope&geometry={lon - dlon:.6f},{lat - dlat:.6f},{lon + dlon:.6f},{lat + dlat:.6f}"
    else:
        geom = f"geometryType=esriGeometryPoint&geometry={lon:.6f},{lat:.6f}"
    url = (f"{IDENTIFY}?{geom}&sr=4326&layers=all:{layer}&tolerance=0"
           f"&mapExtent={lon - 0.01:.6f},{lat - 0.01:.6f},{lon + 0.01:.6f},{lat + 0.01:.6f}"
           f"&imageDisplay=1000,1000,96&returnGeometry=true&geometryFormat=geojson&limit=200{extra}")
    return json.loads(_http().get(url, suffix=".json")).get("results", [])


def address_lookup(lat: float, lon: float, radius_m: int = 100, limit: int = 10) -> dict:
    """What is at a point: {lat, lon, ortschaft, plz, municipality, bfs_nr, canton, in_canton, addresses, source}.

    addresses: official building addresses within radius_m (max 500), nearest first:
    [{street, number, address ("Grundstrasse 32"), zip, ortschaft, municipality, distance_m, lat, lon,
      egid, category}]. category is swisstopo's bdg_category (residential, non_residential, ...).
    Missing parts are null (e.g. outside Switzerland). Values are official names, ready for the export.
    """
    radius_m = max(1, min(int(radius_m), 500))
    ort = _identify(lat, lon, ORT_LAYER)
    gem = sorted(_identify(lat, lon, GEM_LAYER, extra="&timeInstant=2025"),  # lake areas ("kantonsgebiet") last
                 key=lambda f: (f.get("properties") or {}).get("objektart_lookup") not in ("gemeindegebiet", "politische_gemeinde"))
    o = (ort[0].get("properties") or {}) if ort else {}
    g = (gem[0].get("properties") or {}) if gem else {}
    addrs = []
    for f in _identify(lat, lon, ADDR_LAYER, radius_m):
        p = f.get("properties") or {}
        c = (f.get("geometry") or {}).get("coordinates") or [None, None]
        if c[0] is None or not p.get("stn_label"):
            continue
        d = _haversine_m(lat, lon, c[1], c[0])
        if d > radius_m:
            continue
        num = (p.get("adr_number") or "").strip()
        zip_label = p.get("zip_label") or ""
        addrs.append({
            "street": p["stn_label"], "number": num or None,
            "address": f"{p['stn_label']} {num}".strip(),
            "zip": zip_label[:4] or None, "ortschaft": zip_label[5:] or None,
            "municipality": p.get("com_name"), "distance_m": round(d),
            "lat": round(c[1], 6), "lon": round(c[0], 6),
            "egid": p.get("bdg_egid"), "category": p.get("bdg_category"),
        })
    addrs.sort(key=lambda a: a["distance_m"])
    return {
        "lat": lat, "lon": lon,
        "ortschaft": o.get("langtext"), "plz": o.get("plz"),
        "municipality": g.get("gemname"), "bfs_nr": g.get("gde_nr"), "canton": g.get("kanton"),
        "in_canton": g.get("kanton") == "SZ" if g else None,
        "addresses": addrs[:limit],
        "source": "swisstopo: Amtliches Ortschaftenverzeichnis, swissBOUNDARIES3D, Amtliches Gebäudeadressverzeichnis",
    }


# ---------------------------------------------------------------- named buildings (OSM)

NOISE = {"parking", "parking_space", "bicycle_parking", "motorcycle_parking", "bench", "waste_basket", "recycling",
         "vending_machine", "waste_disposal", "charging_station", "parking_entrance", "grit_bin", "hunting_stand"}
KEEP = ("building", "amenity", "tourism", "historic", "leisure", "man_made", "railway", "public_transport",
        "aerialway", "natural", "waterway", "place", "bridge", "office", "healthcare", "shop", "craft",
        "landuse", "highway")
# kind shown to the agent, first matching tag wins
KINDS = [
    ("amenity", "place_of_worship", "Kirche/Kapelle"), ("building", "church", "Kirche/Kapelle"),
    ("building", "chapel", "Kirche/Kapelle"), ("amenity", "monastery", "Kloster"), ("building", "monastery", "Kloster"),
    ("amenity", "townhall", "Rathaus"), ("amenity", "school", "Schule"), ("amenity", "college", "Schule"),
    ("amenity", "kindergarten", "Schule"), ("amenity", "nursing_home", "Alters-/Pflegeheim"),
    ("social_facility", "nursing_home", "Alters-/Pflegeheim"), ("social_facility", "assisted_living", "Alters-/Pflegeheim"),
    ("amenity", "social_facility", "Soziale Einrichtung"), ("amenity", "hospital", "Spital"),
    ("healthcare", None, "Gesundheit"), ("railway", "station", "Bahnhof"), ("public_transport", "station", "Station"),
    ("aerialway", "station", "Bergbahnstation"), ("amenity", "ferry_terminal", "Schiffstation"),
    ("tourism", "hotel", "Hotel"), ("tourism", "alpine_hut", "Berghütte"), ("tourism", "museum", "Museum"),
    ("historic", None, "Historisch"), ("amenity", "restaurant", "Restaurant"), ("leisure", "marina", "Hafen"),
    ("amenity", "fire_station", "Feuerwehr"), ("amenity", "post_office", "Post"), ("amenity", "library", "Bibliothek"),
    ("leisure", "sports_centre", "Sportanlage"), ("leisure", "stadium", "Sportanlage"), ("leisure", "pitch", "Sportanlage"),
    ("leisure", "swimming_pool", "Bad"), ("leisure", "park", "Park"), ("natural", "peak", "Berg"),
    ("natural", "water", "See/Gewässer"), ("waterway", "river", "Fluss"), ("waterway", "stream", "Bach"),
    ("place", None, "Ort"), ("bridge", None, "Brücke"), ("man_made", None, "Bauwerk"), ("office", None, "Büro/Verwaltung"),
    ("shop", None, "Geschäft"), ("tourism", None, "Tourismus"), ("amenity", None, "Einrichtung"),
    ("leisure", None, "Freizeit"), ("building", None, "Gebäude"), ("natural", None, "Natur"), ("landuse", None, "Areal"),
]


def _kind(tags: dict) -> str:
    for key, val, label in KINDS:
        if key in tags and (val is None or tags[key] == val):
            return label
    return "Sonstiges"


def build_buildings() -> int:
    """data/raw/osm/schwyz_named.json (Overpass `out center tags`) -> data/gazetteer/buildings.json."""
    from . import geo

    els = json.loads(OSM_FILE.read_text())["elements"]
    out, seen = [], set()
    for e in els:
        t = e.get("tags") or {}
        name = t.get("name")
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        if not name or lat is None or t.get("amenity") in NOISE or t.get("man_made") in ("survey_point", "manhole"):
            continue
        key = (e["type"], e["id"])
        if key in seen:
            continue
        seen.add(key)
        street = t.get("addr:street")
        num = t.get("addr:housenumber")
        mun = geo.municipality_at(lat, lon)
        out.append({
            "name": name, "kind": _kind(t), "lat": round(lat, 6), "lon": round(lon, 6),
            "address": f"{street} {num}".strip() if street else None,
            "municipality": mun["name"] if mun else None,
            "osm": f"https://www.openstreetmap.org/{e['type']}/{e['id']}",
            "wikidata": t.get("wikidata"), "alt_names": [t[k] for k in ("alt_name", "old_name", "official_name") if t.get(k)],
            "tags": {k: v for k, v in t.items() if k in KEEP or k in ("religion", "denomination", "social_facility", "ele")},
        })
    for b in out:
        b["source"] = "osm"
    out += gwr_buildings(out)
    ensure(GAZETTEER)
    BUILDINGS_FILE.write_text(json.dumps(out, ensure_ascii=False))
    _buildings.cache_clear()
    return len(out)


def _lv95_to_wgs84(e: float, n: float) -> tuple[float, float]:
    """swisstopo approximate formulas (about 1 m)."""
    y, x = (e - 2600000) / 1e6, (n - 1200000) / 1e6
    lon = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y ** 3
    lat = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x ** 3
    return lat * 100 / 36, lon * 100 / 36


def gwr_buildings(osm: list[dict]) -> list[dict]:
    """Named GWR buildings (existing, or demolished in 2003 or later) not already in the OSM list."""
    import sqlite3
    if not GWR_FILE.exists():
        return []
    db = sqlite3.connect(GWR_FILE)
    addr = {}
    for egid, street, num, plz, ort in db.execute(
            "select EGID, STRNAME, DEINR, DPLZ4, DPLZNAME from entrance order by DOFFADR desc, EDID"):
        addr.setdefault(egid, (f"{street} {num or ''}".strip() if street else None, plz, ort))
    near = {}
    for b in osm:
        near.setdefault((round(b["lat"], 2), round(b["lon"], 2)), []).append(b)
    out = []
    rows = db.execute("select EGID, GBEZ, GKLAS, GGDENAME, GKODE, GKODN, GBAUJ, GSTAT, GABBJ from building "
                      "where GBEZ is not null and GBEZ != '' and GKODE is not null")
    for egid, name, klass, gem, e, n, built, status, gone in rows:
        name = name.strip()
        if ADDRESS_LIKE.match(name) or not (status == 1004 or (status == 1007 and (gone or 0) >= 2003)):
            continue
        lat, lon = _lv95_to_wgs84(e, n)
        cell = [b for dy in (-0.01, 0, 0.01) for dx in (-0.01, 0, 0.01)
                for b in near.get((round(lat + dy, 2), round(lon + dx, 2)), [])]
        nn = _norm(name)
        if any(_haversine_m(lat, lon, b["lat"], b["lon"]) < 60 and (nn in _norm(b["name"]) or _norm(b["name"]) in nn)
               for b in cell):
            continue
        kind = "Alters-/Pflegeheim" if CARE.search(name) else GWR_KINDS.get(klass, "Gebäude")
        street, plz, ort = addr.get(egid, (None, None, None))
        out.append({
            "name": name, "kind": kind, "lat": round(lat, 6), "lon": round(lon, 6), "address": street,
            "municipality": gem, "osm": None, "wikidata": None, "alt_names": [], "tags": {},
            "source": "gwr", "egid": egid, "gwr": GWR_URL.format(egid), "year_built": built,
            "locality": ort, "plz": plz, "demolished": gone if status == 1007 else None,
        })
    return out


@lru_cache(maxsize=1)
def _buildings() -> list[dict]:
    return json.loads(BUILDINGS_FILE.read_text(encoding="utf-8")) if BUILDINGS_FILE.exists() else []


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^\w]+", " ", s).strip()


def named_buildings(lat: float | None = None, lon: float | None = None, radius_m: int = 500,
                    name: str | None = None, kinds: list[str] | None = None, limit: int = 20) -> list[dict]:
    """Named places in Kanton Schwyz from OpenStreetMap, near a point and/or matching a name.

    [{name, kind, lat, lon, address, municipality, osm, wikidata, alt_names, tags, distance_m?}]
    With lat/lon: within radius_m, nearest first. With name: case- and accent-insensitive substring
    match on name and alt_names (e.g. name="Acherhof"). kinds filters on `kind` (German labels such as
    "Kirche/Kapelle", "Hotel", "Alters-/Pflegeheim", "Bahnhof", "Berg", "See/Gewässer").
    """
    q = _norm(name) if name else None
    out = []
    for b in _buildings():
        if kinds and b["kind"] not in kinds:
            continue
        if q and not any(q in _norm(n) for n in [b["name"], *b.get("alt_names", [])]):
            continue
        item = dict(b)
        if lat is not None and lon is not None:
            d = _haversine_m(lat, lon, b["lat"], b["lon"])
            if d > radius_m:
                continue
            item["distance_m"] = round(d)
        out.append(item)
    if lat is not None and lon is not None:
        out.sort(key=lambda b: b["distance_m"])
    elif q:  # whole-word hits first ("Acherhof" before "Tischmacherhof"), buildings before bridges and rivers
        out.sort(key=lambda b: (not re.search(rf"\b{re.escape(q)}\b", _norm(b["name"])), b["kind"] in NOT_A_BUILDING))
    return out[:limit]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "lookup"])
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    a = ap.parse_args()
    if a.cmd == "build":
        print(build_buildings(), "named places ->", BUILDINGS_FILE)
    else:
        print(json.dumps(address_lookup(a.lat, a.lon), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
