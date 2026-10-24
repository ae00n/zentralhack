"""AnalysisResult cache: data/results/<photo_id>.json (CONTRACTS section 3 and 5).

A new run of the same photo replaces the cached result; the previous one moves to
data/results/history/<photo_id>/<run_id>.json, so every earlier analysis stays comparable.
"""

import json
from pathlib import Path

from .config import RESULTS_DIR


def _safe(photo_id: str) -> str:
    # ids look like "stasz:514189" or "stasz:514189#1"; keep them readable but filesystem safe
    return photo_id.replace("/", "_")


def _path(photo_id: str) -> Path:
    return RESULTS_DIR / (_safe(photo_id) + ".json")


def _history_dir(photo_id: str) -> Path:
    return RESULTS_DIR / "history" / _safe(photo_id)


def archive(photo_id: str) -> Path | None:
    """Copy the cached result into the history (no-op when there is none or it is already there)."""
    p = _path(photo_id)
    if not p.exists():
        return None
    old = json.loads(p.read_text(encoding="utf-8"))
    dest = _history_dir(photo_id) / (_safe(old.get("run_id") or "unknown") + ".json")
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def add_history(result: dict) -> Path:
    """Write a run straight into the history without making it the current result (the runs of a
    consistency check that were not kept). A composite parent's parts go into their own histories."""
    for part in result.get("part_results") or []:
        add_history(part)
    result = {k: v for k, v in result.items() if k != "part_results"}
    dest = _history_dir(result["photo_id"]) / (_safe(result.get("run_id") or "unknown") + ".json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def history(photo_id: str) -> list[dict]:
    """Every result of this photo, oldest first, the current one last."""
    out = [json.loads(p.read_text(encoding="utf-8")) for p in _history_dir(photo_id).glob("*.json")] \
        if _history_dir(photo_id).exists() else []
    current = load(photo_id)
    if current:
        out = [r for r in out if r.get("run_id") != current.get("run_id")]
    out.sort(key=lambda r: r.get("created_at") or "")
    return out + [current] if current else out


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
    if p.exists() and json.loads(p.read_text(encoding="utf-8")).get("run_id") != result.get("run_id"):
        archive(result["photo_id"])  # a new run: keep the previous one (a review keeps its run_id)
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
