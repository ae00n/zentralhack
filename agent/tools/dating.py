"""Dating aids that need no model call: date_hints for the photo and the visual rule_checklist.

Both go straight into the prompt; date_hints is also shown as the first tool step in the trace.
"""

from data_pipeline.dating import date_hints, rule_checklist

from .base import ToolContext, ToolOutput


def hints(ctx: ToolContext) -> ToolOutput:
    """date_hints with the run's exclusions (the photo's own id is always in ctx.exclude_ids)."""
    try:
        hs = date_hints(photo_id=ctx.photo_id, image_path=ctx.image_path, exclude_ids=list(ctx.exclude_ids))
    except Exception as e:  # missing index or model must not kill the run
        return ToolOutput({"hints": [], "error": f"{type(e).__name__}: {e}"},
                          "Datierungshinweise nicht verfügbar", is_error=True)
    keep = ("kind", "year", "year_low", "year_high", "weight", "evidence")
    data = [{k: h.get(k) for k in keep} for h in hs]
    return ToolOutput({"hints": data}, _summary(data))


def _summary(hs: list[dict]) -> str:
    if not hs:
        return "Keine Datierungshinweise gefunden"
    top = hs[0]
    lo, hi, y = top.get("year_low"), top.get("year_high"), top.get("year")
    span = f"{lo} bis {hi}" if lo and hi else (f"um {y}" if y else (f"bis {hi}" if hi else "ohne Jahr"))
    return f"{len(hs)} Datierungshinweise, stärkster ({top['kind']}): {span}"


def checklist_text() -> str:
    """rule_checklist as compact lines for the system prompt (stable across photos, so it caches)."""
    lines = []
    for r in rule_checklist():
        lo = r.get("year_min") if r.get("year_min") is not None else "?"
        hi = r.get("year_max") if r.get("year_max") is not None else "?"
        lines.append(f"- [{r['id']}] {r['feature']}: {lo} to {hi} ({r.get('confidence')}, {r.get('category')})")
    return "\n".join(lines)


def hints_text(out: ToolOutput) -> str:
    hs = (out.data or {}).get("hints") or []
    if not hs:
        return "No date hints are available for this photo."
    lines = []
    for h in hs:
        rng = f"{h.get('year_low') or '?'}-{h.get('year_high') or '?'}"
        best = f", best {h['year']}" if h.get("year") else ""
        lines.append(f"- {h['kind']} (weight {h.get('weight')}): {rng}{best}. {h.get('evidence')}")
    return "\n".join(lines)
