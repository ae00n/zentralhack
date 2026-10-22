"""Polite HTTP client: one request at a time, a minimum gap between requests,
retries with backoff, and an on-disk cache so a re-run never re-fetches."""

import hashlib
import time
from pathlib import Path

import httpx

USER_AGENT = "ZentralHack2026-team (HSLU hackathon research; contact via github.com/ae00n)"


class PoliteClient:
    def __init__(self, min_interval: float = 2.0, cache_dir: Path | None = None, headers: dict | None = None):
        self.min_interval = min_interval
        self.cache_dir = cache_dir
        self._last = 0.0
        self.requests = 0
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, **(headers or {})},
            timeout=60,
            follow_redirects=True,
        )

    def _wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.monotonic()

    def _cache_path(self, key: str, suffix: str) -> Path | None:
        if not self.cache_dir:
            return None
        h = hashlib.sha1(key.encode()).hexdigest()
        return self.cache_dir / h[:2] / f"{h}{suffix}"

    def request(self, method: str, url: str, *, cache: bool = True, suffix: str = ".bin", **kw) -> bytes:
        key = method + " " + url + " " + repr(kw.get("json") or kw.get("params") or "")
        path = self._cache_path(key, suffix) if cache else None
        if path and path.exists():
            return path.read_bytes()
        for attempt in range(5):
            self._wait()
            self.requests += 1
            try:
                r = self.client.request(method, url, **kw)
            except httpx.HTTPError as e:
                err = str(e)
            else:
                if r.status_code == 200:
                    if path:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(r.content)
                    return r.content
                if r.status_code in (404, 410):
                    raise FileNotFoundError(f"{r.status_code} {url}")
                err = f"HTTP {r.status_code}"
            backoff = 10 * 2**attempt
            print(f"  retry {attempt + 1}/5 in {backoff}s ({err}) {url}", flush=True)
            time.sleep(backoff)
        raise RuntimeError(f"giving up on {url}")

    def get(self, url: str, **kw) -> bytes:
        return self.request("GET", url, **kw)

    def text(self, url: str, **kw) -> str:
        return self.get(url, suffix=".html", **kw).decode("utf-8", errors="replace")
