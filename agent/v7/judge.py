"""The judge: one Claude call sees the photo and every candidate with the photos taken there, picks one or none."""

import data_pipeline as dp

from .. import llm
from ..config import MODEL
from .common import CACHE_ONLY, IMAGE_PX, SURE, cached, image, key, original, ref_image, store

VERSION = "v7.2"
TOOL = {
    "name": "pick", "description": "Which candidate the photo shows. Call exactly once.", "strict": True,
    "input_schema": {"type": "object", "additionalProperties": False,
                     "properties": {"candidate": {"type": ["integer", "null"]},
                                    "certainty": {"type": "string", "enum": list(SURE)},
                                    "building_shown": {"type": "boolean",
                                                       "description": "the named building itself is in the photo"},
                                    "reason": {"type": "string"}},
                     "required": ["candidate", "certainty", "building_shown", "reason"]}}

PROMPT = """Das Foto oben soll verortet werden. Unten stehen Kandidaten: Orte aus dem amtlichen Register \
(in zufälliger Reihenfolge; ähnliche Gebäude derselben Art sind absichtlich dabei), je mit Fotos, die heute (meist 2015 und später) dort \
aufgenommen wurden, und wie viele Bildpunkte geometrisch zum Foto passen (100 und mehr: sehr \
wahrscheinlich dieselbe Szene; unter 60: kein Beleg, nur kein Vergleichsfoto aus demselben Blickwinkel).

Vergleiche konkret: zähle zuerst die Geschosse auf dem Foto und vergleiche sie mit dem Register; dann dasselbe Gebäude (Geschosse, Fensterraster, Dach, Turm), dieselbe Umgebung, dieselben \
Berge im Hintergrund. Gebäude können seit 2003 bis 2013 renoviert sein. Wähle den Kandidaten, der das Foto \
zeigt, oder null, wenn keiner überzeugt. Begründung auf Deutsch, ein bis zwei Sätze."""


def _label(i: int, c: dict) -> str:
    bits = [f"Kandidat {i}: {c.get('building') or c.get('street') or c.get('locality') or c.get('municipality') or c.get('outside')}",
            f"Gemeinde {c.get('municipality') or '?'}", f"Ortschaft {c.get('locality') or '?'}"]
    if c.get("street"):
        bits.append(f"Adresse {c['street']}")
    if c.get("lat") is not None and (f := dp.registers.building_facts(c["lat"], c["lon"])) and f.get("floors"):
        bits.append(f"laut Gebäuderegister {f['floors']} Geschosse" + (f", Grundfläche {f['area_m2']} m²" if f.get("area_m2") else ""))
    chk = c.get("check") or {}
    bits.append(f"bester Bildvergleich {chk.get('best_inliers', 0)} Punkte"
                if chk.get("photos") or chk.get("by_match") else "keine Vergleichsfotos vor Ort")
    return ", ".join(bits)


def judge(rec: dict, cands: list[dict], meta: dict) -> tuple[dict | None, float]:
    """(pick {candidate (1-based or None), certainty, building_shown, reason}, usd)."""
    c = [image(original(rec), IMAGE_PX), {"type": "text", "text": PROMPT}]
    for i, cand in enumerate(cands, 1):
        c.append({"type": "text", "text": _label(i, cand)})
        for p in (cand.get("check") or {}).get("photos", [])[:2]:
            if f := ref_image(p["id"]):  # a machine without the reference photos leaves them out
                c.append(image(f, 512))
    k = key(VERSION, MODEL, "judge", rec["id"], [_label(i, x) for i, x in enumerate(cands, 1)])
    if hit := cached(k):
        return hit["pick"], 0.0
    if CACHE_ONLY:
        return None, 0.0
    resp, usd = llm.create(llm.make_client(), model=MODEL, meta={**meta, "step": "judge"}, max_tokens=8000,
                           tools=[TOOL], tool_choice={"type": "auto"}, output_config={"effort": "high"},
                           messages=[{"role": "user", "content": c}])
    use = next((b for b in resp.content if b.type == "tool_use" and b.name == "pick"), None)
    pick = dict(use.input) if use else None
    if pick is not None:
        store(k, {"pick": pick, "usd": usd, "photo_id": rec["id"]})
    return pick, usd
