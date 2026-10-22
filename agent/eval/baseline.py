"""Similarity-only baseline: no Claude call, so it is free.

municipality = majority vote over the municipalities of the top 5 similar_images hits that carry a
municipality. Ties go to the municipality whose best hit ranks higher. year = median of the hits'
year_from, range = min year_from .. max year_to (a by-product; the pitch number is municipality).

Leakage: similar_images gets exclude_ids = [photo_id] + eval_exclusions(photo_id), and any hit whose
id base (before "#") equals the query's is dropped again here, so a card and its crops never vote.

Predictions are cached in RESULTS_DIR/baseline.jsonl (one line per item, with the search settings),
so a rerun only searches items that are missing for the same settings.
"""

import json
import os
import statistics as st
from collections import Counter
from collections.abc import Callable

from .. import config

TOP = 5
SEARCH_K = 12  # ask for more than TOP: some hits get dropped (own crops, no municipality)
FILE = "baseline.jsonl"


def _base(photo_id: str) -> str:
    return photo_id.split("#", 1)[0]


def _stub() -> bool:
    return os.environ.get("DATA_PIPELINE_STUB") == "1"


def settings(model: str = "fused", verify: bool = True) -> dict:
    # stub.similar_images has no verify parameter, and nothing to verify against
    return {"model": model, "verify": bool(verify and not _stub()), "top": TOP}


def search(photo_id: str, model: str = "fused", verify: bool = True, k: int = SEARCH_K) -> list[dict]:
    """similar_images for an eval card with the eval exclusions applied."""
    import data_pipeline as dp
    from data_pipeline.dating import eval_exclusions

    rec = dp.get_record(photo_id)
    path = dp.image_file(rec) if rec else None
    if path is None or not path.exists():
        raise LookupError(f"kein Bild für {photo_id}")
    kw = {"k": k, "model": model, "exclude_ids": [photo_id] + eval_exclusions(photo_id)}
    if verify and not _stub():
        kw["verify"] = True
    return dp.similar_images(str(path), **kw)


def vote(photo_id: str, hits: list[dict], top: int = TOP) -> dict:
    """Prediction in metrics.score shape from ranked hits ([{id, score, record}])."""
    q = _base(photo_id)
    voters = []
    for h in hits:
        if _base(h["id"]) == q:
            continue
        rec = h.get("record") or {}
        if rec.get("municipality"):
            voters.append(h)
        if len(voters) == top:
            break
    counts, first = Counter(), {}
    for rank, h in enumerate(voters):
        m = h["record"]["municipality"]
        counts[m] += 1
        first.setdefault(m, rank)
    pred = {"id": photo_id, "municipality": None, "municipality_confidence": 0.0,
            "year": None, "year_low": None, "year_high": None,
            "votes": dict(counts), "neighbours": [h["id"] for h in voters]}
    if counts:
        winner = min(counts, key=lambda m: (-counts[m], first[m]))
        pred["municipality"] = winner
        pred["municipality_confidence"] = round(counts[winner] / len(voters), 3)
    dates = [(h["record"].get("date") or {}) for h in voters]
    years = [d["year_from"] for d in dates if d.get("year_from") is not None]
    if years:
        pred["year"] = int(st.median(years))
        pred["year_low"] = min(years)
        pred["year_high"] = max(d.get("year_to") or d["year_from"] for d in dates if d.get("year_from") is not None)
    return pred


def _path():
    return config.RESULTS_DIR / FILE


def load_cache(cfg: dict) -> dict[str, dict]:
    p = _path()
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("settings") == cfg and "id" in row:
            out[row["id"]] = row
    return out


def run(items: list[dict], *, model: str = "fused", verify: bool = True, compute: bool = True,
        log: Callable[[str], None] = print) -> dict[str, dict]:
    """Baseline predictions by id for the given eval items (cached ones are reused).

    compute=False only returns what is cached. Items that fail (no image, no index) are skipped.
    """
    cfg = settings(model, verify)
    cache = load_cache(cfg)
    todo = [it for it in items if it["id"] not in cache]
    if not compute or not todo:
        return {it["id"]: cache[it["id"]] for it in items if it["id"] in cache}
    log(f"Baseline ({cfg['model']}, verify={cfg['verify']}): {len(items) - len(todo)} im Cache, "
        f"{len(todo)} zu berechnen")
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    failed = 0
    with p.open("a", encoding="utf-8") as f:
        for i, it in enumerate(todo, 1):
            try:
                hits = search(it["id"], cfg["model"], cfg["verify"])
            except NotImplementedError as e:  # no index on this machine: every item would fail
                log(f"Baseline abgebrochen: {e}")
                break
            except Exception as e:  # noqa: BLE001  one bad item must not stop the baseline
                failed += 1
                if failed <= 5:
                    log(f"  Baseline {it['id']}: {type(e).__name__}: {e}")
                continue
            row = {**vote(it["id"], hits), "settings": cfg}
            cache[it["id"]] = row
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            if i % 25 == 0:
                log(f"  Baseline {i}/{len(todo)}")
    if failed:
        log(f"Baseline: {failed} Items ohne Vorhersage (kein Bild oder Suche fehlgeschlagen)")
    return {it["id"]: cache[it["id"]] for it in items if it["id"] in cache}


def accuracy(preds: dict[str, dict], items: list[dict]) -> tuple[float | None, int]:
    """(municipality accuracy, n) over the items that have a baseline prediction."""
    pairs = [(it, preds[it["id"]]) for it in items if it["id"] in preds]
    if not pairs:
        return None, 0
    return round(sum(p["municipality"] == it["municipality"] for it, p in pairs) / len(pairs), 3), len(pairs)
