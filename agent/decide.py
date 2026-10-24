"""v5 stage 3: one Claude call for a photo the retrieval could not place by itself.

Claude gets the photo and up to 5 candidate reference photos with the place each one is registered at,
and answers through one strict tool: which candidate shows the same place (if any), the text it can
read, and the names it can back with what it sees. Our code then turns the pick (or a name it read)
into coordinates and official names; Claude never types coordinates.
"""

import logging
import re

import data_pipeline as dp

from . import llm, pipeline
from .config import MODEL
from .tools import submit
from .tools.base import image_block
from .tools.swisstopo import cached_get, search_url

log = logging.getLogger(__name__)

N_CANDIDATES = 5
EFFORT = "medium"
MAX_TOKENS = 4000
TOOL = "answer"

SYSTEM = """You help the Staatsarchiv Schwyz (Switzerland) find where a photo from Kanton Schwyz was taken. \
Most photos are colour photos from 2003 to 2013 of buildings, villages and landscapes.

You get the photo, then numbered candidate reference photos found by image search, each with the place it is \
registered at. The candidates are look-alikes, often of the wrong place.

1. Read every text in the photo (signs, house names, shop names, inscriptions, station boards).
2. A candidate is the same place only if you can point at the same specific things: the same building with \
the same windows and roof, the same church tower, the same skyline. Similar style or a similar lake is not \
enough. If none is the same place, say so (candidate = null).
3. place_query: a name to look up in the map registers when the photo itself tells you where it is: a sign \
you read ("Hotel Waldstätterhof", "Bahnhof Arth-Goldau") or a landmark you clearly recognise ("Kloster \
Einsiedeln"). Otherwise null.
4. Names only with a source you can state. Never guess a village from style alone; null is a valid answer.
Call the answer tool exactly once. Reasons in German, one sentence."""


def _tool(names: list[str]) -> dict:
    nullable = {"type": ["string", "null"]}
    return {
        "name": TOOL,
        "description": "The answer for this photo. Call exactly once.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text_read": {"type": "string", "description": "every text readable in the photo, or ''"},
                "candidate": {"type": ["integer", "null"], "description": "number of the candidate that shows "
                              "the same place, or null"},
                "candidate_reason": nullable,
                "place_query": nullable,
                "municipality": {"anyOf": [{"type": "string", "enum": names}, {"type": "null"}]},
                "locality": nullable,
                "buildings": {"type": "array", "items": {"type": "string"},
                              "description": "concrete building names you can back (sign, landmark), not types"},
                "landscape_features": {"type": "array", "items": {"type": "string"},
                                       "description": "named lakes, rivers, mountains you recognise"},
                "reason": {"type": "string", "description": "German, one sentence: how you know"},
            },
            "required": ["text_read", "candidate", "candidate_reason", "place_query", "municipality", "locality",
                         "buildings", "landscape_features", "reason"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def candidates(hits: list[dict]) -> list[dict]:
    """The top hits with a known place (precise point or at least a municipality), one per place."""
    out = []
    for h in hits:
        if len(out) >= N_CANDIDATES:
            break
        if h["lat"] is None and not h["municipality"]:
            continue
        if any(c["lat"] is not None and h["lat"] is not None
               and pipeline.haversine_m((c["lat"], c["lon"]), (h["lat"], h["lon"])) < 100 for c in out):
            continue
        place = None
        if h["lat"] is not None and h["precision_m"] <= pipeline.PRECISE_M:
            a = dp.address_lookup(h["lat"], h["lon"], radius_m=100, limit=1)
            place = ", ".join(x for x in (a.get("ortschaft"), a.get("municipality")) if x)
        out.append({**h, "place": place or (f"Gemeinde {h['municipality']}" if h["municipality"] else None)})
    return out


def _label(i: int, c: dict) -> str:
    bits = [f"Kandidat {i}: registriert bei {c['place'] or 'unbekannt'}"]
    if c["title"]:
        bits.append(f"Titel \"{c['title']}\"")
    if c["year"]:
        bits.append(str(c["year"]))
    if c["inliers"]:
        bits.append(f"{c['inliers']} geometrisch passende Punkte")
    return ", ".join(bits)


def ask(client, image_path: str, cands: list[dict], context: str, meta: dict) -> tuple[dict | None, float]:
    """One call. Returns (tool input or None, cost_usd)."""
    names = submit.municipalities()
    content = [image_block(image_path, 1024, 88), {"type": "text", "text": f"Das Foto.\n{context}"}]
    for i, c in enumerate(cands, 1):
        path = dp.image_file(dp.get_record(c["id"]))
        if path and path.exists():
            content += [{"type": "text", "text": _label(i, c)}, image_block(path, 512, 80)]
    if not cands:
        content.append({"type": "text", "text": "Keine Kandidaten gefunden."})
    resp, usd = llm.create(
        client, model=MODEL, meta=meta, max_tokens=MAX_TOKENS,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        tools=[_tool(names)], tool_choice={"type": "auto"}, output_config={"effort": EFFORT},
        messages=[{"role": "user", "content": content}])
    use = next((b for b in resp.content if b.type == "tool_use" and b.name == TOOL), None)
    return (dict(use.input) if use else None), usd


_TYPE_WORDS = {"hotel", "restaurant", "gasthaus", "gasthof", "kirche", "pfarrkirche", "kapelle", "haus", "bahnhof",
               "schulhaus", "schule", "station", "talstation", "bergstation", "the", "der", "die", "das", "des", "zum",
               "zur", "am", "im", "bei", "und", "st.", "sankt"}


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[\wäöüéèà.]+", (s or "").lower()) if len(w) >= 4 and w not in _TYPE_WORDS]


def _in(municipality: str | None, place: str | None) -> bool:
    """Same Gemeinde, ignoring a "(SZ)" suffix. No constraint when municipality is None."""
    if not municipality:
        return True
    norm = lambda s: re.sub(r"\s*\(SZ\)\s*$", "", s or "").strip().lower()
    return norm(municipality) == norm(place)


def lookup(query: str, municipality: str | None = None) -> dict | None:
    """A name Claude read or recognised -> {lat, lon, radius_m, source}, inside `municipality` when given.

    Named buildings (OSM + GWR) are scored by how many distinctive words of the query they share
    ("Hotel du Lac Seehof" finds "du Lac Seehof"); at least half the words must match. Then swisstopo
    places, but only places in Kanton Schwyz (its free-text search is fuzzy across the whole country)."""
    words = _words(query)
    best, best_n = None, 0
    seen = set()
    for w in words:
        for b in dp.named_buildings(name=w, limit=50):
            key = (b["name"], b["lat"], b["lon"])
            if key in seen or not _in(municipality, b.get("municipality")):
                continue
            seen.add(key)
            n = sum(1 for x in words if x in " ".join([b["name"], *b.get("alt_names", [])]).lower())
            if n > best_n:
                best, best_n = b, n
    if best and best_n * 2 >= len(words):
        return {"lat": best["lat"], "lon": best["lon"], "radius_m": 50,
                "source": f"Gebäudeverzeichnis: {best['name']} ({best.get('municipality') or '?'})"}
    try:
        body = cached_get(search_url(query))
    except Exception:
        log.warning("swisstopo search failed for %r", query, exc_info=True)
        return None
    for r in body.get("results") or []:
        a = r.get("attrs") or {}
        label = re.sub(r"<[^>]+>", "", a.get("label") or "")
        if "(SZ)" not in label or a.get("lat") is None or not any(w in label.lower() for w in words):
            continue
        place = dp.address_lookup(a["lat"], a["lon"], radius_m=50, limit=1)
        if _in(municipality, place.get("municipality")):
            return {"lat": a["lat"], "lon": a["lon"], "radius_m": 300, "source": f"swisstopo: {label}"}
    return None
