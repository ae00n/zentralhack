"""One Claude attempt: the photo (plus hints, depending on the variant) and tools, ending in one answer.

Variants, so that agreement between attempts means something:
  all    photo + EXIF + session siblings + strong reference matches + Google web hints
  web    photo + EXIF + session siblings + Google web hints
  blind  photo + EXIF + session siblings
"""

import data_pipeline as dp

from .. import fields as submit
from .. import llm
from ..config import MODEL
from . import tools, vision
from .common import CACHE_ONLY, IMAGE_PX, SURE, cached, image, key, original, quarters, store

VARIANTS = ("all", "web", "blind")
EFFORT = "high"
MAX_TOKENS = 12000
MAX_TURNS = 14
STRONG_INLIERS = 100  # below this a match is noise on these photos (29 of 65 weaker hits lie > 2 km off)
SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5,
               "user_location": {"type": "approximate", "country": "CH", "region": "Schwyz", "timezone": "Europe/Zurich"}}
VERSION = "v7.1"

SYSTEM = """You find where a photo was taken, for the Staatsarchiv Schwyz (Switzerland). The photos are colour \
photos from 2003 to 2013, almost all in Kanton Schwyz: villages, buildings, streets, lakes, mountains, events.

Work like an investigator who knows the canton:
1. Look closely. Use zoom on every sign, house name, shop name, poster or number plate you can see.
2. Form hypotheses from text, landmark buildings, the mountain skyline (Mythen, Rigi, Fronalpstock, Urmiberg, \
Frohnalpstock, Drusberg), lake shores (Vierwaldstättersee, Lauerzersee, Zugersee, Sihlsee), terrain.
3. Check them with the tools: find_building / find_address / place_search give register entries with a point; \
buildings_near and address_at tell you what is at a point. web_search checks facts (a hotel's village, a \
chapel's name). Do not stop at the first idea when the clues are weak.
4. Answer with the main subject's register point: point_id of the tool result that IS the building or place \
the photo shows (or, for a street scene, the address it shows). Never pick a point that is only nearby.

Rules:
- Certainty per field: "sicher" (read it, or the landmark is unmistakable and the register confirms it), \
"wahrscheinlich" (strong cues), "vermutet" (an educated guess). null only with no clue at all.
- building: a proper name ("Alterszentrum Acherhof", "Pfarrkirche St. Martin"), never a type alone.
- street: the street (and house number) of the subject, from the register when you have it.
- Outside Kanton Schwyz: municipality null, outside_canton = "Gemeinde KT" (e.g. "Glarus Nord GL").
- Reference photos and web hints can be wrong: a reference is the same place only if you can point at the \
same specific things (same building, windows, roof, tower, skyline).
- Call the answer tool exactly once at the end. reason: German, one or two sentences, what gave it away."""


def answer_tool(names: list[str]) -> dict:
    s = {"type": ["string", "null"]}
    sure = {"anyOf": [{"type": "string", "enum": list(SURE)}, {"type": "null"}]}
    return {
        "name": "answer", "description": "The final answer for this photo. Call exactly once.", "strict": True,
        "input_schema": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "text_read": {"type": "string", "description": "all text readable in the photo, or ''"},
                "municipality": {"anyOf": [{"type": "string", "enum": names}, {"type": "null"}]},
                "municipality_certainty": sure,
                "locality": s, "locality_certainty": sure,
                "building": s, "building_certainty": sure,
                "street": s, "street_certainty": sure,
                "landmarks": {"type": "array", "items": {"type": "string"},
                              "description": "named mountains, lakes, rivers, islands in view"},
                "point_id": {"type": ["string", "null"],
                             "description": "point_id of the tool result that is the photo's main subject"},
                "outside_canton": s,
                "reason": {"type": "string"},
            },
            "required": ["text_read", "municipality", "municipality_certainty", "locality", "locality_certainty",
                         "building", "building_certainty", "street", "street_certainty", "landmarks", "point_id",
                         "outside_canton", "reason"],
        },
    }


def strong_refs(rec: dict) -> list[dict]:
    """Reference matches (precomputed, or computed for an upload) with at least STRONG_INLIERS, one per
    100 m, strongest first."""
    from .common import dist_m
    hits = rec["upload_hits"] if "upload_hits" in rec else (dp.matches(rec["id"]) or {}).get("hits", [])
    out = []
    for h in hits:
        if (h["inliers"] or 0) < STRONG_INLIERS or h["lat"] is None:
            continue
        if not any(dist_m(h, o) < 100 for o in out):
            out.append(h)
    return sorted(out, key=lambda h: -h["inliers"])[:3]


def _context(rec: dict) -> str:
    raw, d = rec.get("raw") or {}, rec.get("date") or {}
    exif = raw.get("exif") or {}
    bits = [f"Aufgenommen am {d['raw']} (EXIF)"] if d.get("raw") else []
    if exif.get("focal_35mm"):
        bits.append(f"Brennweite {exif['focal_35mm']} mm (Kleinbild)")
    return ", ".join(bits) + "." if bits else ""


def content(rec: dict, variant: str) -> tuple[list[dict], list[dict]]:
    """(user content, references shown)."""
    full = original(rec)
    c = [image(full, IMAGE_PX), {"type": "text", "text": f"Das Foto. {_context(rec)}"}]
    if q := quarters(full):
        c += [{"type": "text", "text": "Dasselbe Foto in vier Ausschnitten (oben links, oben rechts, unten links, "
                                       "unten rechts):"}, *q]
    for s in [s for s in ((rec.get("raw") or {}).get("session") or []) if dp.get_record(s)][:2]:
        c += [{"type": "text", "text": "Foto aus derselben Aufnahmeserie (gleiche Kamera, wenige Minuten davor "
                                       "oder danach):"}, image(dp.image_file(dp.get_record(s)), 512)]
    refs = strong_refs(rec) if variant == "all" else []
    for i, r in enumerate(refs, 1):
        p = dp.image_file(dp.get_record(r["id"]))
        if p and p.exists():
            c += [{"type": "text", "text": f"Referenzfoto {i} (Bildvergleich, {r['inliers']} geometrisch passende "
                                           f"Punkte; Titel \"{r.get('title') or '-'}\", {r.get('year') or '?'}, "
                                           f"aufgenommen in {r.get('municipality') or '?'}):"}, image(p, 512)]
    if variant in ("all", "web"):
        if hint := vision.summary(vision.detect(rec["id"], full)):
            c.append({"type": "text", "text": hint})
    c.append({"type": "text", "text": "Wo ist das? Untersuche es mit den Werkzeugen und gib dann die Antwort."})
    c[-1]["cache_control"] = {"type": "ephemeral"}
    return c, refs


def run(rec: dict, variant: str, meta: dict) -> dict:
    """{variant, answer (or None), point (the subject's tool point or None), calls, refs, usd, cached}."""
    names = submit.municipalities()
    user, refs = content(rec, variant)
    has_web = bool(vision.summary(vision.detect(rec["id"], original(rec)))) if variant != "blind" else False
    k = key(VERSION, MODEL, variant, rec["id"], [r["id"] for r in refs], has_web)
    if c := cached(k):
        return {**c, "cached": True}
    out = {"variant": variant, "answer": None, "point": None, "calls": [], "refs": [r["id"] for r in refs],
           "usd": 0.0, "searches": []}
    if CACHE_ONLY:
        return {**out, "cached": False}
    session = tools.Session(original(rec))
    specs = [{**s} for s in tools.SPECS] + [answer_tool(names), SEARCH_TOOL]
    client, messages = llm.make_client(), [{"role": "user", "content": user}]
    for turn in range(MAX_TURNS):
        if turn == MAX_TURNS - 2:  # thinking forbids a forced tool_choice: ask in words
            messages[-1]["content"] = _with_text(messages[-1]["content"], "Letzte Runde: gib jetzt die Antwort.")
        resp, cost = llm.create(
            client, model=MODEL, meta={**meta, "variant": variant}, max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}], tools=specs,
            tool_choice={"type": "auto"},
            output_config={"effort": EFFORT}, messages=messages)
        out["usd"] += cost
        out["searches"] += [b.input.get("query") for b in resp.content if b.type == "server_tool_use"]
        done = next((b for b in resp.content if b.type == "tool_use" and b.name == "answer"), None)
        if done:
            out["answer"] = dict(done.input)
            break
        messages.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})
        uses = [b for b in resp.content if b.type == "tool_use"]
        if uses:
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": b.id, "content": session.run(b.name, dict(b.input))}
                for b in uses]})
        elif resp.stop_reason != "pause_turn":
            messages.append({"role": "user", "content": "Gib jetzt die Antwort mit dem answer-Werkzeug."})
    a = out["answer"] or {}
    out["point"] = session.point(a.get("point_id"))
    out["calls"] = session.calls
    store(k, out)
    return {**out, "cached": False}


def _with_text(c, text: str) -> list[dict]:
    c = [{"type": "text", "text": c}] if isinstance(c, str) else list(c)
    return c + [{"type": "text", "text": text}]
