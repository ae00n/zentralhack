"""swisstopo_search: swissNAMES / address lookup via the geo.admin.ch SearchServer (free, no key).

Every response is cached on disk under config.CACHE_DIR/swisstopo/, keyed by URL, and live calls are
rate limited to 30 per minute (the service allows 40).
"""

import hashlib
import json
import re
import threading
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .. import config
from .base import ToolContext, ToolOutput

SEARCH_URL = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
RATE_PER_MIN = 30
LIMIT = 8
# Hits further than this from the town of Schwyz are fuzzy matches elsewhere in Switzerland (e.g.
# "Urirotstock" finds L'Aurore VD; swisstopo spells it "Uri Rotstock"). 60 km covers the Zentralschweiz.
SCHWYZ_LV95 = (2691000, 1208000)
REGION_KM = 60

DEFINITION = {
    "name": "swisstopo_search",
    "description": (
        "Look up a Swiss place, peak, pass, lake, field name (Flurname) or address in swisstopo's "
        "gazetteer. Returns the matches with type, canton, municipality and WGS84 coordinates. Use it to "
        "place a printed or recognised name on the map, or to check that a name exists in Kanton Schwyz."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "the name to search, e.g. 'Gitschen'"}},
        "required": ["text"],
        "additionalProperties": False,
    },
    "strict": True,
}

_calls: deque[float] = deque()
_rate_lock = threading.Lock()


def _cache_dir() -> Path:
    return Path(config.CACHE_DIR) / "swisstopo"


def _wait_for_slot() -> None:
    with _rate_lock:
        now = time.monotonic()
        while _calls and now - _calls[0] > 60:
            _calls.popleft()
        if len(_calls) >= RATE_PER_MIN:
            time.sleep(60 - (now - _calls[0]) + 0.05)
            _calls.popleft()
        _calls.append(time.monotonic())


def cached_get(url: str, timeout: float = 15.0) -> dict:
    """GET JSON with the disk cache. Only successful responses are cached."""
    path = _cache_dir() / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["body"]
    _wait_for_slot()
    r = httpx.get(url, timeout=timeout, headers={"User-Agent": "zentralhack-agent/1.0"})
    r.raise_for_status()
    body = r.json()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"url": url, "body": body}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return body


def search_url(text: str) -> str:
    return SEARCH_URL + "?" + urlencode({"searchText": text, "type": "locations", "sr": 2056, "limit": LIMIT})


def _clean(label: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", label or "")).strip()


def run(ctx: ToolContext, text: str) -> ToolOutput:
    text = (text or "").strip()
    if not text:
        return ToolOutput({"error": "empty search text"}, "Leere Suche", is_error=True)
    url = search_url(text)
    try:
        body = cached_get(url)
    except (httpx.HTTPError, ValueError) as e:
        return ToolOutput({"error": f"swisstopo not reachable: {type(e).__name__}"},
                          f"swisstopo nicht erreichbar ({text})", is_error=True)
    out = []
    for res in (body.get("results") or [])[:LIMIT]:
        a = res.get("attrs") or {}
        canton = re.search(r"\(([A-Z]{2})\)", a.get("label") or "")
        out.append({k: v for k, v in {
            "name": _clean(a.get("label")),
            "type": a.get("objectclass") or a.get("origin"),
            "canton": canton.group(1) if canton else None,
            "lat": round(a["lat"], 5) if a.get("lat") is not None else None,
            "lon": round(a["lon"], 5) if a.get("lon") is not None else None,
            # with sr=2056 SearchServer puts LV95 northing in x and easting in y
            "E_LV95": round(a["y"]) if a.get("y") is not None else None,
            "N_LV95": round(a["x"]) if a.get("x") is not None else None,
        }.items() if v is not None})
    for r in out:
        if "E_LV95" in r and "N_LV95" in r:
            r["km_from_schwyz"] = round(((r["E_LV95"] - SCHWYZ_LV95[0]) ** 2
                                         + (r["N_LV95"] - SCHWYZ_LV95[1]) ** 2) ** 0.5 / 1000, 1)
    near = [r for r in out if r.get("km_from_schwyz", 0) <= REGION_KM]
    data = {"query": text, "results": near, "url": url}
    if out and not near:
        data["far_results_dropped"] = len(out)
        data["hint"] = ("No match within 60 km of Schwyz, only fuzzy matches elsewhere in Switzerland. "
                        "Try another spelling: swisstopo often writes compound names apart "
                        "(e.g. 'Uri Rotstock', not 'Urirotstock') or without a prefix.")
    return ToolOutput(data, _summary(text, near, len(out) - len(near)))


def _summary(text: str, results: list[dict], dropped: int = 0) -> str:
    if not results:
        if dropped:
            return f"swisstopo: nichts in der Zentralschweiz für «{text}», andere Schreibweise nötig"
        return f"swisstopo: nichts gefunden für «{text}»"
    first = results[0]
    sz = sum(1 for r in results if r.get("canton") == "SZ")
    tail = f", {sz} davon im Kanton SZ" if sz else ""
    return f"swisstopo: {len(results)} Treffer für «{text}», erster: {first['name']}{tail}"
