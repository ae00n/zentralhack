"""v6 analysis: Claude first, registers second, reference matches as a check.

1. One Claude call: the photo, its EXIF date, session siblings and up to 4 geometrically verified reference
   matches (data_pipeline.matches, precomputed) with the place each is registered at. Claude says what it
   reads and recognises: text, Gemeinde, Ortschaft, building name, street, landmarks, which match (if any)
   shows the same place, and how sure it is of each.
2. Our code turns that into a point: a picked match, else the building name in the registers
   (find_building), else the street (find_address), else a strong verified match Claude did not contradict.
3. Names at the point come from the official registers (address_at): Ortschaft, Gemeinde, street, building.
   Landmarks are kept only when swissNAMES3D knows them nearby. Claude never types coordinates.
4. Confidence per field = measured hit rate of the path on the hand check (agent/v6_confidence.json,
   written by `python -m agent.eval.replay --fit`). Until that exists, priors that are marked as such.

Returns the AnalysisResult of CONTRACTS section 3, so the server, the report and the Excel export are unchanged.
Claude calls are cached by input (agent/.cache/v6), so re-running a photo with the same inputs is free;
AGENT_CACHE_ONLY=1 never calls the API (replay).
"""

import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Callable

import data_pipeline as dp

from . import llm, results
from .config import CACHE_DIR, DATA_DIR as DATA_DIR_, MODEL, REPO_ROOT
from . import fields as submit
from .fields import image_block

EFFORT = os.environ.get("AGENT_EFFORT", "high")
MAX_TOKENS = 8000
TOOL = "answer"
N_MATCHES = 4
STRONG_INLIERS = 100  # a verified match this strong places the photo unless Claude contradicts it
SAME_PLACE_M = 300
ACCEPT = 0.9
CONFIDENCE_FILE = REPO_ROOT / "agent" / "v6_confidence.json"
CLAUDE_CACHE = CACHE_DIR / "v6"
CACHE_ONLY = os.environ.get("AGENT_CACHE_ONLY") == "1"
SURE = ("sicher", "wahrscheinlich", "vermutet")
IMAGE_PX = 1568  # the API's largest size without downscaling: small signs stay readable
TILE_PX = 1024   # each quarter of the original once more, for text the full view shrinks away
# server-side web search (only the query leaves, never the photo), as on claude.ai
SEARCH = os.environ.get("AGENT_WEB_SEARCH", "1") == "1"
SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 4,
               "user_location": {"type": "approximate", "country": "CH", "region": "Schwyz", "timezone": "Europe/Zurich"}}
MAX_TURNS = 4
# register kinds whose point is not where a photo is taken from ("Fronalpstock" is a summit, not a building)
NOT_PLACES = {"Berg", "See/Gewässer", "Fluss", "Bach", "Natur", "Ort", "Areal", "Park"}

SYSTEM = """You help the Staatsarchiv Schwyz (Switzerland) find where photos were taken. They are colour photos \
from 2003 to 2013, almost all in Kanton Schwyz: villages, buildings, streets, lakes, mountains, events.

Look at the photo like a local who knows the canton well. Say where it is: Gemeinde, Ortschaft (village or \
locality), the concrete building name ("Alterszentrum Acherhof", "Hotel Waldstätterhof", "Pfarrkirche \
St. Martin"), the street, and named mountains, lakes or rivers in view. Use everything: text you can read \
(signs, house names, shop names, posters, number plates), landmark buildings, the mountain skyline, the shore line.

You may also get reference photos found by image matching, each with the place it is registered at and how \
many points matched geometrically. A reference is the same place only if you can point at the same specific \
things (same building, windows, roof, tower, skyline). Many are look-alikes of the wrong place.

Rules:
- Certainty per field: "sicher" (you read it or the landmark is unmistakable), "wahrscheinlich" (strong cues), \
"vermutet" (an educated guess). Give your best answer with "vermutet" rather than nothing when you have a real \
clue; use null only when you have no clue at all.
- building: a proper name, never a type ("Wohnhaus", "Kirche" alone is not a name). null if you do not know it.
- If the photo is outside Kanton Schwyz, put its political municipality and canton in outside_canton \
(e.g. "Glarus Nord GL", "Schwende-Rüte AI") and municipality null.
- You can search the web to check a name you read or a building you think you recognise (e.g. the hotel's \
address, the chapel's village). Search for facts, not for the photo.
- Call the answer tool exactly once. reason: German, one or two sentences, what gave it away."""


def _tool(names: list[str]) -> dict:
    s = {"type": ["string", "null"]}
    sure = {"anyOf": [{"type": "string", "enum": list(SURE)}, {"type": "null"}]}  # strict mode: no null in an enum
    return {
        "name": TOOL, "description": "The answer for this photo. Call exactly once.", "strict": True,
        "input_schema": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "text_read": {"type": "string", "description": "every text readable in the photo, or ''"},
                "municipality": {"anyOf": [{"type": "string", "enum": names}, {"type": "null"}]},
                "municipality_certainty": sure,
                "locality": s, "locality_certainty": sure,
                "building": s, "building_certainty": sure,
                "street": {"type": ["string", "null"], "description": "street name, with house number if known"},
                "street_certainty": sure,
                "landmarks": {"type": "array", "items": {"type": "string"},
                              "description": "named mountains, lakes, rivers, islands in view"},
                "same_place_reference": {"type": ["integer", "null"],
                                         "description": "number of the reference photo showing the same place"},
                "outside_canton": s,
                "reason": {"type": "string"},
            },
            "required": ["text_read", "municipality", "municipality_certainty", "locality", "locality_certainty",
                         "building", "building_certainty", "street", "street_certainty", "landmarks",
                         "same_place_reference", "outside_canton", "reason"],
        },
    }


# ---------------------------------------------------------------- inputs

def references(photo_id: str | None, image_path: str) -> list[dict]:
    """Verified matches with a precise point, one per place, strongest first. Only from the precomputed
    matches of the current index (data_pipeline.matches): none for an upload or before the build ran."""
    m = dp.matches(photo_id) if photo_id else None
    out = []
    for h in (m or {}).get("hits", []):
        if not h["verified"] or h["lat"] is None or (h["precision_m"] or 1e9) > 100:
            continue
        if any(_dist(h, o) < 100 for o in out):
            continue
        a = dp.address_at(h["lat"], h["lon"], 80, limit=1)
        out.append({**h, "place": ", ".join(x for x in (a.get("ortschaft"), a.get("municipality")) if x) or None})
        if len(out) == N_MATCHES:
            break
    return out


def original(rec: dict, fallback: str) -> str:
    """The photo at full resolution: the challenge originals (data/challenge/<folder>/<file>, 3000 px and more)
    or a downloaded Commons original, else the 1024 px copy the data pipeline keeps."""
    raw = rec.get("raw") or {}
    from data_pipeline.paths import DATA_DIR, IMAGES
    if rec.get("source") == "challenge" and raw.get("folder") and raw.get("file_name"):
        p = DATA_DIR / "challenge" / raw["folder"] / raw["file_name"]
    else:
        p = IMAGES / f"{rec.get('source')}_full" / f"{rec.get('source_id')}.jpg"
    return str(p) if p.exists() else fallback


def tiles(path: str) -> list[dict]:
    """The four quarters of a large photo (overlapping by 10%), each as its own image block."""
    import base64
    import io

    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        if max(w, h) <= IMAGE_PX * 1.2:
            return []
        out = []
        for x0, y0 in ((0, 0), (0.45, 0), (0, 0.45), (0.45, 0.45)):
            t = im.crop((int(x0 * w), int(y0 * h), int((x0 + 0.55) * w), int((y0 + 0.55) * h)))
            t.thumbnail((TILE_PX, TILE_PX))
            buf = io.BytesIO()
            t.save(buf, format="JPEG", quality=88)
            out.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.standard_b64encode(buf.getvalue()).decode("ascii")}})
    return out


def _siblings(rec: dict) -> list[str]:
    return [s for s in ((rec.get("raw") or {}).get("session") or []) if dp.get_record(s)][:2]


def _context(rec: dict) -> str:
    raw, d = rec.get("raw") or {}, rec.get("date") or {}
    exif = raw.get("exif") or {}
    bits = []
    if d.get("raw"):
        bits.append(f"Aufgenommen am {d['raw']} (EXIF)")
    if exif.get("focal_35mm"):
        bits.append(f"Brennweite {exif['focal_35mm']} mm (Kleinbild)")
    return ", ".join(bits) + "." if bits else ""


def _label(i: int, r: dict) -> str:
    bits = [f"Referenz {i}: registriert bei {r['place'] or 'unbekannt'}", f"{r['inliers']} passende Punkte"]
    if r.get("title"):
        bits.append(f"Titel \"{r['title']}\"")
    if r.get("year"):
        bits.append(str(r["year"]))
    return ", ".join(bits)


# ---------------------------------------------------------------- the one call

def ask(image_path: str, rec: dict, refs: list[dict], meta: dict) -> tuple[dict | None, float, bool]:
    """(tool input or None, cost_usd, from_cache)."""
    names = submit.municipalities()
    sibs = _siblings(rec)
    full = original(rec, image_path)
    content = [image_block(full, IMAGE_PX, 90), {"type": "text", "text": f"Das Foto. {_context(rec)}"}]
    quarters = tiles(full)
    if quarters:
        content.append({"type": "text", "text": "Dasselbe Foto in vier Ausschnitten (oben links, oben rechts, "
                                                "unten links, unten rechts), damit kleine Schrift lesbar ist:"})
        content += quarters
    for s in sibs:
        content += [{"type": "text", "text": "Foto aus derselben Aufnahmeserie (gleiche Kamera, wenige Minuten "
                                             "davor oder danach):"}, image_block(dp.image_file(dp.get_record(s)), 512, 80)]
    for i, r in enumerate(refs, 1):
        p = dp.image_file(dp.get_record(r["id"]))
        if p and p.exists():
            content += [{"type": "text", "text": _label(i, r)}, image_block(p, 512, 80)]
    tool = _tool(names)
    tools = [tool] + ([SEARCH_TOOL] if SEARCH else [])
    key = hashlib.sha256(json.dumps([MODEL, EFFORT, SYSTEM, tools, (rec.get("image") or {}).get("sha1") or image_path,
                                     full != image_path, _context(rec), sibs, [r["id"] for r in refs]],
                                    ensure_ascii=False).encode()).hexdigest()[:24]
    cache = CLAUDE_CACHE / f"{key}.json"
    if cache.exists():
        c = json.loads(cache.read_text())
        return c["input"], 0.0, True
    if CACHE_ONLY:
        return None, 0.0, False
    client, messages, usd, searches, answer = llm.make_client(), [{"role": "user", "content": content}], 0.0, [], None
    for _ in range(MAX_TURNS):  # searches can pause the turn; and an answer in prose gets one reminder
        resp, cost = llm.create(
            client, model=MODEL, meta=meta, max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=tools, tool_choice={"type": "auto"}, output_config={"effort": EFFORT}, messages=messages)
        usd += cost
        searches += [b.input.get("query") for b in resp.content if b.type == "server_tool_use"]
        use = next((b for b in resp.content if b.type == "tool_use" and b.name == TOOL), None)
        if use:
            answer = dict(use.input)
            break
        messages.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})
        if resp.stop_reason != "pause_turn":
            messages.append({"role": "user", "content": "Call the answer tool now."})
    if answer is not None:
        answer["searches"] = searches
        CLAUDE_CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"input": answer, "usd": usd, "photo_id": meta.get("photo_id")}, ensure_ascii=False))
    return answer, usd, False


# ---------------------------------------------------------------- compare look-alike buildings

# kinds that look alike from outside: a guessed care home is compared with hospitals and schools too
LOOKALIKE = [{"Spital", "Alters-/Pflegeheim", "Soziale Einrichtung", "Schule"},
             {"Hotel", "Restaurant", "Tourismus"}, {"Kirche/Kapelle", "Kloster"}, {"Bahnhof", "Station", "Bergbahnstation"}]
N_CANDIDATES = 8
COMPARE_TOOL = {
    "name": "pick", "description": "Which candidate place the photo shows. Call exactly once.", "strict": True,
    "input_schema": {"type": "object", "additionalProperties": False,
                     "properties": {"candidate": {"type": ["integer", "null"]},
                                    "certainty": {"type": "string", "enum": list(SURE)},
                                    "reason": {"type": "string"}},
                     "required": ["candidate", "certainty", "reason"]}}


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1)))
    return math.degrees(math.atan2(y, x)) % 360


def facing(b: dict, n: int = 2) -> list[dict]:
    """Reference photos that look at the building: taken 15 to 200 m away with the camera turned towards
    it (within 35 degrees). A photo next to it facing the other way shows other houses."""
    out = []
    for p in dp.photos_near(b["lat"], b["lon"], 200, max_precision_m=100, limit=300):
        if p["source"] not in ("mapillary", "commons") or p["heading_deg"] is None or p["distance_m"] < 15:
            continue
        r = dp.get_record(p["id"])
        to = _bearing(r["location"]["lat"], r["location"]["lon"], b["lat"], b["lon"])
        off = abs((p["heading_deg"] - to + 180) % 360 - 180)
        if off <= 35:
            out.append((off / 35 + p["distance_m"] / 200, p))
    return [p for _, p in sorted(out, key=lambda x: x[0])[:n]]


def candidates(guess: str, municipality: str) -> list[dict]:
    """The guessed building and the look-alike buildings of its Gemeinde (same kind group), each with up to
    two reference photos taken within 150 m (Mapillary, Commons). Only candidates with photos count."""
    hits = [h for h in dp.find_building(guess, municipality) if h["kind"] not in NOT_PLACES]
    group = next((g for g in LOOKALIKE if hits and hits[0]["kind"] in g), None)
    if not group:
        return []
    from data_pipeline.places import named_buildings
    g = _center(municipality) or hits[0]
    same = [b for b in named_buildings(lat=g["lat"], lon=g["lon"], radius_m=8000, limit=2000)
            if b["kind"] in group and not b.get("generic") and _gem(b.get("municipality")) == _gem(municipality)]
    # the guessed kind first (care homes count as hospitals), then nearest the guessed building: Claude usually
    # knows the area and confuses neighbours
    care = {"Spital", "Alters-/Pflegeheim", "Soziale Einrichtung"}
    pool = hits[:1] + sorted(same, key=lambda b: (b["kind"] != hits[0]["kind"] and not {b["kind"], hits[0]["kind"]} <= care,
                                                  _dist(b, hits[0])))
    out = []
    for b in pool:
        if any(_dist(b, o) < 80 for o in out):  # OSM and GWR name the same house twice
            continue
        photos = facing(b)
        facts = dp.registers.building_facts(b["lat"], b["lon"])
        if photos or (facts and facts.get("floors")):
            out.append({"name": b["name"], "kind": b["kind"], "lat": b["lat"], "lon": b["lon"], "photos": photos,
                        "facts": facts})
        if len(out) == N_CANDIDATES:
            break
    return out


def compare(full: str, answer: dict, meta: dict) -> tuple[dict | None, float, int]:
    """Claude only guessed the building: show it the look-alike buildings of the Gemeinde, each with photos
    taken there, and let it pick. (pick {building, certainty, reason} or None, cost_usd, candidates shown)."""
    cands = candidates(answer["building"], answer["municipality"])
    if len(cands) < 2:
        return None, 0.0, len(cands)
    content = [image_block(full, IMAGE_PX, 90),
               {"type": "text", "text": f"Das Foto. Vermutet wurde: {answer['building']} in {answer['municipality']}. "
                                        "Unten Kandidaten aus dem Gebäuderegister derselben Gemeinde, je mit Fotos, "
                                        "die in der Nähe aufgenommen wurden (2015 und später: Fassaden können seither renoviert sein) und den "
                                        "Geschossen aus dem Gebäuderegister. Welcher Kandidat zeigt dasselbe Gebäude? "
                                        "Zähle zuerst die Geschosse auf dem Foto und vergleiche sie mit dem Register; dann "
                                        "Grundriss, Fensterraster, Dach, Umgebung und den Blick auf die Berge. Keiner "
                                        "passt: candidate null."}]
    for i, c in enumerate(cands, 1):
        f = c.get("facts") or {}
        reg = ", ".join(x for x in (f"{f['floors']} Geschosse" if f.get("floors") else None,
                                    f"Grundfläche {f['area_m2']} m²" if f.get("area_m2") else None) if x)
        content.append({"type": "text", "text": f"Kandidat {i}: {c['name']} ({c['kind']})"
                                                + (f", laut Gebäuderegister {reg}" if reg else "")
                                                + ("" if c["photos"] else ", keine Fotos aus der Nähe")})
        content += [image_block(DATA_DIR_ / p["image_path"], 512, 80) for p in c["photos"]]
    key = hashlib.sha256(json.dumps([MODEL, "compare", COMPARE_TOOL, full, content[1]["text"],
                                     [(c["name"], c.get("facts"), [p["id"] for p in c["photos"]]) for c in cands]],
                                    ensure_ascii=False).encode()).hexdigest()[:24]
    cache = CLAUDE_CACHE / f"{key}.json"
    if cache.exists():
        pick = json.loads(cache.read_text())["input"]
        usd = 0.0
    elif CACHE_ONLY:
        return None, 0.0, len(cands)
    else:
        resp, usd = llm.create(llm.make_client(), model=MODEL, meta=meta, max_tokens=MAX_TOKENS,
                               tools=[COMPARE_TOOL], tool_choice={"type": "auto"}, output_config={"effort": EFFORT},
                               messages=[{"role": "user", "content": content}])
        use = next((b for b in resp.content if b.type == "tool_use" and b.name == "pick"), None)
        pick = dict(use.input) if use else None
        if pick is None:
            return None, usd, len(cands)
        CLAUDE_CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"input": pick, "usd": usd, "photo_id": meta.get("photo_id")}, ensure_ascii=False))
    k = pick.get("candidate")
    if not isinstance(k, int) or not 1 <= k <= len(cands):
        return {"building": None, "certainty": pick["certainty"], "reason": pick["reason"]}, usd, len(cands)
    return {"building": cands[k - 1]["name"], "certainty": pick["certainty"], "reason": pick["reason"]}, usd, len(cands)


# ---------------------------------------------------------------- resolve

def _dist(a: dict, b: dict) -> float:
    from data_pipeline.places import _haversine_m
    return _haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])


def _gem(s: str | None) -> str:
    return re.sub(r"\s*\(SZ\)\s*$", "", s or "").strip().casefold()


def resolve(answer: dict, refs: list[dict]) -> dict:
    """Claude's answer + references -> {path, point, building, agree, ref}. Rules, first that applies:
    pick (Claude names a reference as the same place), building (its name is in the registers; a name Claude
    only guessed counts after compare() picked it among the look-alike buildings of the Gemeinde),
    street (the street is in the register of that Gemeinde), match (a strong verified reference, unless
    Claude names another Gemeinde with "sicher" or "wahrscheinlich"), claude (names only, no point)."""
    mun, sure = answer.get("municipality"), answer.get("municipality_certainty")
    k = answer.get("same_place_reference")
    best = refs[0] if refs else None
    if isinstance(k, int) and 1 <= k <= len(refs):
        r = refs[k - 1]
        return {"path": "pick", "point": {"lat": r["lat"], "lon": r["lon"], "radius_m": 50}, "ref": r, "building": None}
    if answer.get("building") and (answer.get("building_certainty") != "vermutet" or answer.get("compared")):
        hits = [h for h in dp.find_building(answer["building"], mun) if h["kind"] not in NOT_PLACES]
        if not mun and len({h["municipality"] for h in hits}) > 1:
            hits = []  # same name in several Gemeinden and no Gemeinde to tell them apart
        if hits:
            h = hits[0]
            return {"path": "building", "point": {"lat": h["lat"], "lon": h["lon"], "radius_m": 50}, "ref": None,
                    "building": h}
    if answer.get("street") and mun:
        m = re.match(r"^(.*?)\s*(\d+\w*)?$", answer["street"].strip())
        hits = dp.find_address(m.group(1), m.group(2), mun)
        if hits:
            h = hits[0]
            radius = 30 if m.group(2) and h["number"] and h["number"].startswith(m.group(2)) else 300
            return {"path": "street", "point": {"lat": h["lat"], "lon": h["lon"], "radius_m": radius}, "ref": None,
                    "building": None}
    if best and best["inliers"] >= STRONG_INLIERS:
        at = dp.address_at(best["lat"], best["lon"], 50, limit=1)
        if not mun or sure == "vermutet" or _gem(at.get("municipality")) == _gem(mun):
            return {"path": "match", "point": {"lat": best["lat"], "lon": best["lon"], "radius_m": 100}, "ref": best,
                    "building": None}
    return {"path": "claude" if (mun or answer.get("outside_canton")) else None, "point": None, "ref": None,
            "building": None}


# ---------------------------------------------------------------- confidence

PRIORS = {  # used until the hand check exists; guesses, labelled as such in the explanation
    "pick": 0.85, "building": 0.85, "compare": 0.7, "street": 0.75, "match": 0.8, "claude": 0.5,
}


def _table() -> dict:
    return json.loads(CONFIDENCE_FILE.read_text()) if CONFIDENCE_FILE.exists() else {}


def bucket(path: str | None, agree: bool | None, sure: str | None) -> str:
    """The cell confidence is measured in: how the point was found (path) and how sure Claude is of the
    Gemeinde. Measured on Commons: "sicher" was right 94% of the time, "vermutet" 55%, whatever the path."""
    return f"{path}|{sure or 'none'}"


def confidence(b: str, field: str) -> tuple[float, bool]:
    """(value, measured). measured False = prior."""
    cell = _table().get(b, {}).get(field)
    if cell and cell.get("n", 0) >= 3:
        return cell["rate"], True
    base = PRIORS.get(b.split("|")[0], 0.0)
    if b.startswith("claude|"):
        base = {"sicher": 0.7, "wahrscheinlich": 0.55, "vermutet": 0.35}.get(b.split("|")[1], 0.0)
    if b.startswith("compare|"):
        base = {"sicher": 0.8, "wahrscheinlich": 0.65, "vermutet": 0.4}.get(b.split("|")[1], 0.0)
    return base, False


# ---------------------------------------------------------------- analyze

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ev(kind: str, summary: str, ref_id: str | None = None, score: float | None = None, supports: bool = True) -> dict:
    return {"kind": kind, "summary": summary, "ref_id": ref_id, "url": None, "score": score, "supports": supports}


def analyze(photo_id: str | None = None, image_path: str | None = None, *, model: str = MODEL,
            exclude_ids: list[str] = (), on_event: Callable[[dict], None] | None = None) -> dict:
    rec = (dp.get_record(photo_id) if photo_id else None) or {}
    if photo_id and not rec:
        raise ValueError(f"unknown photo_id {photo_id!r} (data_pipeline.get_record returned None)")
    image_path = image_path or str(dp.image_file(rec))
    year = (rec.get("date") or {}).get("year_from")
    trace: list[dict] = []

    def emit(item: dict) -> None:
        item = {"step": len(trace) + 1, **item}
        trace.append(item)
        if on_event:
            on_event(item)

    t0 = time.monotonic()
    refs = [r for r in references(photo_id, image_path) if r["id"] not in set(exclude_ids)]
    emit({"type": "tool_call", "tool": "matches", "input": {"photo_id": photo_id},
          "output_summary": f"{len(refs)} geometrisch bestätigte Referenzfotos"
                            + (f", bestes mit {refs[0]['inliers']} Punkten ({refs[0]['place']})" if refs else ""),
          "ms": round((time.monotonic() - t0) * 1000)})
    t1 = time.monotonic()
    answer, usd, cached = ask(image_path, rec, refs, {"photo_id": photo_id, "pipeline": 6})
    emit({"type": "tool_call", "tool": "claude", "input": {"references": len(refs), "cached": cached},
          "output_summary": (answer or {}).get("reason") or "keine Antwort", "ms": round((time.monotonic() - t1) * 1000)})
    answer = answer or {}
    if answer.get("building_certainty") == "vermutet" and answer.get("municipality"):
        t2 = time.monotonic()
        picked, cost, n = compare(original(rec, image_path), answer, {"photo_id": photo_id, "pipeline": 6, "step": "compare"})
        usd += cost
        if n:
            emit({"type": "tool_call", "tool": "compare", "input": {"candidates": n},
                  "output_summary": (picked or {}).get("reason") or "kein Kandidat passt",
                  "ms": round((time.monotonic() - t2) * 1000)})
        if picked:  # the street came with the guessed building: it goes when the comparison rejects that building
            same = picked.get("building") == answer["building"]
            answer = {**answer, "building": picked.get("building"), "building_certainty": picked["certainty"],
                      "compared": True, **({} if same else {"street": None, "street_certainty": None})}
    res = resolve(answer, refs) if answer else {"path": None, "point": None, "ref": None, "building": None}
    return _result(photo_id, model, rec, year, answer, refs, res, usd, trace, emit)


def _result(photo_id, model, rec, year, answer, refs, res, usd, trace, emit) -> dict:
    f = submit.empty_fields()
    path, point = res["path"], res["point"]
    at = dp.address_at(point["lat"], point["lon"], 60, limit=5, year=year) if point else {}
    claude_mun = answer.get("municipality")
    # agree: a verified reference at the point, or Claude's Gemeinde equal to the point's
    near_ref = next((r for r in refs if point and _dist(r, point) <= SAME_PLACE_M), None)
    agree = bool(point) and (near_ref is not None or _gem(claude_mun) == _gem(at.get("municipality")))
    b = bucket(path, agree, answer.get("municipality_certainty"))
    if path == "building" and answer.get("compared"):
        b = f"compare|{answer.get('building_certainty')}"
    measured = []

    claude_ev = [_ev("visual_cue", answer["reason"])] if answer.get("reason") else []
    if answer.get("text_read"):
        claude_ev.append(_ev("text_on_card", f"Gelesen: {answer['text_read'][:200]}"))
    ref_ev = [_ev("similar_image", f"Referenzfoto {r['place'] or ''}: {r.get('title') or r['id']} "
                                   f"({r['inliers']} passende Punkte)", r["id"], r["inliers"]) for r in refs[:2]
              if point and _dist(r, point) <= SAME_PLACE_M]
    reg_ev = [_ev("address_register", "Amtliches Gebäude- und Adressregister (GWR) am bestimmten Punkt")] if point else []
    bld_ev = [_ev("named_building", f"Gebäuderegister: {res['building']['name']}")] if res.get("building") else []

    def put(name: str, value, evidence: list[dict]) -> None:
        if value in (None, [], ""):
            return
        c, m = confidence(b, name)
        measured.append(m)
        f[name] = {"value": value, "confidence": round(c, 3), "evidence": evidence}

    if point:
        put("municipality", at.get("municipality"), ref_ev + reg_ev + claude_ev)
        put("locality", at.get("ortschaft"), ref_ev + reg_ev + claude_ev)
        addr = (res.get("building") or {}).get("address") or next((a["address"] for a in at.get("addresses") or []), None)
        put("street", addr, reg_ev)
        named = [res["building"]["name"]] if res.get("building") else _named_at(answer, point, at)
        put("buildings", named, bld_ev or reg_ev)
        f["coordinates"] = {"value": point, "confidence": confidence(b, "coordinates")[0], "evidence": ref_ev + reg_ev}
    elif path == "claude":
        put("municipality", claude_mun or answer.get("outside_canton"), claude_ev)
        put("locality", _official_locality(answer.get("locality")) if claude_mun else None, claude_ev)
        if answer.get("building_certainty") == "sicher":
            put("buildings", [answer["building"]] if answer.get("building") else [], claude_ev)
    center = point or _center(claude_mun)
    marks = _landmarks(answer.get("landmarks") or [], center)
    put("landscape_features", marks, [_ev("map_layer", "swissNAMES3D (swisstopo)")] + claude_ev if marks else [])

    overall = min(f["municipality"]["confidence"], f["locality"]["confidence"] or f["municipality"]["confidence"])
    needs_review = overall < ACCEPT or not f["municipality"]["value"]
    why = {"pick": "Claude erkennt denselben Ort auf einem geometrisch bestätigten Referenzfoto",
           "building": "Gebäude erkannt bzw. Name gelesen und im Gebäuderegister gefunden",
           "street": "Strasse gelesen bzw. erkannt und im Adressregister gefunden",
           "match": "Geometrisch stark bestätigtes Referenzfoto",
           "claude": "Nur Claudes Einschätzung des Bildes, kein Register- oder Referenztreffer"}.get(path)
    how = "gemessene Trefferquote der Handprüfung" if measured and all(measured) else "Schätzwert, noch nicht gemessen"
    expl = f"{why}. Konfidenz: {how} ({b})." if why else "Kein Hinweis auf den Ort: offen gelassen."
    emit({"type": "final", "text": f"{f['locality']['value'] or '?'}, {f['municipality']['value'] or '?'} "
                                   f"({path or 'offen'}, Konfidenz {overall:.2f})", "ms": 0})
    return {
        "photo_id": photo_id, "run_id": f"{_now()}-{secrets.token_hex(2)}",
        "status": "needs_review" if needs_review else "done", "model": model, "composite": None,
        "fields": f, "overall_confidence": round(overall, 3), "confidence_explanation": expl,
        "needs_review": needs_review, "review": None, "rejected_hypotheses": [], "trace": trace,
        "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 0, "cost_usd": round(usd, 6), "budget_hit": False,
                  "api_calls": 0 if not usd else 1},
        "created_at": _now(), "estimates": {"place_name_printed": None},
        "settings": {"pipeline": 6, "path": path, "bucket": b, "answer": answer,
                     "references": [{k: r[k] for k in ("id", "inliers", "place")} for r in refs]},
    }


def _named_at(answer: dict, point: dict, at: dict) -> list[str]:
    """The building at a point placed by a reference: the name Claude read or recognised when the register has
    it within 150 m, else a proper GWR name within 30 m ("Aufbewahrungshalle" and other types are left out)."""
    if answer.get("building") and answer.get("building_certainty") in ("sicher", "wahrscheinlich"):
        for h in dp.find_building(answer["building"], answer.get("municipality")):
            if h["kind"] not in NOT_PLACES and _dist(h, point) <= 150:
                return [h["name"]]
    return [a["building"] for a in at.get("addresses") or []
            if a.get("building") and a["distance_m"] <= 30 and a.get("kind")][:1]


def _official_locality(name: str | None) -> str | None:
    """Claude's Ortschaft in the official PLZ spelling ("Seewen" -> "Seewen SZ"), or None when it is not
    an Ortschaft at all ("Sattel, bei der Talstation"): the export only takes official names."""
    from data_pipeline.qc import _norm, official_names
    if not name:
        return None
    ort = official_names()["locality"]
    return ort.get(_norm(name)) or ort.get(re.sub(r"\s+sz$", "", _norm(name)))


def _center(municipality: str | None) -> dict | None:
    g = next((g for g in dp.gazetteer() if _gem(g["name"]) == _gem(municipality)), None) if municipality else None
    return {"lat": g["lat"], "lon": g["lon"]} if g else None


def _landmarks(names: list[str], center: dict | None) -> list[str]:
    """Claude's landmark names that swissNAMES3D knows within 40 km, in the official spelling."""
    out = []
    for n in names:
        q = re.sub(r"^(der|die|das|the)\s+", "", n.strip(), flags=re.I)
        q = re.sub(r"^Grosse[rs]?\s", "Gross ", re.sub(r"^Kleine[rs]?\s", "Chli ", q))  # swisstopo: "Chli Mythen"
        lat, lon = (center["lat"], center["lon"]) if center else (47.02, 8.75)
        hits = dp.landmarks_near(lat, lon, 40, name=q, limit=1)
        if hits and hits[0]["name"] not in out:
            out.append(hits[0]["name"])
    return out


def run(photo_ids: list[str], save: bool = True) -> list[dict]:
    out = []
    for pid in photo_ids:
        r = analyze(pid)
        if save:
            results.archive(pid)
            results.save(r)
        out.append(r)
        print(f"{pid}: {r['trace'][-1]['text']}  ${r['usage']['cost_usd']:.3f}", flush=True)
    return out


def main() -> None:
    import argparse

    from data_pipeline.jsonl import read_jsonl
    from data_pipeline.paths import RECORDS

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="photo ids; default: all Prio 1")
    ap.add_argument("--all", action="store_true", help="all 603 challenge photos")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    ids = a.ids or [r["id"] for r in read_jsonl(RECORDS / "challenge.jsonl")
                    if a.all or (r.get("raw") or {}).get("priority") == 1]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(lambda pid: run([pid]), ids))


if __name__ == "__main__":
    main()
