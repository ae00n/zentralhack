"""The agent loop. Single entry point used by the CLI, the server and the eval runner.

One photo in: image (max 1024 px) plus the photo's own facts (EXIF, session siblings' results) in the
prompt, then a tool loop (similar_images, named_buildings, address_lookup, swisstopo_search, archive_lookup,
terrain_check) until the model calls submit_result, the tool budget (MAX_STEPS) is used up, or the per-photo
cost guard (PHOTO_BUDGET_USD) is hit. In the last two cases the model gets one more turn to submit. The
confidences come from agent.confidence (count of independent sources), not from the model. Out: an
AnalysisResult (CONTRACTS section 3, v3 fields).
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

from . import confidence, config, llm, prompts, results
from .config import FIXTURES, MAX_STEPS, MODEL, PHOTO_BUDGET_USD
from .tools import SUBMIT, ToolContext, definitions, run_tool, submit
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
    if config.PIPELINE == 5:
        from . import v5

        return v5.analyze(photo_id, image_path, model=model, exclude_ids=exclude_ids, on_event=on_event)
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
        exif = ((self.record or {}).get("raw") or {}).get("exif") or {}
        if isinstance(exif.get("focal_35mm"), (int, float)) and exif["focal_35mm"] > 0:
            self.ctx.focal_35mm = float(exif["focal_35mm"])
        size = (self.record or {}).get("image") or {}
        self.ctx.portrait = bool(size.get("height") and size.get("width") and size["height"] > size["width"])
        if (self.record or {}).get("source") == "challenge":  # the EXIF date of a handed-out photo
            self.ctx.year = ((self.record.get("date") or {}).get("year_from"))
            self.ctx.captured = exif.get("datetime")
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
        system = prompts.system(names)

        kind = (self.record or {}).get("kind")
        messages = [{"role": "user", "content": [
            image_block(self.image_path, IMAGE_PX, 90),  # image first, then text
            {"type": "text", "text": prompts.first_turn(self._context(), kind, MAX_STEPS)},
            *self._session_images(),
        ]}]

        steps_used, final_turn, submitted, reason = 0, False, None, None
        while True:
            resp, ms = self._call(system, tools, messages)
            self._thoughts(resp.content, ms)
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            sub = next((b for b in tool_uses if b.name == SUBMIT), None)
            if sub is not None:
                submitted = dict(sub.input or {})
                look = self._second_look(submitted, names, tool_uses, steps_used, final_turn)
                if look:
                    messages.append({"role": "assistant", "content": resp.content})
                    messages.append({"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": sub.id, "content": [{"type": "text", "text": look}]}]})
                    continue
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

    def _second_look(self, submitted: dict, names: list[str], tool_uses, steps_used: int, final_turn: bool) -> str | None:
        """Once per analysis: when the answer would score below the acceptance line and there is room left,
        tell the model which fields are weak and let it check alternatives before the final answer."""
        if (getattr(self, "looked_twice", False) or final_turn or len(tool_uses) != 1
                or MAX_STEPS - steps_used < SECOND_LOOK_MIN_STEPS
                or self.usage["cost_usd"] >= PHOTO_BUDGET_USD * SECOND_LOOK_MAX_BUDGET_SHARE):
            return None
        body = submit.normalize(copy.deepcopy(submitted), names)
        scored = confidence.apply(body["fields"], self.ctx.tools_called, getattr(self, "allowed", set()),
                                  self.ctx.verified_refs)
        if scored["overall"] >= confidence.ACCEPT:
            return None
        weak = [(label, body["fields"][n]["confidence"]) for n, label in confidence.FIELD_LABEL.items()
                if body["fields"][n]["confidence"] < SECOND_LOOK_WEAK]
        if not weak:
            return None
        self.looked_twice = True
        listing = ", ".join(f"{label} {c:.2f}" for label, c in weak)
        self.emit({"type": "thought", "ms": 0,
                   "text": f"Vorläufige Gesamtkonfidenz {scored['overall']:.2f}, unter 0.90: zweite Prüfung ({listing})."})
        return prompts.second_look(scored["overall"], listing, MAX_STEPS - steps_used)

    def _session_images(self) -> list[dict]:
        """The other photos of the same session (same camera, under 30 minutes): usually the same place from
        another angle, often with the sign or building this photo lacks. Shown as images, answered or not."""
        out = []
        for sid in ((self.record or {}).get("raw") or {}).get("session", [])[:SESSION_IMAGES]:
            try:
                path = dp.image_file(dp.get_record(sid))
            except Exception:
                path = None
            if path and path.exists():
                out += [{"type": "text", "text": f"Session-Foto {sid} (gleiche Kamera, unter 30 Minuten Abstand; "
                                                 "evidence kind session_photo mit ref_id, wenn es den Ort belegt):"},
                        image_block(path, SESSION_PX, 80)]
        if out:
            self.allowed.add("session_photo")
        return out

    def _register_check(self, f: dict) -> None:
        """Our own check after the answer (no model call): what does the official register say at the
        answer's coordinates? The same Ortschaft / Gemeinde adds a source, a different one is a real
        counter-source. Skipped when the coordinates are too rough to decide."""
        c = (f.get("coordinates") or {}).get("value") or {}
        if c.get("lat") is None or (c.get("radius_m") or 0) > REGISTER_CHECK_MAX_RADIUS_M:
            return
        try:
            a = dp.address_lookup(c["lat"], c["lon"], radius_m=100, limit=1)
        except Exception:
            log.warning("register check failed", exc_info=True)
            return
        if not (a.get("ortschaft") or a.get("municipality")):
            return  # nothing at that point to compare with
        for name, official in (("locality", a.get("ortschaft")), ("municipality", a.get("municipality"))):
            given = f[name]["value"]
            if not given or not official:
                continue
            same = _same_place(given, official)
            label = "Ortschaft" if name == "locality" else "Gemeinde"
            summary = (f"Automatische Prüfung: das amtliche Verzeichnis nennt am Antwortpunkt dieselbe {label} ({official})."
                       if same else
                       f"Automatische Prüfung: das amtliche Verzeichnis nennt am Antwortpunkt {label} {official}, nicht {given}.")
            # "auto": run by our code, so it counts without the model having called address_lookup
            f[name]["evidence"].append({"kind": "address_register", "summary": summary, "supports": same, "auto": True})
        self.emit({"type": "tool_call", "tool": "address_lookup", "input": {"lat": c["lat"], "lon": c["lon"], "auto": True},
                   "output_summary": f"Automatische Prüfung am Antwortpunkt: {a.get('ortschaft') or '?'}, "
                                     f"Gemeinde {a.get('municipality') or '?'}", "ms": 0})

    def _context(self) -> str:
        """Facts about the photo that are not the answer: file name, EXIF date and camera, EXIF GPS, and the
        results of photos from the same session. Catalogue titles and places are never given (they are
        the answer for archive photos)."""
        rec = self.record or {}
        raw = rec.get("raw") or {}
        lines, self.allowed = [], set()
        if rec.get("source") == "challenge":
            exif = raw.get("exif") or {}
            lines.append(f"File: {raw.get('file_name') or rec.get('signature')}")
            if (rec.get("date") or {}).get("raw"):
                lines.append(f"Captured (EXIF): {rec['date']['raw']}, camera {exif.get('make') or '?'} "
                             f"{exif.get('model') or ''}".rstrip())
            if exif.get("lat") is not None and exif.get("lon") is not None:
                lines.append(f"EXIF GPS: lat {exif['lat']}, lon {exif['lon']} (evidence kind exif)")
                self.allowed.add("exif")
        siblings = []
        for sid in raw.get("session") or []:
            r = results.load(sid)
            f = (r or {}).get("fields") or {}
            if not r or not (f.get("municipality") or {}).get("value"):
                continue
            def val(n):
                v = (f.get(n) or {}).get("value")
                return ", ".join(v) if isinstance(v, list) else v
            parts = [f"{label} {val(n)}" for n, label in (("locality", "Ortschaft"), ("municipality", "Gemeinde"),
                                                          ("buildings", "Gebäude"), ("street", "Strasse")) if val(n)]
            siblings.append(f"- {sid}: {', '.join(parts)} (Gesamtkonfidenz {r.get('overall_confidence', 0):.2f})")
        if siblings:
            lines.append("Photos from the same session (same camera, under 30 minutes apart, usually the same "
                         "place; cite as evidence kind session_photo with ref_id, and still check what differs):")
            lines += siblings
            self.allowed.add("session_photo")
        return "\n".join(lines) if lines else "No metadata for this photo."

    def _timed(self, fn):
        t0 = time.monotonic()
        out = fn()
        return out, round((time.monotonic() - t0) * 1000)

    # ---------- result ----------

    def _result(self, submitted: dict | None, reason: str | None, names: list[str]) -> dict:
        body = submit.normalize(submitted, names) if submitted is not None else submit.fallback(reason)
        f = body["fields"]
        if submitted is not None:
            self._register_check(f)
        allowed = getattr(self, "allowed", set())
        verified = self.ctx.verified_refs
        scored = confidence.apply(f, self.ctx.tools_called, allowed, verified)
        f["coordinates"]["confidence"] = confidence.score_field(f["coordinates"], self.ctx.tools_called, allowed,
                                                                verified)[0]
        if f["coordinates"]["confidence"] == 0.0:
            f["coordinates"]["value"] = None
        needs_review = submitted is None or scored["needs_review"]
        explanation = reason if submitted is None else scored["explanation"]
        self.emit({"type": "final", "text": _final_line(f, scored["overall"], reason), "ms": 0})
        return {
            "photo_id": self.photo_id,
            "run_id": self.run_id,
            "status": "needs_review" if needs_review else "done",
            "model": self.model,
            "composite": None,  # a composite parent is built by _Composite from its parts
            "fields": f,
            "overall_confidence": scored["overall"],
            "confidence_explanation": explanation,
            "needs_review": needs_review,
            "review": None,
            "rejected_hypotheses": body["rejected_hypotheses"],
            "trace": self.trace,
            "usage": {**self.usage, "api_calls": self.api_calls},
            "created_at": _now(),
            # extra keys (allowed by CONTRACTS): inputs for data_pipeline.metrics.score, and the settings
            # that produced this result (the report compares runs by them)
            "estimates": body["estimates"],
            "settings": {"effort": EFFORT, "max_steps": MAX_STEPS, "photo_budget_usd": PHOTO_BUDGET_USD},
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


SESSION_IMAGES, SESSION_PX = 3, 640
SECOND_LOOK_MIN_STEPS = 2          # tool calls that must be left for a second look to be worth it
SECOND_LOOK_MAX_BUDGET_SHARE = 0.75  # no second look once 75% of the per-photo budget is spent
SECOND_LOOK_WEAK = 0.85            # fields below this are named as weak
REGISTER_CHECK_MAX_RADIUS_M = 1500  # coarser coordinates cannot decide a Gemeinde boundary


def _same_place(a: str, b: str) -> bool:
    """'Küssnacht (SZ)' == 'Küssnacht', 'Stoos SZ' == 'Stoos'."""
    def norm(x: str) -> str:
        x = x.casefold().replace("(sz)", "").strip()
        return x[:-3].strip() if x.endswith(" sz") else x
    return norm(a) == norm(b)


def _final_line(f: dict, overall: float, reason: str | None) -> str:
    if reason:
        return reason
    def val(n):
        v = f[n]["value"]
        return ", ".join(v) if isinstance(v, list) else v
    parts = [val(n) for n in ("locality", "buildings", "street") if val(n)]
    if f["municipality"]["value"] and f["municipality"]["value"] != f["locality"]["value"]:
        parts.insert(1, f"Gemeinde {f['municipality']['value']}")
    where = ", ".join(parts) if parts else "Ort nicht bestimmbar"
    return f"{where}, Konfidenz {overall:.2f}"
