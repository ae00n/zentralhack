"""Shared types and helpers for the agent tools."""

import base64
import io
import json
from dataclasses import dataclass, field
from pathlib import Path


def base_id(photo_id: str) -> str:
    """"stasz:514189#2" -> "stasz:514189" (a composite card and its crops share the base)."""
    return photo_id.split("#", 1)[0]


@dataclass
class ToolContext:
    """What a tool may know about the current run. The query image is passed implicitly."""
    photo_id: str | None          # None for uploads
    image_path: str               # original file on disk (not the resized copy)
    exclude_ids: list[str] = field(default_factory=list)  # always includes photo_id when set
    tools_called: set[str] = field(default_factory=set)   # filled by run_tool; confidence only counts
                                                          # tool-backed evidence when the tool really ran

    def excluded_bases(self) -> set[str]:
        return {base_id(i) for i in self.exclude_ids}


@dataclass
class ToolOutput:
    data: object                   # structured result, sent to the model as JSON
    summary: str                   # short German line for the trace
    images: list[dict] = field(default_factory=list)  # content blocks (text labels + images) for the model
    is_error: bool = False

    def content(self, note: str | None = None) -> list[dict]:
        """tool_result content: JSON text first, then any images."""
        text = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"))
        if note:
            text += "\n" + note
        return [{"type": "text", "text": text}, *self.images]


def image_block(path: str | Path, max_px: int = 1024, quality: int = 88) -> dict:
    """Base64 JPEG image block, long edge at most max_px."""
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg",
                       "data": base64.standard_b64encode(buf.getvalue()).decode("ascii")}}


def year_span(rec: dict) -> str | None:
    d = rec.get("date") or {}
    a, b = d.get("year_from"), d.get("year_to")
    if a is None:
        return None
    return str(a) if a == b or b is None else f"{a}-{b}"
