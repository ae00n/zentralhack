"""The agent loop. Single entry point used by the CLI, the server and the eval runner.

One photo in: image (max 1024 px) plus date hints and the dating checklist in the prompt, then a tool
loop (similar_images, archive_lookup, swisstopo_search) until the model calls submit_result, the tool
budget (MAX_STEPS) is used up, or the per-photo cost guard (PHOTO_BUDGET_USD) is hit. In the last two
cases the model gets one more turn to submit. Out: an AnalysisResult (CONTRACTS section 3).
"""

import copy
import hashlib
import json
import logging
import os
import secrets
import time
from collections.abc import Callable
from datetime import datetime, timezone

import data_pipeline as dp

from . import config, llm, prompts
from .config import FIXTURES, MAX_STEPS, MODEL, NEEDS_REVIEW_BELOW, PHOTO_BUDGET_USD
from .tools import SUBMIT, ToolContext, definitions, run_tool, submit
from .tools import dating
from .tools.base import image_block

log = logging.getLogger(__name__)

EFFORT = os.environ.get("AGENT_EFFORT", "medium")
MAX_TOKENS = 16000          # thinking counts toward this; enough for one turn at medium effort
IMAGE_PX = 1024
MAX_THOUGHT_CHARS = 2000


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
    # Raises llm.MissingKey (no key, before any call), llm.SessionBudgetExceeded (cost ledger past
    # SESSION_BUDGET_USD) and anthropic API errors after the SDK's retries; callers decide what to do.
    if config.FAKE:
        return _fake_result(photo_id, model, on_event)
    client = llm.make_client()
    parts = _parts(photo_id, image_path)
    if len(parts) >= 2:
        return _Composite(photo_id, image_path, parts, model, list(exclude_ids), on_event, client).execute()
    return _Run(photo_id, image_path, model, list(exclude_ids), on_event, client).execute()


MAX_PARTS = 12


def _parts(photo_id: str | None, image_path: str | None) -> list[tuple[str, str | None]]:
    """[(part_id, part_image_path or None)] for a composite card, else [].

    Archive cards were split ahead of time by data_pipeline (crop records `<id>#1`, `#2` with parent_id
    set), so only uploads are split here. A crop is never split again.
    """
    if photo_id and "#" in photo_id:
        return []
    if photo_id:
        crops = []
        for i in range(1, MAX_PARTS + 1):
            rec = dp.get_record(f"{photo_id}#{i}")
            if not rec or rec.get("parent_id") != photo_id:
                break
            crops.append((rec["id"], None))
        return crops
    try:
        items = dp.split_composite(image_path)
    except Exception:  # no splitter on this machine: treat the upload as one photo
        log.warning("split_composite failed for %s", image_path, exc_info=True)
        return []
    if len(items) < 2:
        return []
    uid = _upload_id(image_path)
    return [(f"{uid}#{i}", it["path"]) for i, it in enumerate(items[:MAX_PARTS], 1)]


def _fake_result(photo_id, model, on_event) -> dict:
    """AGENT_FAKE=1: replay the contract fixture, no Claude call (offline fallback, UI development)."""
    result = json.loads((FIXTURES / "analysis_result.json").read_text(encoding="utf-8"))
    result["photo_id"] = photo_id or "upload"
    result["model"] = model
    for item in result["trace"]:
        if on_event:
            on_event(copy.deepcopy(item))
    return result


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _upload_id(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return "upload:" + h.hexdigest()[:12]


class _Run:
    def __init__(self, photo_id, image_path, model, exclude_ids, on_event, client):
        self.model, self.on_event, self.client = model, on_event, client
        self.record = dp.get_record(photo_id) if photo_id else None
        if image_path is None:
            if photo_id is None:
                raise ValueError("analyze needs a photo_id or an image_path")
            if self.record is None:
                raise ValueError(f"unknown photo_id {photo_id!r} (data_pipeline.get_record returned None)")
            p = dp.image_file(self.record)
            if p is None or not p.exists():
                raise FileNotFoundError(f"no image on disk for {photo_id}: {p}")
            image_path = str(p)
        self.image_path = str(image_path)
        self.photo_id = photo_id or _upload_id(self.image_path)
        excl = ([photo_id] if photo_id else []) + [i for i in exclude_ids if i]
        self.ctx = ToolContext(photo_id=photo_id, image_path=self.image_path, exclude_ids=list(dict.fromkeys(excl)))
        self.run_id = f"{_now()}-{secrets.token_hex(2)}"
        self.trace: list[dict] = []
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                      "cache_creation_input_tokens": 0, "cost_usd": 0.0, "budget_hit": False}
        self.api_calls = 0

    # ---------- trace ----------

    def emit(self, item: dict) -> None:
        item = {"step": len(self.trace) + 1, **item}
        self.trace.append(item)
        if self.on_event:
            try:
                self.on_event(item)
            except Exception:  # a broken SSE consumer must not end the analysis
                log.exception("on_event failed")

    def _thoughts(self, content, ms: int) -> None:
        # Only the model's own text goes into the trace: it follows the German instruction, while the
        # API's thinking summaries come back in English and repeat what the next text block says.
        for b in content:
            text = (b.text or "").strip() if b.type == "text" else ""
            if text:
                self.emit({"type": "thought", "text": text[:MAX_THOUGHT_CHARS], "ms": ms})
                ms = 0

    # ---------- model ----------

    def _call(self, system, tools, messages):
        t0 = time.monotonic()
        resp, usd = llm.create(
            self.client, model=self.model, meta={"photo_id": self.photo_id, "run_id": self.run_id},
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=tools,
            tool_choice={"type": "auto"},  # forced tool choice is a 400 on the 5.5 models
            output_config={"effort": EFFORT},
            cache_control={"type": "ephemeral"},  # also cache the growing conversation between turns
            messages=messages,
        )
        self.api_calls += 1
        t = llm.usage_tokens(resp.usage)
        self.usage["input_tokens"] += t["input"] + t["cache_write"] + t["cache_read"]
        self.usage["cache_read_input_tokens"] += t["cache_read"]
        self.usage["cache_creation_input_tokens"] += t["cache_write"]
        self.usage["output_tokens"] += t["output"]
        self.usage["cost_usd"] = round(self.usage["cost_usd"] + usd, 6)
        return resp, round((time.monotonic() - t0) * 1000)

    # ---------- the loop ----------

    def execute(self) -> dict:
        names = submit.municipalities()
        tools = definitions(names)
        system = prompts.system(names, dating.checklist_text())

        hints, ms = self._timed(lambda: dating.hints(self.ctx))
        self.emit({"type": "tool_call", "tool": "date_hints", "input": {}, "output_summary": hints.summary, "ms": ms})
        kind = (self.record or {}).get("kind")
        messages = [{"role": "user", "content": [
            image_block(self.image_path, IMAGE_PX, 90),  # image first, then text
            {"type": "text", "text": prompts.first_turn(dating.hints_text(hints), kind, MAX_STEPS)},
        ]}]

        steps_used, final_turn, submitted, reason = 0, False, None, None
        while True:
            resp, ms = self._call(system, tools, messages)
            self._thoughts(resp.content, ms)
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            sub = next((b for b in tool_uses if b.name == SUBMIT), None)
            if sub is not None:
                submitted = dict(sub.input or {})
                break
            if resp.stop_reason == "refusal":
                reason = "Das Modell hat die Analyse abgelehnt; manuelle Prüfung nötig."
                break
            if final_turn:
                reason = "Das Modell hat keine Antwort eingereicht; manuelle Prüfung nötig."
                break

            messages.append({"role": "assistant", "content": resp.content})
            over_budget = self.usage["cost_usd"] >= PHOTO_BUDGET_USD
            if over_budget:
                self.usage["budget_hit"] = True

            if not tool_uses:  # end_turn or max_tokens without an answer: one nudge
                text = prompts.STOP_NOW_BUDGET if over_budget else prompts.NUDGE_SUBMIT
                messages.append({"role": "user", "content": [{"type": "text", "text": text}]})
                final_turn = True
                continue

            results = []
            for b in tool_uses:
                if over_budget or steps_used >= MAX_STEPS:
                    results.append({"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                                    "content": [{"type": "text", "text": prompts.SKIPPED_TOOL}]})
                    continue
                steps_used += 1
                out, tool_ms = run_tool(b.name, dict(b.input or {}), self.ctx)
                self.emit({"type": "tool_call", "tool": b.name, "input": dict(b.input or {}),
                           "output_summary": out.summary, "ms": tool_ms})
                note = f"(tool calls left: {MAX_STEPS - steps_used})"
                results.append({"type": "tool_result", "tool_use_id": b.id, "is_error": out.is_error,
                                "content": out.content(note)})
            if over_budget:
                results.append({"type": "text", "text": prompts.STOP_NOW_BUDGET})
                final_turn = True
            elif steps_used >= MAX_STEPS:
                results.append({"type": "text", "text": prompts.STOP_NOW_STEPS})
                final_turn = True
            messages.append({"role": "user", "content": results})

        return self._result(submitted, reason, names)

    def _timed(self, fn):
        t0 = time.monotonic()
        out = fn()
        return out, round((time.monotonic() - t0) * 1000)

    # ---------- result ----------

    def _result(self, submitted: dict | None, reason: str | None, names: list[str]) -> dict:
        body = submit.normalize(submitted, names) if submitted is not None else submit.fallback(reason)
        f = body["fields"]
        needs_review = (submitted is None
                        or f["municipality"]["confidence"] < NEEDS_REVIEW_BELOW
                        or f["decade"]["confidence"] < NEEDS_REVIEW_BELOW)
        self.emit({"type": "final", "text": _final_line(f, body["overall_confidence"], reason), "ms": 0})
        return {
            "photo_id": self.photo_id,
            "run_id": self.run_id,
            "status": "needs_review" if needs_review else "done",
            "model": self.model,
            "composite": None,  # a composite parent is built by _Composite from its parts
            "fields": f,
            "overall_confidence": body["overall_confidence"],
            "needs_review": needs_review,
            "rejected_hypotheses": body["rejected_hypotheses"],
            "trace": self.trace,
            "usage": {**self.usage, "api_calls": self.api_calls},
            "created_at": _now(),
            # extra keys (allowed by CONTRACTS): inputs for data_pipeline.metrics.score
            "estimates": body["estimates"],
        }


class _Composite:
    """A card with several pictures: each part is analysed on its own, the parent takes the fields of
    the most confident part and lists all parts in composite.parts (CONTRACTS section 3)."""

    def __init__(self, photo_id, image_path, parts, model, exclude_ids, on_event, client):
        self.photo_id = photo_id or _upload_id(image_path)
        self.parts, self.model, self.on_event, self.client = parts, model, on_event, client
        # siblings and the parent never count as evidence for a part
        self.exclude_ids = list(dict.fromkeys([self.photo_id, *(p for p, _ in parts), *exclude_ids]))
        self.trace: list[dict] = []

    def emit(self, item: dict, part: str | None = None) -> None:
        item = {**item, "step": len(self.trace) + 1}
        if part:
            item["part"] = part
        self.trace.append(item)
        if self.on_event:
            try:
                self.on_event(item)
            except Exception:
                log.exception("on_event failed")

    def execute(self) -> dict:
        n = len(self.parts)
        part_results = []
        for i, (pid, path) in enumerate(self.parts, 1):
            self.emit({"type": "thought", "text": f"Zusammengesetzte Karte: Teil {i} von {n} wird analysiert.",
                       "ms": 0}, pid)
            r = _Run(pid, path, self.model, self.exclude_ids, lambda item, pid=pid: self.emit(item, pid),
                     self.client).execute()
            part_results.append(r)
        best_i, best = max(enumerate(part_results, 1), key=lambda x: x[1]["overall_confidence"])
        self.emit({"type": "final", "ms": 0, "text": f"Zusammengesetzte Karte mit {n} Teilen, Ergebnis vom "
                   f"sichersten Teil {best_i}: {_final_line(best['fields'], best['overall_confidence'], None)}"})
        usage = {k: 0 for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                "cache_creation_input_tokens", "api_calls")}
        usage.update(cost_usd=0.0, budget_hit=False)
        for r in part_results:
            for k in usage:
                if k == "budget_hit":
                    usage[k] = usage[k] or r["usage"].get(k, False)
                elif k == "cost_usd":
                    usage[k] = round(usage[k] + r["usage"].get(k, 0.0), 6)
                else:
                    usage[k] += r["usage"].get(k, 0)
        return {
            **best,
            "photo_id": self.photo_id,
            "run_id": f"{_now()}-{secrets.token_hex(2)}",
            "composite": {"is_composite": True, "parts": [r["photo_id"] for r in part_results]},
            "trace": self.trace,
            "usage": usage,
            "created_at": _now(),
            "part_results": part_results,  # results.save writes each part to its own file
        }


def _final_line(f: dict, overall: float, reason: str | None) -> str:
    if reason:
        return reason
    muni = f["municipality"]["value"] or "Gemeinde unbekannt"
    place = f["place"]["value"]
    dec = f["decade"]["value"]
    when = f"{dec}er Jahre" if dec is not None else "Jahrzehnt unbekannt"
    where = f"{muni} ({place})" if place else muni
    return f"{where}, {when}, Konfidenz {overall:.2f}"
