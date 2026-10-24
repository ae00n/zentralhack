"""archive_lookup: dated, labelled Staatsarchiv cards for a place / municipality / period."""

import data_pipeline as dp

from .base import ToolContext, ToolOutput, base_id, year_span

MAX_LIMIT = 20

DEFINITION = {
    "name": "archive_lookup",
    "description": (
        "Search dated, labelled Staatsarchiv Schwyz cards by place name (substring of the catalogue "
        "place tags and title), municipality (exact Gemeinde name) and year range (overlap). Use it to "
        "date a scene (when did a building first or last appear on dated cards of the same place) or to "
        "check that a place name exists in a municipality. Returns text only, no images."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "place": {"type": ["string", "null"], "description": "place or building name, e.g. 'Brunnen'"},
            "municipality": {"type": ["string", "null"], "description": "Gemeinde, e.g. 'Ingenbohl'"},
            "year_from": {"type": ["integer", "null"]},
            "year_to": {"type": ["integer", "null"]},
        },
        "required": ["place", "municipality", "year_from", "year_to"],
        "additionalProperties": False,
    },
    "strict": True,
}


def run(ctx: ToolContext, place: str | None = None, municipality: str | None = None,
        year_from: int | None = None, year_to: int | None = None) -> ToolOutput:
    if not any([place, municipality, year_from, year_to]):
        return ToolOutput({"error": "give at least one filter"}, "Archivsuche ohne Filter abgelehnt", is_error=True)
    excluded = ctx.excluded_bases()
    recs = dp.archive_lookup(place=place or None, municipality=municipality or None,
                             year_from=year_from, year_to=year_to, limit=MAX_LIMIT + len(excluded))
    recs = [r for r in recs if base_id(r["id"]) not in excluded][:MAX_LIMIT]
    data = [{
        "id": r["id"],
        "title": r.get("title"),
        "municipality": r.get("municipality"),
        "places": (r.get("places") or [])[:6],
        "year": year_span(r),
        "date_raw": (r.get("date") or {}).get("raw"),
    } for r in recs]
    return ToolOutput({"records": data, "n": len(data)}, _summary(data, place or municipality))


def _summary(data: list[dict], what: str | None) -> str:
    where = f" zu {what}" if what else ""
    if not data:
        return f"Keine datierten Archivkarten{where} gefunden"
    years = [int(str(d["year"]).split("-")[0]) for d in data if d.get("year")]
    span = f" {min(years)} bis {max(years)}" if years else ""
    return f"{len(data)} datierte Archivkarten{where}{span}"
