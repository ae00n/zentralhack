"""Claude client, token usage to USD, and the global cost ledger with the session hard stop.

Ledger: one JSON line per API call in RESULTS_DIR/costs.jsonl. Every call checks the ledger total
first and refuses to run once it passes config.SESSION_BUDGET_USD (the credit is $100).
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

# Server-side refusal fallback (beta). Only the Opus/Sonnet 5.5 line has it; Haiku 5.5 has no fallback.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-opus-5-5"}
# thinking display "updates" (beta): short progress notes between tool calls, reasoning stays hidden
UPDATES_BETA = "thinking-display-updates-2026-08-18"
UPDATES_MODELS = {"claude-opus-5-5"}

# A fallback can answer on another model; price it at that model's list price.
EXTRA_PRICES = {"claude-opus-5": (5.0, 25.0), "claude-opus-4-8": (5.0, 25.0)}
# Cache write = 1.25x input, cache read = 0.1x input. Opus 5.5 reads are actually cheaper (0.05x);
# 0.1x keeps the estimate on the safe side for the budget guards.
CACHE_WRITE_FACTOR = 1.25
CACHE_READ_FACTOR = 0.1

_lock = threading.Lock()


class MissingKey(RuntimeError):
    pass


class SessionBudgetExceeded(RuntimeError):
    pass


def has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def make_client():
    """anthropic.Anthropic from env. Raises MissingKey (before any network call) when no key is set."""
    if not has_credentials():
        raise MissingKey("ANTHROPIC_API_KEY is not set. Put it in the environment or in <repo>/.env "
                         "(gitignored). No Claude call was made.")
    import anthropic

    return anthropic.Anthropic(max_retries=4, timeout=300.0)


# ---------- cost ----------

def price(model: str) -> tuple[float, float]:
    """USD per million tokens (input, output). Unknown models get the most expensive known price."""
    table = {**EXTRA_PRICES, **config.PRICES}
    if model in table:
        return table[model]
    return max(table.values())


def _get(usage, name: str) -> int:
    v = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
    return int(v or 0)


def usage_tokens(usage) -> dict:
    """SDK Usage (or dict) -> {input, cache_write, cache_read, output}. input excludes cached tokens."""
    return {
        "input": _get(usage, "input_tokens"),
        "cache_write": _get(usage, "cache_creation_input_tokens"),
        "cache_read": _get(usage, "cache_read_input_tokens"),
        "output": _get(usage, "output_tokens"),
    }


def cost_usd(model: str, usage) -> float:
    t = usage_tokens(usage)
    p_in, p_out = price(model)
    usd_in = (t["input"] + CACHE_WRITE_FACTOR * t["cache_write"] + CACHE_READ_FACTOR * t["cache_read"]) * p_in
    return (usd_in + t["output"] * p_out) / 1e6


# ---------- ledger ----------

def ledger_path() -> Path:
    # read at call time so tests (and AGENT_RESULTS_DIR) can redirect it
    return Path(config.RESULTS_DIR) / "costs.jsonl"


def ledger_total() -> float:
    p = ledger_path()
    if not p.exists():
        return 0.0
    total = 0.0
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    total += float(json.loads(line).get("cost_usd", 0.0))
                except ValueError:
                    continue
    return total


def record(entry: dict) -> None:
    p = ledger_path()
    with _lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def check_session_budget() -> float:
    total = ledger_total()
    if total >= config.SESSION_BUDGET_USD:
        raise SessionBudgetExceeded(
            f"cost ledger total ${total:.2f} has reached SESSION_BUDGET_USD ${config.SESSION_BUDGET_USD:.2f} "
            f"({ledger_path()}); no further Claude calls")
    return total


# ---------- the call ----------

_degraded = False  # set once the API rejected a beta feature; later calls go out plain


def thinking_param(model: str, plain: bool = False) -> dict:
    """Thinking is always on for the 5.5 models; effort controls depth. "updates" returns the model's
    short between-tool notes (reasoning stays hidden); "summarized" is the GA fallback."""
    if not plain and model in UPDATES_MODELS:
        return {"type": "adaptive", "display": "updates"}
    return {"type": "adaptive", "display": "summarized"}


def create(client, *, model: str, meta: dict | None = None, **params):
    """One Messages API call with the session hard stop and a ledger line. Returns (response, cost_usd).

    Adds the thinking config. For FALLBACK_MODELS the call goes through the beta namespace with
    fallbacks="default" (a classifier refusal is retried server-side on the recommended model) and
    thinking display "updates". If the API rejects one of these features or a strict tool schema
    (HTTP 400), the call is retried once without them, and later calls stay plain.
    """
    global _degraded
    check_session_budget()
    t0 = time.monotonic()
    try:
        resp = _send(client, model, params, plain=_degraded)
    except Exception as e:
        if _degraded or not _is_feature_error(e):
            raise
        log.warning("API rejected a beta feature or strict schema (%s); retrying plain", e)
        _degraded = True
        resp = _send(client, model, params, plain=True)
    served_by = getattr(resp, "model", None) or model
    usd = cost_usd(served_by, resp.usage)
    record({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": served_by,
        **{f"{k}_tokens": v for k, v in usage_tokens(resp.usage).items()},
        "cost_usd": round(usd, 6),
        "ms": round((time.monotonic() - t0) * 1000),
        **(meta or {}),
    })
    return resp, usd


def _send(client, model: str, params: dict, plain: bool):
    params = {**params, "thinking": thinking_param(model, plain)}
    if plain:
        params["tools"] = [{k: v for k, v in t.items() if k != "strict"} for t in params.get("tools", [])]
        return client.messages.create(model=model, **params)
    betas = []
    if model in FALLBACK_MODELS:
        betas.append(FALLBACK_BETA)
        params["fallbacks"] = "default"
    if model in UPDATES_MODELS:
        betas.append(UPDATES_BETA)
    if betas:
        return client.beta.messages.create(model=model, betas=betas, **params)
    return client.messages.create(model=model, **params)


def _is_feature_error(e: Exception) -> bool:
    if getattr(e, "status_code", None) != 400:
        return False
    msg = str(e).lower()
    return any(w in msg for w in ("strict", "schema", "beta", "fallback", "display"))
