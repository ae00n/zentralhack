"""submit_result: the final answer tool. Its input is the `fields` block of CONTRACTS 3 plus
rejected_hypotheses, so the answer arrives as structured data without parsing prose."""

import copy

import data_pipeline as dp

from ..config import FIXTURES

NAME = "submit_result"
EVIDENCE_KINDS = ["visual_cue", "text_on_card", "similar_image", "archive_record",
                  "swisstopo_place", "terrain", "map_layer"]
FIELD_NAMES = ["municipality", "place", "buildings", "landscape_features", "decade", "year_range", "coordinates"]

_EVIDENCE = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": EVIDENCE_KINDS},
        "summary": {"type": "string", "description": "one German sentence"},
        "ref_id": {"type": ["string", "null"], "description": "PhotoRecord id the evidence comes from, or null"},
        "score": {"type": ["number", "null"]},
        "supports": {"type": "boolean", "description": "false = evidence against the value"},
    },
    "required": ["kind", "summary", "ref_id", "score", "supports"],
    "additionalProperties": False,
}


def _field(value_schema: dict, about: str) -> dict:
    return {
        "type": "object",
        "description": about,
        "properties": {
            "value": value_schema,
            "confidence": {"type": "number", "description": "0.0 to 1.0"},
            "evidence": {"type": "array", "items": {"$ref": "#/$defs/evidence"}},
        },
        "required": ["value", "confidence", "evidence"],
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
    year_obj = {
        "type": ["object", "null"],
        "properties": {"from": {"type": "integer"}, "to": {"type": "integer"}},
        "required": ["from", "to"],
        "additionalProperties": False,
    }
    coord_obj = {
        "type": ["object", "null"],
        "properties": {"lat": {"type": "number"}, "lon": {"type": "number"},
                       "radius_m": {"type": "number", "description": "uncertainty radius in metres"}},
        "required": ["lat", "lon", "radius_m"],
        "additionalProperties": False,
    }
    return {
        "name": NAME,
        "description": (
            "Submit the final answer. Call it exactly once, when you are done (or when told to stop). "
            "Every field needs a value (null or [] when unknown), a calibrated confidence and its evidence. "
            "All summaries and reasons in German, one sentence each."
        ),
        "input_schema": {
            "type": "object",
            "$defs": {"evidence": _EVIDENCE},
            "properties": {
                "municipality": _field({"type": ["string", "null"], "enum": [*names, None]},
                                       "Gemeinde in Kanton Schwyz, or null if outside or unknown"),
                "place": _field({"type": ["string", "null"]}, "locality, village part or viewpoint"),
                "buildings": _field({"type": "array", "items": {"type": "string"}}, "named buildings visible"),
                "landscape_features": _field({"type": "array", "items": {"type": "string"}},
                                             "named peaks, lakes, rivers visible"),
                "decade": _field({"type": ["integer", "null"]}, "first year of the decade the photo was taken, e.g. 1910"),
                "year_range": _field(year_obj, "plausible range of the capture year"),
                "coordinates": _field(coord_obj, "WGS84 position of the depicted place"),
                "year_best": {"type": ["integer", "null"], "description": "single most likely capture year"},
                "place_name_printed": {"type": "boolean",
                                       "description": "true if a place name is printed or written on the card"},
                "overall_confidence": {"type": "number"},
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
            "required": [*FIELD_NAMES, "year_best", "place_name_printed", "overall_confidence", "rejected_hypotheses"],
            "additionalProperties": False,
        },
        "strict": True,
    }


# ---------- normalisation (never reject a final answer; repair it) ----------

def _conf(x) -> float:
    try:
        return round(min(1.0, max(0.0, float(x))), 3)
    except (TypeError, ValueError):
        return 0.0


def _int(x):
    try:
        return int(x) if x is not None else None
    except (TypeError, ValueError):
        return None


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
    if name == "place":
        return str(v).strip() if v else None
    if name in ("buildings", "landscape_features"):
        return [str(s) for s in v] if isinstance(v, list) else ([str(v)] if v else [])
    if name == "decade":
        d = _int(v)
        return d - d % 10 if d is not None else None
    if name == "year_range":
        if not isinstance(v, dict):
            return None
        a, b = _int(v.get("from")), _int(v.get("to"))
        if a is None and b is None:
            return None
        a, b = (a if a is not None else b), (b if b is not None else a)
        return {"from": min(a, b), "to": max(a, b)}
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
    """submit_result input -> {fields, overall_confidence, rejected_hypotheses, estimates}."""
    nameset = set(names)
    fields = empty_fields()
    for n in FIELD_NAMES:
        f = inp.get(n)
        if not isinstance(f, dict):
            continue
        fields[n] = {"value": _value(n, f.get("value"), nameset),
                     "confidence": _conf(f.get("confidence")),
                     "evidence": _evidence(f.get("evidence"))}
    # decade and year_range must agree; fill one from the other
    yr, dec = fields["year_range"]["value"], fields["decade"]["value"]
    if dec is None and yr:
        mid = (yr["from"] + yr["to"]) // 2
        fields["decade"]["value"] = mid - mid % 10
    if "overall_confidence" in inp:
        overall = _conf(inp["overall_confidence"])
    else:
        overall = round((fields["municipality"]["confidence"] + fields["decade"]["confidence"]) / 2, 3)
    rejected = [{"field": str(r.get("field")), "value": str(r.get("value")), "reason": str(r.get("reason"))}
                for r in inp.get("rejected_hypotheses") or [] if isinstance(r, dict) and r.get("reason")]
    year = _int(inp.get("year_best"))
    if year is None and yr:
        year = (yr["from"] + yr["to"]) // 2
    return {
        "fields": fields,
        "overall_confidence": overall,
        "rejected_hypotheses": rejected,
        "estimates": {"year": year, "place_name_printed": inp.get("place_name_printed")},
    }


def fallback(reason: str) -> dict:
    """Result body when the model never submitted: everything unknown, confidence 0."""
    out = {"fields": copy.deepcopy(empty_fields()), "overall_confidence": 0.0,
           "rejected_hypotheses": [], "estimates": {"year": None, "place_name_printed": None}}
    out["fields"]["municipality"]["evidence"] = [{"kind": "visual_cue", "summary": reason, "supports": False}]
    return out
