"""Tool registry: the JSON definitions sent to Claude and the dispatcher that runs them.

Each tool module has DEFINITION (or definition()) and run(ctx, **input) -> ToolOutput.
The order of definitions() is fixed so the tools block stays byte-identical across calls (prompt cache).
"""

import time

from . import archive, nearby, places, similar, submit, swisstopo, terrain, viewpoint, views
from .base import ToolContext, ToolOutput

_RUNNERS = {
    "similar_images": similar.run,
    "archive_lookup": archive.run,
    "swisstopo_search": swisstopo.run,
    "terrain_check": terrain.run,
    "address_lookup": places.run_address_lookup,
    "named_buildings": places.run_named_buildings,
    "viewpoint_search": viewpoint.run,
    "photos_near": nearby.run,
    "aerial_view": views.run_aerial,
    "skyline": views.run_skyline,
}

SUBMIT = submit.NAME


def definitions(municipalities: list[str]) -> list[dict]:
    return [similar.DEFINITION, places.NAMED_BUILDINGS, places.ADDRESS_LOOKUP, swisstopo.DEFINITION,
            viewpoint.DEFINITION, nearby.DEFINITION, views.AERIAL_VIEW, views.SKYLINE, archive.DEFINITION,
            terrain.DEFINITION,
            submit.definition(municipalities)]


def run_tool(name: str, tool_input: dict, ctx: ToolContext) -> tuple[ToolOutput, int]:
    """Run one tool. Returns (output, ms). Unknown tools and tool failures become error outputs."""
    t0 = time.monotonic()
    fn = _RUNNERS.get(name)
    if fn is None:
        out = ToolOutput({"error": f"unknown tool {name}"}, f"Unbekanntes Werkzeug {name}", is_error=True)
    else:
        try:
            ctx.tools_called.add(name)
            out = fn(ctx, **(tool_input or {}))
        except Exception as e:  # a broken tool must not end the run; the model sees the error
            out = ToolOutput({"error": f"{type(e).__name__}: {e}"}, f"Fehler in {name}: {type(e).__name__}",
                             is_error=True)
    return out, round((time.monotonic() - t0) * 1000)


__all__ = ["SUBMIT", "ToolContext", "ToolOutput", "definitions", "run_tool"]
