"""Kanton Schwyz municipalities + resolving archive place tags (Thema) to a municipality.

Sources (swisstopo, no key):
- municipality polygons: ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill (identify, timeInstant=2025)
- place names: SearchServer type=locations
Results are cached in data/gazetteer/ so each place is looked up once.
"""

import json
import re
import unicodedata

from .http import PoliteClient
from .paths import GAZETTEER, RAW, ensure

API = "https://api3.geo.admin.ch/rest/services"
SZ_LV95_BOX = "2670000,1185000,2735000,1240000"
GEMEINDE_LAYER = "ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill"

# swisstopo REST limit is 40 requests/minute
_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        ensure(RAW / "geoadmin")
        _client = PoliteClient(min_interval=2.0, cache_dir=RAW / "geoadmin")
    return _client


def norm(s: str) -> str:
    s = re.sub(r"\s*\((SZ|Schwyz)\)\s*$", "", s.strip())
    s = unicodedata.normalize("NFC", s).casefold()
    return re.sub(r"[^\w]+", " ", s).strip()


def _unused_identify_gemeinde(e: float, n: float) -> dict | None:
    url = (
        f"{API}/all/MapServer/identify?geometryType=esriGeometryPoint&geometry={e},{n}&sr=2056"
        f"&layers=all:{GEMEINDE_LAYER}&tolerance=0&mapExtent={SZ_LV95_BOX}&imageDisplay=1000,800,96"
        "&returnGeometry=false&timeInstant=2025"
    )
    res = json.loads(client().get(url, suffix=".json"))["results"]
    for r in res:
        a = r["attributes"]
        if 1300 <= a.get("gde_nr", 0) < 1400:
            return {"name": a["gemname"], "bfs_nr": a["gde_nr"]}
    return None


def search(text: str, limit: int = 5) -> list[dict]:
    url = f"{API}/api/SearchServer"
    params = {"searchText": text, "type": "locations", "sr": "2056", "limit": limit,
              "origins": "gazetteer,gg25", "bbox": SZ_LV95_BOX}
    data = json.loads(client().get(url, params=params, suffix=".json"))
    return [r["attrs"] for r in data.get("results", [])]


def build_gemeinden() -> list[dict]:
    url = (
        f"{API}/all/MapServer/identify?geometryType=esriGeometryEnvelope&geometry={SZ_LV95_BOX}&sr=2056"
        f"&layers=all:{GEMEINDE_LAYER}&tolerance=0&mapExtent={SZ_LV95_BOX}&imageDisplay=1000,800,96"
        "&returnGeometry=false&limit=200&timeInstant=2025"
    )
    res = json.loads(client().get(url, suffix=".json"))["results"]
    out = {}
    for r in res:
        a = r["attributes"]
        if 1300 <= a.get("gde_nr", 0) < 1400:
            out[a["gde_nr"]] = {"name": a["gemname"], "bfs_nr": a["gde_nr"]}
    for g in out.values():
        hits = [h for h in search(g["name"].replace(" (SZ)", ""), 10) if h.get("origin") == "gg25"]
        if hits:
            g["lat"], g["lon"] = hits[0]["lat"], hits[0]["lon"]
        short = g["name"].replace(" (SZ)", "")
        g["aliases"] = sorted({short} - {g["name"]})
    gem = sorted(out.values(), key=lambda g: g["bfs_nr"])
    ensure(GAZETTEER)
    (GAZETTEER / "gemeinden.json").write_text(json.dumps(gem, ensure_ascii=False, indent=1))
    return gem


_gem: list[dict] | None = None
_cache: dict | None = None


def gemeinden() -> list[dict]:
    global _gem
    if _gem is None:
        p = GAZETTEER / "gemeinden.json"
        _gem = json.loads(p.read_text()) if p.exists() else build_gemeinden()
    return _gem


def _place_cache() -> dict:
    global _cache
    if _cache is None:
        p = GAZETTEER / "place_cache.json"
        _cache = json.loads(p.read_text()) if p.exists() else {}
    return _cache


def _save_cache() -> None:
    ensure(GAZETTEER)
    (GAZETTEER / "place_cache.json").write_text(json.dumps(_place_cache(), ensure_ascii=False, indent=1))


def lookup_place(tag: str) -> dict | None:
    """Geocode one place tag inside Kanton Schwyz -> {label, lat, lon, municipality, bfs_nr, origin} or None."""
    key = norm(tag)
    cache = _place_cache()
    if key in cache:
        return cache[key]
    names = {norm(g["name"]): g for g in gemeinden()}
    # rank: exact name first, then municipality > settlement > peaks/regions > anything else.
    # Flurnamen (tiny field names) are skipped: too many false hits ("Rigi" in Altendorf).
    prio = {"gg25": 0, "TLM_SIEDLUNGSNAME": 1, "TLM_NAME_PKT": 2, "TLM_GELAENDENAME": 3}
    cands = []
    for h in search(tag, 15):
        # label looks like "<i>Ort</i> <b>Oberarth</b> (SZ) - Arth" or "(LU,SZ) - Ingenbohl,Weggis,..."
        m = re.search(r"<b>(.*?)</b>\s*(?:\(([A-Z,]+)\))?\s*(?:-\s*(.+))?$", h.get("label", ""))
        if not m or not norm(m.group(1)).startswith(key.split(" ")[0]):
            continue
        cls = "gg25" if h.get("origin") == "gg25" else (h.get("objectclass") or "").upper()
        if cls == "TLM_FLURNAME":
            continue
        if cls == "gg25":
            gs = [names.get(norm(m.group(1)))]
        elif m.group(2) and "SZ" in m.group(2).split(",") and m.group(3):
            gs = [names.get(norm(x)) for x in m.group(3).split(",")]
        else:
            continue
        gs = [g for g in gs if g]
        if not gs:
            continue
        g = gs[0] if len(gs) == 1 else None  # spans several municipalities: location only
        exact = norm(m.group(1)) == key
        cands.append(((0 if exact else 1, prio.get(cls, 5)), h, g, cls))
    hit = None
    if cands:
        _, h, g, cls = min(cands, key=lambda c: c[0])
        hit = {"label": re.sub(r"<[^>]+>", "", h["label"]), "lat": h["lat"], "lon": h["lon"],
               "origin": h.get("origin"), "kind": cls,
               "municipality": g["name"] if g else None, "bfs_nr": g["bfs_nr"] if g else None}
    cache[key] = hit
    _save_cache()
    return hit


def resolve(tags: list[str]) -> tuple[str | None, dict | None]:
    """Thema tags -> (municipality, location). A tag that is itself a municipality wins;
    otherwise the first tag that geocodes inside the canton."""
    by_name = {}
    for g in gemeinden():
        by_name[norm(g["name"])] = g
        for a in g.get("aliases", []):
            by_name[norm(a)] = g
    muni = next((by_name[norm(t)] for t in tags if norm(t) in by_name), None)
    rest = [t for t in tags if norm(t) not in by_name]
    queries = [f"{a} {b}" for a, b in zip(rest, rest[1:])] + rest  # "Rigi; Staffel" -> "Rigi Staffel"
    place = None
    for q in queries:
        place = lookup_place(q)
        if place and (muni is None or place["municipality"] in (None, muni["name"])):
            break
        place = None
    if muni is None and place and place["municipality"]:
        muni = next(g for g in gemeinden() if g["name"] == place["municipality"])
    if place:
        loc = {"lat": place["lat"], "lon": place["lon"], "method": "thema_gazetteer", "precision_m": 1000}
    elif muni and "lat" in muni:
        loc = {"lat": muni["lat"], "lon": muni["lon"], "method": "thema_gazetteer", "precision_m": 3000}
    else:
        loc = None
    return (muni["name"] if muni else None), loc
