"""v5 stage 3: one Claude call for a photo the retrieval could not place by itself.

Claude gets the photo and up to 5 candidate reference photos with the place each one is registered at,
and answers through one strict tool: which candidate shows the same place (if any), the text it can
read, and the names it can back with what it sees. Our code then turns the pick (or a name it read)
into coordinates and official names; Claude never types coordinates.
"""

import logging

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
                "municipality": {"type": ["string", "null"], "enum": [*names, None]},
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


def lookup(query: str) -> dict | None:
    """A name Claude read or recognised -> {lat, lon, radius_m, source}. Named buildings first, then swisstopo."""
    hits = dp.named_buildings(name=query, limit=3)
    if hits:
        b = hits[0]
        return {"lat": b["lat"], "lon": b["lon"], "radius_m": 50, "source": f"Gebäudeverzeichnis: {b['name']}"}
    try:
        body = cached_get(search_url(query))
    except Exception:
        log.warning("swisstopo search failed for %r", query, exc_info=True)
        return None
    for r in body.get("results") or []:
        a = r.get("attrs") or {}
        if "(SZ)" in (a.get("label") or "") or "SZ" == (a.get("detail") or "")[-2:].upper():
            return {"lat": a["lat"], "lon": a["lon"], "radius_m": 300, "source": f"swisstopo: {query}"}
    return None
