"""HTTP API for the frontend (CONTRACTS section 5).

    uvicorn agent.server.app:app --port 8000
    AGENT_FAKE=1 DATA_PIPELINE_STUB=1 uvicorn agent.server.app:app --port 8000   # no data, no key

Env: AGENT_OFFLINE=1 makes /health point the frontend at /tiles and stops the tile proxy.
"""

import asyncio
import json
import os
import re
import time

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .. import config, results
from . import catalogue, export, jobs

WMTS = "https://wmts.geo.admin.ch/1.0.0"
TILE_EXT = {"ch.swisstopo.zeitreihen": "png", "ch.swisstopo.swissimage": "jpeg"}
SAFE = re.compile(r"^[\w.\-]+$")

app = FastAPI(title="Zentral Hack Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


def _offline() -> bool:
    return os.environ.get("AGENT_OFFLINE") == "1"


def _not_found(what: str = "Foto") -> HTTPException:
    return HTTPException(404, f"{what} nicht gefunden")


@app.get("/health")
def health():
    offline = _offline()
    return {"ok": True, "model": config.MODEL, "offline": offline,
            "tiles_url": "/tiles" if offline else WMTS, "fake": config.FAKE}


# ---------- photos and images ----------

@app.get("/photos")
def photos(split: str | None = None, municipality: str | None = None, q: str | None = None,
           limit: int = Query(50, ge=1, le=1000), offset: int = Query(0, ge=0)):
    items = catalogue.list_records(split or None, municipality or None, q or None)
    return {"items": items[offset:offset + limit], "total": len(items)}


@app.get("/photos/{photo_id:path}")
def photo(photo_id: str):
    rec = catalogue.get_record(photo_id)
    if rec is None:
        raise _not_found()
    return rec


@app.get("/images/{photo_id:path}")
def image(photo_id: str, w: int | None = Query(None, ge=16, le=4096)):
    p = catalogue.image_path(photo_id)
    if p is None:
        raise _not_found("Bild")
    return Response(catalogue.image_bytes(p, w), media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


# ---------- analysis ----------

# The body is parsed by hand (JSON or multipart), so describe it for the /docs page explicitly.
_ANALYZE_BODY = {"requestBody": {"required": True, "content": {
    "application/json": {
        "schema": {"type": "object", "required": ["photo_id"], "properties": {"photo_id": {"type": "string"}}},
        "example": {"photo_id": "epics:PK_020566"}},
    "multipart/form-data": {
        "schema": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}},
}}}


@app.post("/analyze", openapi_extra=_ANALYZE_BODY)
async def analyze(request: Request, fresh: bool = False):
    ctype = request.headers.get("content-type", "")
    image_path = None
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        f = form.get("file")
        if f is not None and hasattr(f, "read"):
            try:
                photo_id = catalogue.save_upload(await f.read(), getattr(f, "filename", None))
            except Exception:  # noqa: BLE001 (PIL raises several types for bad files)
                raise HTTPException(400, "Datei ist kein lesbares Bild")
            image_path = str(catalogue.image_path(photo_id))
        else:
            photo_id = form.get("photo_id")
    else:
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "JSON {photo_id} oder Datei erwartet")
        photo_id = body.get("photo_id") if isinstance(body, dict) else None
    if not photo_id or not isinstance(photo_id, str):
        raise HTTPException(400, "photo_id oder Datei fehlt")
    # fake mode needs no data: any id replays the fixture
    if not config.FAKE and image_path is None and catalogue.image_path(photo_id) is None:
        raise _not_found()
    job = jobs.submit(photo_id, image_path=image_path, fresh=fresh)
    return {"job_id": job.id, "photo_id": photo_id}


def _job(job_id: str) -> jobs.Job:
    job = jobs.get(job_id)
    if job is None:
        raise _not_found("Auftrag")
    return job


@app.get("/analyze/{job_id}")
def analyze_status(job_id: str):
    return _job(job_id).snapshot()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/analyze/{job_id}/events")
async def analyze_events(job_id: str, request: Request):
    job = _job(job_id)

    async def stream():
        i, last = 0, time.monotonic()
        while True:
            items, result = job.since(i)
            for item in items:
                yield _sse("trace", item)
            i += len(items)
            if result is not None:
                yield _sse("result", result)
                return
            if await request.is_disconnected():
                return
            if time.monotonic() - last > 15:
                last = time.monotonic()
                yield ": ping\n\n"
            await asyncio.sleep(0.05)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/results/{photo_id:path}")
def result(photo_id: str):
    r = results.load(photo_id) or jobs.latest_result(photo_id)
    if r is None:
        raise HTTPException(404, "Kein Ergebnis vorhanden")
    return r


# ---------- export ----------

def _export_rows(ids: str | None) -> list[dict]:
    if ids:
        wanted = [i.strip() for i in ids.split(",") if i.strip()]
        found = [results.load(i) or jobs.latest_result(i) for i in wanted]
        rs = [r for r in found if r]
    else:
        rs = results.all_results()
        have = {r["photo_id"] for r in rs}
        rs += [r for r in jobs.memory_results() if r["photo_id"] not in have]
    return [export.row(r, catalogue.get_record(r["photo_id"])) for r in rs]


@app.get("/export.csv")
def export_csv(ids: str | None = None):
    return Response(export.to_csv(_export_rows(ids)), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="export.csv"'})


@app.get("/export.json")
def export_json(ids: str | None = None):
    return _export_rows(ids)


# ---------- timeline, eval, demo, tiles ----------

@app.get("/timeline")
def timeline(lat: float, lon: float, radius_m: int = Query(1000, ge=1, le=50000)):
    return {"photos": catalogue.timeline(lat, lon, radius_m), "map_years": catalogue.map_years()}


@app.get("/eval/summary")
def eval_summary():
    p = config.RESULTS_DIR / "eval_summary.json"
    if not p.exists():
        p = config.FIXTURES / "eval_summary.json"
    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


@app.get("/demo")
def demo():
    return catalogue.demo()


@app.get("/tiles/{layer}/{tile_time}/{z}/{x}/{y}")
async def tile(layer: str, tile_time: str, z: int, x: int, y: str):
    y_num, _, ext = y.partition(".")
    if not (SAFE.match(layer) and SAFE.match(tile_time) and y_num.isdigit()):
        raise HTTPException(400, "Ungültige Kachel")
    manifest_ext = (catalogue.tile_manifest().get(layer) or {}).get("ext")
    ext = ext or manifest_ext or TILE_EXT.get(layer, "png")
    media = "image/png" if ext == "png" else "image/jpeg"
    rel = f"{layer}/{tile_time}/{z}/{x}/{y_num}.{ext}"
    for base in (catalogue.tiles_dir(), config.CACHE_DIR / "tiles"):
        p = base / rel
        if p.exists():
            return Response(p.read_bytes(), media_type=media, headers={"Cache-Control": "public, max-age=604800"})
    if _offline():
        raise _not_found("Kachel")
    url = f"{WMTS}/{layer}/default/{tile_time}/3857/{z}/{x}/{y_num}.{ext}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
    except httpx.HTTPError:
        raise HTTPException(502, "Kachelserver nicht erreichbar")
    if r.status_code != 200:
        raise _not_found("Kachel")
    out = config.CACHE_DIR / "tiles" / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    return Response(r.content, media_type=r.headers.get("content-type", media),
                    headers={"Cache-Control": "public, max-age=604800"})
