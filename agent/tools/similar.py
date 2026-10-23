"""similar_images: nearest archive photos to the query image (data_pipeline.similar_images).

Leakage rule (CONTRACTS 4): never return the query card, its crops, or anything in exclude_ids,
even if data_pipeline lets one through.
"""

import inspect
from collections import Counter

import data_pipeline as dp

from .base import ToolContext, ToolOutput, base_id, image_block, year_span

THUMBS = 3
THUMB_PX = 384
MAX_K = 12

DEFINITION = {
    "name": "similar_images",
    "description": (
        "Find the archive photos that look most like the query photo (the query image is passed "
        "automatically). Each hit has its catalogue municipality, place tags, year and, when checked, "
        "'verified' (a geometric match of the same scene; a verified hit shows the same place about 96% "
        "of the time). Unverified hits are only visually similar. The top 3 come back as thumbnails so you "
        "can compare them. Neighbour years are loose hints only."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "k": {"type": "integer", "description": "number of hits, 1 to 12 (default 8)"},
            "sources": {
                "type": ["array", "null"],
                "items": {"type": "string", "enum": ["staatsarchiv", "smapshot", "epics", "lubis", "nb"]},
                "description": "restrict to these collections, or null for all",
            },
        },
        "required": ["k", "sources"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _supports_verify() -> bool:
    # the stub has no verify parameter, the real api does
    return "verify" in inspect.signature(dp.similar_images).parameters


def _excluded(ctx: ToolContext) -> set[str]:
    bases = ctx.excluded_bases()
    if ctx.photo_id:
        rec = dp.get_record(ctx.photo_id)  # a merged alias id resolves to its canonical record
        if rec:
            bases.add(base_id(rec["id"]))
    return bases


def run(ctx: ToolContext, k: int = 8, sources: list[str] | None = None) -> ToolOutput:
    k = max(1, min(int(k or 8), MAX_K))
    excluded = _excluded(ctx)
    kwargs = {"k": k, "exclude_ids": sorted(set(ctx.exclude_ids) | excluded), "sources": sources or None}
    if _supports_verify():
        kwargs.update(model="fused", verify=True)
    raw = dp.similar_images(ctx.image_path, **kwargs)

    hits = []
    for h in raw:
        rec = h.get("record") or dp.get_record(h["id"]) or {}
        ids = {base_id(h["id"]), base_id(rec.get("id") or h["id"])}
        if rec.get("parent_id"):
            ids.add(base_id(rec["parent_id"]))
        if ids & excluded:
            continue  # leakage guard, independent of data_pipeline
        hits.append((h, rec))
    hits = hits[:k]

    data, images = [], []
    for i, (h, rec) in enumerate(hits, 1):
        loc = rec.get("location") or {}
        item = {
            "rank": i,
            "id": rec.get("id") or h["id"],
            "score": round(float(h.get("score", 0.0)), 4),
            "verified": h.get("verified"),
            "inliers": h.get("inliers"),
            "municipality": rec.get("municipality"),
            "places": (rec.get("places") or [])[:6],
            "title": rec.get("title"),
            "year": year_span(rec),
            "year_is_approximate": (rec.get("date") or {}).get("approximate"),
            "lat": loc.get("lat"),
            "lon": loc.get("lon"),
            "source": rec.get("source"),
        }
        data.append({k2: v for k2, v in item.items() if v is not None})
        if h.get("verified"):  # only geometrically verified hits count as a source (agent.confidence)
            ctx.verified_refs.update({item["id"], base_id(item["id"])})
        if i <= THUMBS:
            path = dp.image_file(rec) if rec else None
            if path and path.exists():
                label = f"Treffer {i}: {item['id']}, {item['municipality'] or 'Gemeinde unbekannt'}, {item['year'] or 'ohne Jahr'}"
                images += [{"type": "text", "text": label}, image_block(path, THUMB_PX, 80)]
    return ToolOutput({"hits": data, "n": len(data)}, _summary(data, k), images)


def _summary(hits: list[dict], k: int) -> str:
    if not hits:
        return "Keine ähnlichen Bilder gefunden"
    munis = Counter(h["municipality"] for h in hits if h.get("municipality"))
    parts = [f"{len(hits)} Treffer"]
    if munis:
        top, n = munis.most_common(1)[0]
        parts.append(f"{n} davon in {top}")
    verified = [h for h in hits if h.get("verified")]
    if verified:
        vm = Counter(h.get("municipality") or "?" for h in verified).most_common(1)[0][0]
        parts.append(f"{len(verified)} geometrisch bestätigt (v. a. {vm})")
    return ", ".join(parts)
