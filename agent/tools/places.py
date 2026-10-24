"""address_lookup and named_buildings (CONTRACTS 4, v3): what is at a point, and which named place a
building is. They give the official names the archive wants (Ortschaft, Gemeinde, Strasse, Gebaeude)."""

import data_pipeline as dp

from .base import ToolContext, ToolOutput

MAX_ADDRESSES = 5
MAX_BUILDINGS = 10

ADDRESS_LOOKUP = {
    "name": "address_lookup",
    "description": (
        "What is at a point, from the official Swiss registers (swisstopo): Ortschaft (postal locality, e.g. "
        "Brunnen in Gemeinde Ingenbohl), politische Gemeinde, canton, and the nearest official building "
        "addresses (street + number). Use it once you have coordinates for the depicted place (from "
        "named_buildings, swisstopo_search or a reference photo) to get the official locality, municipality "
        "and street."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "radius_m": {"type": "integer", "description": "search radius for addresses, 20 to 500, default 100"},
        },
        "required": ["lat", "lon"],
        "additionalProperties": False,
    },
}

NAMED_BUILDINGS = {
    "name": "named_buildings",
    "description": (
        "Named places in Kanton Schwyz from OpenStreetMap and the federal building register GWR (source "
        "'gwr': official building name, year built, official address): buildings (churches, schools, care "
        "homes, hotels, stations, huts, ...) and landscape names, with coordinates. A building built after "
        "the photo's capture year cannot be in the photo. Search by name (substring, "
        "accents ignored, e.g. 'Acherhof'), near a point, or both; optionally filter by kind. Kinds are German "
        "labels such as Kirche/Kapelle, Kloster, Rathaus, Schule, Alters-/Pflegeheim, Spital, Bahnhof, "
        "Bergbahnstation, Schiffstation, Hotel, Berghütte, Museum, Restaurant, Berg, See/Gewässer, Fluss, Ort, "
        "Brücke, Gebäude. Use it to turn a building you see into its concrete name."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": ["string", "null"], "description": "name or part of it, or null"},
            "lat": {"type": ["number", "null"], "description": "search near this point, or null"},
            "lon": {"type": ["number", "null"]},
            "radius_m": {"type": "integer", "description": "radius around lat/lon, default 500"},
            "kinds": {"type": ["array", "null"], "items": {"type": "string"},
                      "description": "only these kinds, or null for all"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}


def run_address_lookup(ctx: ToolContext, lat: float, lon: float, radius_m: int = 100) -> ToolOutput:
    radius = max(20, min(500, int(radius_m or 100)))
    a = dp.address_lookup(lat, lon, radius_m=radius, limit=MAX_ADDRESSES)
    addresses = [{k: x.get(k) for k in ("address", "street", "number", "ortschaft", "municipality", "distance_m",
                                        "lat", "lon", "category")} for x in (a.get("addresses") or [])[:MAX_ADDRESSES]]
    data = {k: a.get(k) for k in ("ortschaft", "plz", "municipality", "canton", "in_canton", "source")}
    data["addresses"] = addresses
    return ToolOutput(data, _address_summary(data))


def _address_summary(d: dict) -> str:
    if not d.get("municipality"):
        return "Adressverzeichnis: keine Gemeinde an diesem Punkt gefunden"
    where = f"{d['ortschaft']}, Gemeinde {d['municipality']}" if d.get("ortschaft") else f"Gemeinde {d['municipality']}"
    if not d.get("in_canton", True):
        where += f" ({d.get('canton') or 'ausserhalb'}, nicht Kanton Schwyz)"
    if d["addresses"]:
        first = d["addresses"][0]
        return f"Adressverzeichnis: {where}, nächste Adresse {first['address']} ({first.get('distance_m')} m)"
    return f"Adressverzeichnis: {where}, keine Adresse im Umkreis"


def run_named_buildings(ctx: ToolContext, name: str | None = None, lat: float | None = None,
                        lon: float | None = None, radius_m: int = 500, kinds: list[str] | None = None) -> ToolOutput:
    if not name and (lat is None or lon is None):
        return ToolOutput({"error": "give a name, or lat and lon"}, "Gebäudesuche: Name oder Koordinaten fehlen",
                          is_error=True)
    hits = dp.named_buildings(lat=lat, lon=lon, radius_m=int(radius_m or 500), name=name or None,
                              kinds=kinds or None, limit=MAX_BUILDINGS)
    keep = ("name", "kind", "source", "address", "locality", "municipality", "lat", "lon", "distance_m", "year_built",
            "demolished", "osm", "gwr", "wikidata", "alt_names")
    out = [{k: h[k] for k in keep if h.get(k) not in (None, [], "")} for h in hits[:MAX_BUILDINGS]]
    query = {"name": name, "lat": lat, "lon": lon, "radius_m": radius_m, "kinds": kinds}
    return ToolOutput({"query": {k: v for k, v in query.items() if v is not None}, "results": out},
                      _buildings_summary(name, out))


def _buildings_summary(name: str | None, hits: list[dict]) -> str:
    what = f"«{name}»" if name else "in der Nähe"
    if not hits:
        return f"Gebäude {what}: nichts gefunden"
    first = hits[0]
    where = f", {first['municipality']}" if first.get("municipality") else ""
    src = "GWR" if first.get("source") == "gwr" else "OSM"
    return f"Gebäude {what}: {len(hits)} Treffer, erster: {first['name']} ({src}, {first.get('kind')}{where})"
