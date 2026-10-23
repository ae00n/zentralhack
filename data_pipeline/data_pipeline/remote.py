"""Remote mode: the section 4 interface backed by a data server (data_pipeline.serve) instead of data/.

Active when env DATA_PIPELINE_URL is set (see data_pipeline/__init__.py), with DATA_PIPELINE_TOKEN.
ZH_DATA_DIR (default <repo>/data) becomes a local mirror:

- On import, the small files (records, splits, gazetteer, best.json, tile manifest, about 60 MB the
  first time) are synced, so get_record, archive_lookup, timeline, gazetteer, eval_ids, metrics and
  everything else that reads them run locally on identical files.
- image_file() fetches an image the first time it is asked for, into the same relative path.
- similar_images, date_hints and split_composite run on the server (indexes, models, raw data).

Same code, same files, so every call answers the same as on the server. Not mirrored: the indexes,
the model weights, the map tiles (fetch one with fetch_file("tiles/...") if needed).
"""

import base64
import os
from pathlib import Path
from urllib.parse import quote

import httpx

from .paths import DATA_DIR

URL = os.environ.get("DATA_PIPELINE_URL", "").rstrip("/")
TOKEN = os.environ.get("DATA_PIPELINE_TOKEN", "")
STATE = DATA_DIR / ".remote_sync.json"


class RemoteError(RuntimeError):
    pass


_client: httpx.Client | None = None


def _http() -> httpx.Client:
    global _client
    if _client is None:
        if not TOKEN:
            raise RemoteError("DATA_PIPELINE_URL is set but DATA_PIPELINE_TOKEN is not")
        _client = httpx.Client(base_url=URL, headers={"Authorization": f"Bearer {TOKEN}"},
                               timeout=httpx.Timeout(300, connect=10), follow_redirects=False)
    return _client


def _get(path: str) -> httpx.Response:
    r = _http().get(path)
    if r.status_code == 401:
        raise RemoteError("data server: wrong DATA_PIPELINE_TOKEN")
    return r


def fetch_file(rel: str) -> Path | None:
    """Download data/<rel> into the mirror (atomic); None if the server has no such file."""
    r = _get("/file/" + quote(rel))  # crop names contain "#"
    if r.status_code == 404:
        return None
    r.raise_for_status()
    p = DATA_DIR / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    tmp.write_bytes(r.content)
    tmp.replace(p)
    return p


def sync() -> int:
    """Bring the mirrored small files up to date. Returns how many were downloaded."""
    import json
    r = _get("/manifest")
    r.raise_for_status()
    want = r.json()
    have = json.loads(STATE.read_text()) if STATE.exists() else {}
    n = 0
    for rel, meta in want.items():
        if have.get(rel) != meta or not (DATA_DIR / rel).exists():
            if fetch_file(rel):
                have[rel] = meta
                n += 1
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(have))
    return n


def _rpc(name: str, kwargs: dict, image_path: str | None = None):
    body: dict = {"kwargs": kwargs}
    if image_path is not None:
        p = Path(image_path)
        rel = None
        try:
            rel = p.resolve().relative_to(DATA_DIR.resolve()).as_posix()
        except ValueError:
            pass
        if rel and rel.startswith("images/"):  # an archive image or crop: the server has it
            body["image"] = {"rel": rel}
        else:  # an upload: send the bytes
            body["image"] = {"name": p.name, "b64": base64.b64encode(p.read_bytes()).decode()}
    r = _http().post(f"/rpc/{name}", json=body)
    if r.status_code == 401:
        raise RemoteError("data server: wrong DATA_PIPELINE_TOKEN")
    data = r.json()
    if r.status_code == 404 and image_path is not None:
        raise FileNotFoundError(data.get("error"))
    if r.status_code != 200:
        raise RemoteError(f"data server {name}: {data.get('error')}")
    return data["result"]


# ---------- the remote versions (same signatures as api.py / dating.py) ----------

def image_file(record: dict) -> Path | None:
    p = (record.get("image") or {}).get("path")
    if not p:
        return None
    path = DATA_DIR / p
    if not path.exists():
        fetch_file(p)
    return path


def similar_images(image_path: str, k: int = 8, model: str = "best",
                   exclude_ids: list[str] = (), sources: list[str] | None = None,
                   verify: bool = False) -> list[dict]:
    return _rpc("similar_images", {"k": k, "model": model, "exclude_ids": list(exclude_ids),
                                   "sources": sources, "verify": verify}, image_path)


def date_hints(photo_id: str | None = None, image_path: str | None = None, exclude_ids=()) -> list[dict]:
    return _rpc("date_hints", {"photo_id": photo_id, "exclude_ids": list(exclude_ids)}, image_path)


def split_composite(image_path: str) -> list[dict]:
    out = []
    for it in _rpc("split_composite", {}, image_path):
        if it["rel"] is None or not it["rel"].startswith("images/crops/"):
            path = Path(image_path)  # not composite: the full image, as the caller passed it
        else:
            path = DATA_DIR / it["rel"]
            if not path.exists():
                fetch_file(it["rel"])
        out.append({"bbox": it["bbox"], "path": str(path)})
    return out


def install() -> None:
    """Sync the mirror and swap the heavy functions in api and dating for the remote ones."""
    from . import api, dating
    sync()
    api.image_file = image_file
    api.similar_images = similar_images
    api.split_composite = split_composite
    dating.image_file = image_file
    dating.date_hints = date_hints
