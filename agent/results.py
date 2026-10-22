"""AnalysisResult cache: data/results/<photo_id>.json (CONTRACTS section 3 and 5)."""

import json
from pathlib import Path

from .config import RESULTS_DIR


def _path(photo_id: str) -> Path:
    # ids look like "stasz:514189" or "stasz:514189#1"; keep them readable but filesystem safe
    return RESULTS_DIR / (photo_id.replace("/", "_") + ".json")


def load(photo_id: str, model: str | None = None) -> dict | None:
    """Cached result, or None. With model set, only a result produced by that model counts."""
    p = _path(photo_id)
    if not p.exists():
        return None
    result = json.loads(p.read_text(encoding="utf-8"))
    if model and result.get("model") != model:
        return None
    return result


def save(result: dict) -> Path:
    """Write the result. A composite parent carries its parts in "part_results": each part gets its own
    file (so /results/<id>#1 works) and the parent file keeps only the part ids in composite.parts."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if "part_results" in result:
        for part in result["part_results"]:
            save(part)
        result = {k: v for k, v in result.items() if k != "part_results"}
    p = _path(result["photo_id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def all_results() -> list[dict]:
    if not RESULTS_DIR.exists():
        return []
    out = []
    for p in sorted(RESULTS_DIR.glob("*.json")):
        if p.name in ("eval_summary.json",):
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        if "photo_id" in r and "fields" in r:
            out.append(r)
    return out
