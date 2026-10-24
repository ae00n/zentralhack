"""Single entry point used by the CLI and the server: one photo in, one AnalysisResult (CONTRACTS section 3) out.

The analysis itself is agent.v7 (three attempts, registers, image check at the spot, judge, tiers) for a
known photo, and agent.v6 for an upload (v7 needs the record: EXIF, session, precomputed matches).
AGENT_FAKE=1 replays the contract fixture instead, with no Claude call (offline fallback, UI development).
"""

import copy
import json
from collections.abc import Callable

from . import config, v6
from .v7 import pipeline as v7
from .config import FIXTURES, MODEL


def analyze(photo_id: str | None = None, image_path: str | None = None, *,
            model: str = MODEL, exclude_ids: list[str] = (),
            on_event: Callable[[dict], None] | None = None) -> dict:
    """photo_id: a challenge or archive id (image comes from data_pipeline), or None for an upload given by
    image_path. on_event: called with each trace item as it happens (for SSE). Does not read or write the
    results cache; callers do that. Raises llm.MissingKey, llm.SessionBudgetExceeded and API errors."""
    if photo_id is None and image_path is None:
        raise ValueError("analyze needs a photo_id or an image_path")
    if config.FAKE:
        return _fake_result(photo_id, model, on_event)
    if photo_id is not None:
        return v7.analyze(photo_id, model=model, on_event=on_event)
    return v6.analyze(photo_id, image_path, model=model, exclude_ids=exclude_ids, on_event=on_event)


def _fake_result(photo_id, model, on_event) -> dict:
    result = json.loads((FIXTURES / "analysis_result.json").read_text(encoding="utf-8"))
    result["photo_id"] = photo_id or "upload"
    result["model"] = model
    for item in result["trace"]:
        if on_event:
            on_event(copy.deepcopy(item))
    return result
