"""Confidence method (CHALLENGE_BRIEF section 4). The model names values and their evidence; the numbers
come from counting independent supporting sources, so every score can be explained in one sentence.

Per field: 1 independent source 0.5, 2 sources 0.7, 3 sources 0.85, 4 or more 0.95. Any evidence against
the value caps it at 0.6. An unknown value (null or []) is 0. Overall = the lower of locality and
municipality, plus 0.05 when buildings and street are determined too. needs_review below 0.9 or when
locality or municipality is unknown.
"""

FIELDS = ["locality", "municipality", "buildings", "landscape_features", "street"]
CORE = ("locality", "municipality")
SCALE = {1: 0.5, 2: 0.7, 3: 0.85}
TOP = 0.95
CONTRADICTED_CAP = 0.6
AGREE_BONUS = 0.05
ACCEPT = 0.9

# Evidence that claims a tool result only counts when that tool really ran in this analysis.
NEEDS_TOOL = {
    "similar_image": "similar_images",
    "archive_record": "archive_lookup",
    "swisstopo_place": "swisstopo_search",
    "address_register": "address_lookup",
    "named_building": "named_buildings",
    "terrain": "terrain_check",
}

LABEL = {
    "visual_cue": "Bildinhalt",
    "text_on_card": "Text im Bild",
    "similar_image": "Referenzfoto",
    "archive_record": "Archivdatensatz",
    "swisstopo_place": "swisstopo-Ortsname",
    "terrain": "Geländeprüfung",
    "map_layer": "Karte",
    "address_register": "Gebäudeadressverzeichnis",
    "named_building": "OSM-Gebäude",
    "exif": "EXIF-GPS",
    "session_photo": "Session-Foto",
}

FIELD_LABEL = {"locality": "Ortschaft", "municipality": "Gemeinde", "buildings": "Gebäude",
               "landscape_features": "See/Fluss/Berg", "street": "Strasse"}


def _known(value) -> bool:
    return value not in (None, "", [])


def counted(evidence: list[dict], tools_called: set[str], allowed: set[str] = frozenset()) -> list[dict]:
    """Supporting evidence that counts, one item per independent source (kind + reference)."""
    seen, out = set(), []
    for e in evidence:
        if e.get("supports") is False:
            continue
        kind = e.get("kind")
        tool = NEEDS_TOOL.get(kind)
        if tool and tool not in tools_called:
            continue
        if kind in ("session_photo", "exif") and kind not in allowed:
            continue
        key = (kind, e.get("ref_id") or e.get("url") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def score_field(field: dict, tools_called: set[str], allowed: set[str] = frozenset()) -> tuple[float, list[dict]]:
    if not _known(field.get("value")):
        return 0.0, []
    support = counted(field.get("evidence") or [], tools_called, allowed)
    if not support:
        return 0.0, []
    score = SCALE.get(len(support), TOP)
    if any(e.get("supports") is False for e in field.get("evidence") or []):
        score = min(score, CONTRADICTED_CAP)
    return score, support


def apply(fields: dict, tools_called: set[str], allowed: set[str] = frozenset()) -> dict:
    """Set every field's confidence from its evidence. Returns {overall, needs_review, explanation}.

    allowed: evidence kinds that need no tool but must be real for this photo ("session_photo" when a
    session sibling result was given, "exif" when the record has EXIF GPS).
    """
    support = {}
    for name, f in fields.items():
        if name not in FIELDS:
            continue
        f["confidence"], support[name] = score_field(f, tools_called, allowed)
        if f["confidence"] == 0.0:  # no backing source: unknown, never a guess (brief: null + 0)
            f["value"] = [] if isinstance(f.get("value"), list) else None
    core = [fields[n]["confidence"] for n in CORE if n in fields]
    overall = min(core) if core else 0.0
    if overall > 0 and fields.get("buildings", {}).get("confidence", 0) > 0 \
            and fields.get("street", {}).get("confidence", 0) > 0:
        overall = min(1.0, overall + AGREE_BONUS)
    overall = round(overall, 3)
    unknown = [n for n in CORE if not _known(fields.get(n, {}).get("value"))]
    return {"overall": overall, "needs_review": overall < ACCEPT or bool(unknown),
            "explanation": explain(fields, support)}


def explain(fields: dict, support: dict) -> str:
    """One German sentence: how many independent sources back the core fields, and what stays open."""
    parts = []
    for name in CORE:
        src = support.get(name) or []
        if not src:
            continue
        kinds = ", ".join(dict.fromkeys(LABEL.get(e.get("kind"), e.get("kind")) for e in src))
        n = len(src)
        word = "einer Quelle" if n == 1 else f"{n} unabhängigen Quellen"
        capped = " (mit Widerspruch)" if any(e.get("supports") is False for e in fields[name].get("evidence") or []) else ""
        parts.append(f"{FIELD_LABEL[name]} durch {word} gestützt ({kinds}){capped}")
    # same sources for Ortschaft and Gemeinde: say it once
    if len(parts) == 2 and support.get("locality") == support.get("municipality"):
        parts = [parts[1].replace("Gemeinde durch", "Ortschaft und Gemeinde durch")]
    open_fields = [FIELD_LABEL[n] for n in FIELDS if n in fields and not _known(fields[n].get("value"))]
    if open_fields:
        parts.append(", ".join(open_fields) + " nicht bestimmbar")
    if not parts:
        return "Keine Angabe durch eine Quelle gestützt."
    return "; ".join(parts) + "."
