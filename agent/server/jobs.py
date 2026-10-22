"""Analysis jobs: one background thread per job, trace items buffered for SSE replay."""

import json
import secrets
import threading
import time
from datetime import datetime, timezone

import anthropic

from .. import config, llm, loop, results

# AGENT_FAKE replay: seconds between trace items (tests set it to ~0)
FAKE_DELAY_S = 0.3
MAX_JOBS = 500


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_id() -> str:
    return f"{_now()}-{secrets.token_hex(2)}"


class Job:
    def __init__(self, photo_id: str, model: str):
        self.id = secrets.token_hex(8)
        self.photo_id = photo_id
        self.model = model
        self.run_id = _run_id()
        self.created_at = _now()
        self.trace: list[dict] = []
        self.result: dict | None = None
        self._lock = threading.Lock()

    @property
    def done(self) -> bool:
        return self.result is not None

    def push(self, item: dict) -> None:
        with self._lock:
            self.trace.append(item)

    def finish(self, result: dict) -> None:
        with self._lock:
            self.result = result

    def fail(self, message: str, detail: str | None = None) -> None:
        r = self._partial("error")
        r["error"] = message  # German, shown in the UI
        if detail:
            r["error_detail"] = detail
        self.finish(r)

    def since(self, i: int) -> tuple[list[dict], dict | None]:
        """Trace items from index i on, plus the final result once the job is done."""
        with self._lock:
            return list(self.trace[i:]), self.result

    def _partial(self, status: str) -> dict:
        return {
            "photo_id": self.photo_id, "run_id": self.run_id, "status": status, "model": self.model,
            "composite": None, "fields": {}, "overall_confidence": 0.0, "needs_review": True,
            "rejected_hypotheses": [], "trace": list(self.trace),
            "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "budget_hit": False},
            "created_at": self.created_at,
        }

    def snapshot(self) -> dict:
        with self._lock:
            return self.result if self.result is not None else self._partial("running")


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def _register(job: Job) -> Job:
    with _jobs_lock:
        _jobs[job.id] = job
        while len(_jobs) > MAX_JOBS:
            _jobs.pop(next(iter(_jobs)))
    return job


def latest_result(photo_id: str) -> dict | None:
    """Newest finished in-memory result for a photo (fake runs are not written to the cache)."""
    for job in reversed(list(_jobs.values())):
        if job.photo_id == photo_id and job.result and job.result.get("status") != "error":
            return job.result
    return None


def memory_results() -> list[dict]:
    seen, out = set(), []
    for job in reversed(list(_jobs.values())):
        r = job.result
        if r and r.get("status") != "error" and job.photo_id not in seen:
            seen.add(job.photo_id)
            out.append(r)
    return out


def submit(photo_id: str, *, image_path: str | None = None, fresh: bool = False,
           fake: bool | None = None) -> Job:
    """Start (or reuse) an analysis job. A cached result gives a job that is already done."""
    fake = config.FAKE if fake is None else fake
    if not fresh:
        cached = results.load(photo_id)
        if cached:
            job = Job(photo_id, cached.get("model", config.MODEL))
            job.trace = list(cached.get("trace") or [])
            job.result = cached
            return _register(job)
    for job in reversed(list(_jobs.values())):
        if job.photo_id == photo_id and not job.done:
            return job  # already running: share it
    job = _register(Job(photo_id, config.MODEL))
    target = _run_fake if fake else _run_real
    threading.Thread(target=target, args=(job, image_path), daemon=True, name=f"job-{job.id}").start()
    return job


def _run_fake(job: Job, image_path: str | None) -> None:
    fx = json.loads((config.FIXTURES / "analysis_result.json").read_text(encoding="utf-8"))
    try:
        for item in fx["trace"]:
            time.sleep(FAKE_DELAY_S)
            job.push(item)
        time.sleep(FAKE_DELAY_S)
        job.finish({**fx, "photo_id": job.photo_id, "run_id": job.run_id, "created_at": _now()})
    except Exception as e:  # noqa: BLE001
        job.fail(f"{type(e).__name__}: {e}")


def _german_error(e: Exception) -> str:
    if isinstance(e, llm.MissingKey):
        return "Kein API-Schlüssel gesetzt: die Analyse kann nicht starten."
    if isinstance(e, llm.SessionBudgetExceeded):
        return "Kostenlimit erreicht: keine weiteren Analysen in dieser Sitzung."
    if isinstance(e, anthropic.AuthenticationError):
        return "API-Schlüssel ungültig."
    if isinstance(e, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return "Claude ist nicht erreichbar. Bitte Internetverbindung prüfen."
    if isinstance(e, anthropic.RateLimitError):
        return "Zu viele Anfragen an Claude. Bitte kurz warten und erneut versuchen."
    if isinstance(e, anthropic.APIStatusError):
        return "Claude hat die Anfrage abgelehnt."
    if isinstance(e, (FileNotFoundError, ValueError)):
        return "Foto oder Bilddatei nicht gefunden."
    return "Die Analyse ist fehlgeschlagen."


def _run_real(job: Job, image_path: str | None) -> None:
    try:
        upload = image_path is not None and job.photo_id.startswith("upload:")
        result = loop.analyze(None if upload else job.photo_id, image_path if upload else None,
                              model=job.model, on_event=job.push)
        result["photo_id"] = job.photo_id
        results.save(result)
        job.finish(result)
    except Exception as e:  # noqa: BLE001
        job.fail(_german_error(e), f"{type(e).__name__}: {e}")
