"""Eval items (ground truth) from data/splits/eval.jsonl.

data_pipeline has no loader for the items themselves (only eval_ids()), so this reads the file the
same way data_pipeline.metrics does: read_jsonl(SPLITS / "eval.jsonl"). Item shape (CONTRACTS 1):
{id, subset, municipality, year_from, year_to, approximate, year_is_upper_bound}.
"""

from pathlib import Path

from data_pipeline.jsonl import read_jsonl
from data_pipeline.paths import SPLITS

SUBSETS = ("card_exact", "card_posted", "photo_dated")


def eval_file() -> Path:
    return SPLITS / "eval.jsonl"


def interleave(items: list[dict]) -> list[dict]:
    """Round robin over subsets, so a --limit or a cost-capped run still covers all three."""
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(it.get("subset") or "", []).append(it)
    out, lists = [], list(groups.values())
    for i in range(max((len(g) for g in lists), default=0)):
        out += [g[i] for g in lists if i < len(g)]
    return out


def load(path: Path | str | None = None, subsets: list[str] | None = None,
         limit: int | None = None) -> list[dict]:
    """Eval items, interleaved by subset, optionally filtered and cut to the first `limit`."""
    items = list(read_jsonl(Path(path) if path else eval_file()))
    if subsets:
        items = [it for it in items if it.get("subset") in subsets]
    items = interleave(items)
    return items[:limit] if limit else items
