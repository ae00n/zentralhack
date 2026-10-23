"""Data server: the section 4 interface over HTTP, for teammates without a local data/ folder.

    DATA_PIPELINE_TOKEN=... python -m data_pipeline.serve [--host 127.0.0.1] [--port 8790]

The client side is data_pipeline.remote (env DATA_PIPELINE_URL + DATA_PIPELINE_TOKEN). It mirrors the
small files (records, splits, gazetteer, best.json, tile manifest) and runs the record functions
locally on them, so only the heavy calls come here:

    GET  /manifest            {relpath: [size, mtime_ns]} of the mirrored files
    GET  /file/<relpath>      one file under data/ (images, crops, mirrored files, tiles)
    POST /rpc/<name>          {"kwargs": {...}, "image": {"rel": ...} | {"name": ..., "b64": ...}}
                              name: similar_images | date_hints | split_composite

Both sides run the same functions on the same data, so a call answers the same either way.
Every request needs `Authorization: Bearer <DATA_PIPELINE_TOKEN>`. The Staatsarchiv images are not
openly licensed: run this only behind the token, never as a public file server.
"""

import argparse
import base64
import hmac
import json
import os
import re
import shutil
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .paths import DATA_DIR

MIRROR = ["records/all.jsonl", "records/crops.jsonl", "records/challenge.jsonl", "splits", "gazetteer", "index/best.json",
          "tiles/manifest.json"]
SERVED = ("records/", "splits/", "gazetteer/", "images/", "tiles/", "index/best.json")
RPC = ("similar_images", "date_hints", "split_composite")
_lock = threading.Lock()  # one heavy call at a time (models are not thread safe, RAM is shared)


def manifest() -> dict[str, list[int]]:
    out = {}
    for m in MIRROR:
        p = DATA_DIR / m
        for f in ([p] if p.is_file() else sorted(p.rglob("*")) if p.is_dir() else []):
            if f.is_file() and not f.name.endswith(".tmp"):
                st = f.stat()
                out[f.relative_to(DATA_DIR).as_posix()] = [st.st_size, st.st_mtime_ns]
    return out


def _safe(rel: str) -> Path | None:
    if not rel.startswith(SERVED) or ".." in Path(rel).parts:
        return None
    p = (DATA_DIR / rel).resolve()
    return p if p.is_file() and p.is_relative_to(DATA_DIR.resolve()) else None


def _rel(path: str) -> str | None:
    try:
        return Path(path).resolve().relative_to(DATA_DIR.resolve()).as_posix()
    except ValueError:
        return None


def rpc(name: str, body: dict) -> object:
    from . import api, dating
    kw = dict(body.get("kwargs") or {})
    img, tmp = body.get("image"), None
    try:
        if img and img.get("rel"):
            p = _safe(img["rel"])
            if p is None:
                raise FileNotFoundError(img["rel"])
            kw["image_path"] = str(p)
        elif img:
            tmp = Path(tempfile.mkdtemp(prefix="zh-upload-"))
            stem = re.sub(r"[^\w.-]+", "_", Path(img.get("name") or "upload.jpg").name) or "upload.jpg"
            p = tmp / stem
            p.write_bytes(base64.b64decode(img["b64"]))
            kw["image_path"] = str(p)
        with _lock:
            if name == "similar_images":
                return api.similar_images(**kw)
            if name == "date_hints":
                return dating.date_hints(**kw)
            if name == "split_composite":
                out = api.split_composite(**kw)
                # paths relative to data/; the upload itself comes back as null (the client keeps its own copy)
                return [{"bbox": it["bbox"], "rel": _rel(it["path"])} for it in out]
        raise KeyError(name)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    token = ""

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode())

    def _authed(self) -> bool:
        got = self.headers.get("Authorization", "")
        if self.token and hmac.compare_digest(got, f"Bearer {self.token}"):
            return True
        self._json(401, {"error": "unauthorized"})
        return False

    def do_GET(self):
        if not self._authed():
            return
        if self.path == "/health":
            return self._json(200, {"ok": True})
        if self.path == "/manifest":
            return self._json(200, manifest())
        if self.path.startswith("/file/"):
            from urllib.parse import unquote
            p = _safe(unquote(self.path[len("/file/"):]))
            if p is None:
                return self._json(404, {"error": "not found"})
            ctype = "image/jpeg" if p.suffix in (".jpg", ".jpeg") else "application/octet-stream"
            return self._send(200, p.read_bytes(), ctype)
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._authed():
            return
        name = self.path.removeprefix("/rpc/")
        if not self.path.startswith("/rpc/") or name not in RPC:
            return self._json(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            self._json(200, {"result": rpc(name, body)})
        except FileNotFoundError as e:
            self._json(404, {"error": f"not found: {e}"})
        except Exception as e:  # the client re-raises it with the same type name
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}", flush=True)


def warm() -> None:
    """Load the best index and encoder once so the first real call is not slow."""
    from . import api
    q = next(iter(sorted((DATA_DIR / "images" / "staatsarchiv").glob("*.jpg"))), None)
    if q:
        api.similar_images(str(q), k=1)
    print("warm", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--no-warm", action="store_true")
    a = ap.parse_args()
    Handler.token = os.environ.get("DATA_PIPELINE_TOKEN", "")
    if not Handler.token:
        raise SystemExit("set DATA_PIPELINE_TOKEN")
    if not a.no_warm:
        threading.Thread(target=lambda: _locked(warm), daemon=True).start()
    print(f"serving {DATA_DIR} on {a.host}:{a.port}", flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


def _locked(fn) -> None:
    with _lock:
        fn()


if __name__ == "__main__":
    main()
