"""The agent loop. Single entry point used by the CLI, the server and the eval runner.

Placeholder until the real loop lands: it returns the fixture result with the requested photo_id,
so the server and eval runner can be built against the final signature.
"""

import json
from collections.abc import Callable

from .config import FIXTURES, MODEL


def analyze(photo_id: str | None = None, image_path: str | None = None, *,
            model: str = MODEL, exclude_ids: list[str] = (),
            on_event: Callable[[dict], None] | None = None) -> dict:
    """Analyse one photo and return an AnalysisResult (CONTRACTS section 3).

    photo_id: an archive id (image comes from data_pipeline), or None for an upload given by image_path.
    exclude_ids: extra ids to hide from tools (eval runs pass eval_exclusions(photo_id)); the photo's
        own id is always excluded.
    on_event: called with each trace item as it happens (for SSE).
    Does not read or write the results cache; callers do that.
    """
    result = json.loads((FIXTURES / "analysis_result.json").read_text(encoding="utf-8"))
    result["photo_id"] = photo_id or "upload"
    result["model"] = model
    for item in result["trace"]:
        if on_event:
            on_event(item)
    return result
