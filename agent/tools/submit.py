"""submit_result: the final answer tool. Its input is the `fields` block of CONTRACTS 3 plus
rejected_hypotheses, so the answer arrives as structured data without parsing prose."""

import copy

import data_pipeline as dp

from ..config import FIXTURES

NAME = "submit_result"
EVIDENCE_KINDS = ["visual_cue", "text_on_card", "similar_image", "archive_record", "swisstopo_place", "terrain",
                  "map_layer", "address_register", "named_building", "exif", "session_photo"]
# v3 order = the archive's priority (Ortschaft, Gemeinde, Gebaeude, See/Fluss/Berg, Strasse), then the map pin
FIELD_NAMES = ["locality", "municipality", "buildings", "landscape_features", "street", "coordinates"]

_EVIDENCE = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": EVIDENCE_KINDS},
        "summary": {"type": "string", "description": "one German sentence naming the source"},
        "ref_id": {"type": ["string", "null"], "description": "PhotoRecord id the evidence comes from, or null"},
        "url": {"type": ["string", "null"], "description": "link to the source (OSM, swisstopo), or null"},
        "score": {"type": ["number", "null"]},
        "supports": {"type": "boolean", "description": "false = evidence against the value"},
    },
    "required": ["kind", "summary", "ref_id", "url", "score", "supports"],
    "additionalProperties": False,
}


def _field(value_schema: dict, about: str) -> dict:
    return {
        "type": "object",
        "description": about,
        "properties": {
            "value": value_schema,
            "evidence": {"type": "array", "items": {"$ref": "#/$defs/evidence"},
                         "description": "every independent source that supports (or contradicts) the value"},
        },
        "required": ["value", "evidence"],
        "additionalProperties": False,
    }


def municipalities() -> list[str]:
    """The canonical Gemeinde names (data_pipeline gazetteer, else the contract fixture)."""
    try:
        names = [g["name"] for g in dp.gazetteer()]
    except Exception:
        names = []
    if not names:
        import json

        names = [g["name"] for g in json.loads((FIXTURES / "gemeinden.json").read_text(encoding="utf-8"))]
    return sorted(set(names))


def definition(names: list[str]) -> dict:
    coord_obj = {
        "type": ["object", "null"],
        "properties": {"lat": {"type": "number"}, "lon": {"type": "number"},
                       "radius_m": {"type": "number", "description": "uncertainty radius in metres"}},
        "required": ["lat", "lon", "radius_m"],
        "additionalProperties": False,
    }
    text_or_null = {"type": ["string", "null"]}
    names_list = {"type": "array", "items": {"type": "string"}}
    return {
        "name": NAME,
        "description": (
            "Submit the final answer. Call it exactly once, when you are done (or when told to stop). "
            "For every field give the value and ALL independent sources that back it; the confidence is "
            "computed from the number of independent sources. A value you cannot back with a source must be "
            "null (or []): never guess a name. Summaries and reasons in German, one sentence each."
        ),
        "input_schema": {
            "type": "object",
            "$defs": {"evidence": _EVIDENCE},
            "properties": {
                "locality": _field(text_or_null, "Ortschaft: official postal locality, e.g. 'Brunnen' (in Ingenbohl)"),
                # strict mode rejects an enum on a ["string", "null"] type, so spell it as anyOf
                "municipality": _field({"anyOf": [{"type": "string", "enum": list(names)}, {"type": "null"}]},
                                       "politische Gemeinde in Kanton Schwyz, or null if outside or unknown"),
                "buildings": _field(names_list, "concrete names of the buildings shown, e.g. 'Alterszentrum Acherhof'"),
                "landscape_features": _field(names_list, "named lakes, rivers, mountains visible, e.g. 'Grosser Mythen'"),
                "street": _field(text_or_null, "street and number, e.g. 'Grundstrasse 32', else street only, else null"),
                "coordinates": _field(coord_obj, "WGS84 position of the depicted place"),
                "place_name_printed": {"type": "boolean",
                                       "description": "true if a place name is printed or written in the image"},
                "rejected_hypotheses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"field": {"type": "string", "enum": FIELD_NAMES},
                                       "value": {"type": "string"},
                                       "reason": {"type": "string", "description": "German, one sentence"}},
                        "required": ["field", "value", "reason"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": [*FIELD_NAMES, "place_name_printed", "rejected_hypotheses"],
            "additionalProperties": False,
        },
        # Not strict: together with the other strict tools this schema compiles to a grammar the API
        # rejects as too large (400). normalize() below repairs whatever the model sends instead.
        "strict": False,
    }


# ---------- normalisation (never reject a final answer; repair it) ----------

def _conf(x) -> float:
    try:
        return round(min(1.0, max(0.0, float(x))), 3)
    except (TypeError, ValueError):
        return 0.0


def _evidence(items) -> list[dict]:
    out = []
    for e in items or []:
        if not isinstance(e, dict) or not e.get("summary"):
            continue
        ev = {"kind": e.get("kind") if e.get("kind") in EVIDENCE_KINDS else "visual_cue",
              "summary": str(e["summary"]).strip(),
              "supports": bool(e.get("supports", True))}
        if e.get("ref_id"):
            ev["ref_id"] = str(e["ref_id"])
        if isinstance(e.get("score"), (int, float)):
            ev["score"] = float(e["score"])
        if e.get("url"):
            ev["url"] = str(e["url"])
        out.append(ev)
    return out


def _value(name: str, v, names: set[str]):
    if name == "municipality":
        if not v:
            return None
        v = str(v).strip()
        if v in names:
            return v
        low = {n.casefold(): n for n in names} | {n.split(" (")[0].casefold(): n for n in names}
        return low.get(v.casefold(), v)
    if name in ("locality", "street"):
        return str(v).strip() or None if v else None
    if name in ("buildings", "landscape_features"):
        items = v if isinstance(v, list) else ([v] if v else [])
        return [str(x).strip() for x in items if str(x).strip()]
    if name == "coordinates":
        if not isinstance(v, dict) or v.get("lat") is None or v.get("lon") is None:
            return None
        try:
            out = {"lat": float(v["lat"]), "lon": float(v["lon"])}
        except (TypeError, ValueError):
            return None
        if isinstance(v.get("radius_m"), (int, float)):
            out["radius_m"] = float(v["radius_m"])
        return out
    return v


def empty_fields() -> dict:
    return {n: {"value": [] if n in ("buildings", "landscape_features") else None,
                "confidence": 0.0, "evidence": []} for n in FIELD_NAMES}


def normalize(inp: dict, names: list[str]) -> dict:
    """submit_result input -> {fields, rejected_hypotheses, estimates}. Confidences are set later by
    agent.confidence from the evidence; here they start at 0."""
    nameset = set(names)
    fields = empty_fields()
    for n in FIELD_NAMES:
        f = inp.get(n)
        if not isinstance(f, dict):
            continue
        fields[n] = {"value": _value(n, f.get("value"), nameset), "confidence": 0.0,
                     "evidence": _evidence(f.get("evidence"))}
    rejected = [{"field": str(r.get("field")), "value": str(r.get("value")), "reason": str(r.get("reason"))}
                for r in inp.get("rejected_hypotheses") or [] if isinstance(r, dict) and r.get("reason")]
    printed = inp.get("place_name_printed")
    return {
        "fields": fields,
        "rejected_hypotheses": rejected,
        "estimates": {"place_name_printed": printed if isinstance(printed, bool) else None},
    }


def fallback(reason: str) -> dict:
    """Result body when the model never submitted: everything unknown, confidence 0."""
    out = {"fields": copy.deepcopy(empty_fields()), "rejected_hypotheses": [],
           "estimates": {"place_name_printed": None}}
    out["fields"]["municipality"]["evidence"] = [{"kind": "visual_cue", "summary": reason, "supports": False}]
    return out
