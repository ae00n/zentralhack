"""The Python interface Agent calls (docs/CONTRACTS.md section 4).

Everything loads lazily from data/ on first use. Image paths in records are relative to
DATA_DIR (env ZH_DATA_DIR, default <repo>/data); `image_file(record)` resolves them.

Eval leakage rule: `similar_images` never returns an id in `exclude_ids`, nor a crop (`id#n`)
or parent of one; `archive_lookup` never returns an eval card.
"""

import json
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from .jsonl import read_jsonl
from .paths import DATA_DIR, GAZETTEER, RECORDS, SPLITS


def _base(photo_id: str) -> str:
    return photo_id.split("#", 1)[0]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").casefold()
    return re.sub(r"[^\w]+", " ", s).strip()


@lru_cache(maxsize=1)
def _records() -> dict[str, dict]:
    recs = {r["id"]: r for r in read_jsonl(RECORDS / "all.jsonl")}
    for r in read_jsonl(RECORDS / "crops.jsonl"):  # written by the composite splitter, if present
        recs[r["id"]] = r
    for r in read_jsonl(RECORDS / "challenge.jsonl"):  # the event photos (scrapers/challenge.py), not indexed
        recs[r["id"]] = r
    # Smapshot ids that were merged into an E-Pics record still resolve
    for r in list(recs.values()):
        for alias in (r.get("raw") or {}).get("merged_from", []):
            recs.setdefault(alias, r)
    return recs


def reload() -> None:
    """Drop caches (call after merge/splits ran while the process was alive)."""
    _records.cache_clear()
    eval_ids.cache_clear()
    gazetteer.cache_clear()


def image_file(record: dict) -> Path | None:
    p = (record.get("image") or {}).get("path")
    return DATA_DIR / p if p else None


def get_record(photo_id: str) -> dict | None:
    """PhotoRecord by id (also crop ids `stasz:1#2` and merged Smapshot ids), else None."""
    return _records().get(photo_id)


@lru_cache(maxsize=1)
def eval_ids() -> frozenset[str]:
    """Ids in data/splits/eval.jsonl. The eval runner and the leakage tests share this."""
    return frozenset(r["id"] for r in read_jsonl(SPLITS / "eval.jsonl"))


@lru_cache(maxsize=1)
def gazetteer() -> list[dict]:
    """Kanton Schwyz municipalities: [{name, bfs_nr, lat, lon, aliases}]."""
    p = GAZETTEER / "gemeinden.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


VERIFY_TOP = 10  # with verify=True, this many candidates (or k, if larger) get matched


def similar_images(image_path: str, k: int = 8, model: str = "best",
                   exclude_ids: list[str] = (), sources: list[str] | None = None,
                   verify: bool = False) -> list[dict]:
    """[{id, score, record}] sorted by score desc.

    model: "best" (best.json), "clip", "dinov2", "megaloc" or "fused" (rank fusion of all three;
    score is then an RRF score, not a cosine).
    verify=True: geometric check (data_pipeline.verify, ~1 to 2 s per candidate on CPU) of the top
    max(k, VERIFY_TOP) hits. Each item gains "inliers" and "verified"; verified hits come first
    (most inliers first), the rest keep score order. A verified hit shows the same place.

    Always pass the query card's own id in exclude_ids when analysing an archive card.
    Needs data_pipeline.embed with `search(image_path, k, model) -> [(id, score)]`.
    """
    try:
        from . import embed
    except ImportError as e:
        raise NotImplementedError("similar_images needs data_pipeline.embed (index not built yet)") from e
    excluded = {_base(i) for i in exclude_ids}
    want = k * 3 + len(excluded) + 10
    out, seen = [], set()
    # sources go into the index search, so a filter like ["commons"] pages past the older photos ranked above them
    for pid, score in embed.search(image_path, want, model, sources=sources):
        if _base(pid) in excluded or _base(pid) in seen:  # a card and its crops count once (best one wins)
            continue
        rec = get_record(pid)
        if rec is None or (sources and rec["source"] not in sources):
            continue
        seen.add(_base(pid))
        out.append({"id": rec["id"], "score": float(score), "record": rec})
        if len(out) >= (max(k, VERIFY_TOP) if verify else k):
            break
    if verify:
        out = _verify_rerank(image_path, out)[:k]
    return out


def _verify_rerank(image_path: str, items: list[dict]) -> list[dict]:
    from . import verify as geo

    paths = [image_file(it["record"]) for it in items]
    checked = iter(geo.verify(image_path, [p for p in paths if p is not None]))
    for it, p in zip(items, paths):
        r = next(checked) if p is not None else {"inliers": 0, "verified": False}
        it["inliers"], it["verified"] = r["inliers"], r["verified"]
    # sorted() is stable: unverified hits keep their score order
    return sorted(items, key=lambda it: (not it["verified"], -it["inliers"] if it["verified"] else 0))


def archive_lookup(place: str | None = None, municipality: str | None = None,
                   year_from: int | None = None, year_to: int | None = None, limit: int = 20) -> list[dict]:
    """Dated, labelled Staatsarchiv records matching the filter. Never returns eval cards.

    place: matches Thema tags and title when every word of it occurs there, in any order ("Kirche
    Lachen" finds "Lachen, Pfarrkirche"). With no hit at all, spelling variants count too
    ("Muotathal" finds "Muotatal"). municipality: exact Gemeinde name (with or without "(SZ)").
    Years: overlap with the card's year range.
    """
    ev = eval_ids()
    p = _norm(place) if place else None
    m = _norm(re.sub(r"\s*\(SZ\)\s*$", "", municipality)) if municipality else None
    words = [w for w in (p or "").split() if len(w) >= 3] or ([p] if p else [])
    out, fuzzy = [], []
    for r in _records().values():
        if r["source"] != "staatsarchiv" or "#" in r["id"] or r["id"] in ev:
            continue
        d = r.get("date") or {}
        if d.get("year_from") is None:
            continue
        if m and _norm(re.sub(r"\s*\(SZ\)\s*$", "", r.get("municipality") or "")) != m:
            continue
        if year_from is not None and d.get("year_to") is not None and d["year_to"] < year_from:  # "nach 1910": open end
            continue
        if year_to is not None and d["year_from"] > year_to:
            continue
        if p:
            text = _norm(" ".join(r.get("places") or []) + " " + (r.get("title") or ""))
            if not all(w in text for w in words):
                if not out:
                    fuzzy.append((r, text))
                continue
        out.append(r)
    if p and not out:  # spelling variants: every query word close to some word of the card
        import difflib
        for r, text in fuzzy:
            tw = text.split()
            if all(difflib.get_close_matches(w, tw, n=1, cutoff=0.8) for w in words):
                out.append(r)
    out.sort(key=lambda r: (r["date"]["year_from"], r["id"]))
    return out[:limit]


def split_composite(image_path: str) -> list[dict]:
    """[{bbox: [x, y, w, h], path}]; one item (the full image) when not composite.

    Needs data_pipeline.split with `split_composite(image_path)`.
    """
    try:
        from . import split
    except ImportError as e:
        raise NotImplementedError("split_composite needs data_pipeline.split (not built yet)") from e
    return split.split_composite(image_path)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def timeline(lat: float, lon: float, radius_m: int = 1000) -> list[dict]:
    """Dated Staatsarchiv cards near a point: [{id, year_from, year_to, distance_m, image_path}] by year.

    Eval cards are left out so the time slider never reveals an eval answer.
    image_path is relative to DATA_DIR, like PhotoRecord.image.path.
    """
    ev = eval_ids()
    out = []
    for r in _records().values():
        if r["source"] != "staatsarchiv" or "#" in r["id"] or r["id"] in ev:
            continue
        d, loc = r.get("date") or {}, r.get("location")
        if d.get("year_from") is None or not loc or not (r.get("image") or {}).get("path"):
            continue
        dist = _haversine_m(lat, lon, loc["lat"], loc["lon"])
        if dist <= radius_m:
            out.append({"id": r["id"], "year_from": d["year_from"], "year_to": d["year_to"],
                        "distance_m": round(dist), "image_path": r["image"]["path"]})
    out.sort(key=lambda x: (x["year_from"], x["distance_m"], x["id"]))
    return out


def photos_near(lat: float, lon: float, radius_m: int = 500, max_precision_m: int = 500,
                sources: list[str] | None = None, exclude_ids: list[str] = (), limit: int = 12) -> list[dict]:
    """Reference photos taken near a point, nearest first ("walk around" a candidate spot).

    [{id, source, title, year, distance_m, precision_m, heading_deg, image_path}]
    Every source with a position counts (Commons, E-Pics/Smapshot, LUBIS, Staatsarchiv, NB). Only
    positions at least as precise as max_precision_m: Staatsarchiv cards placed at their municipality
    (1 to 3 km) are left out by default. heading_deg is the camera's viewing direction (0 = north,
    90 = east) where a pose is known (Smapshot, E-Pics, LUBIS), else null. Never returns eval cards,
    challenge photos, crops, or anything in exclude_ids.
    """
    ev = eval_ids()
    excluded = {_base(i) for i in exclude_ids}
    out = []
    for r in _records().values():
        if r["source"] == "challenge" or "#" in r["id"] or r["id"] in ev or r["id"] in excluded:
            continue
        loc = r.get("location")
        if not loc or (loc.get("precision_m") or 10**6) > max_precision_m or not (r.get("image") or {}).get("path"):
            continue
        if sources and r["source"] not in sources:
            continue
        dist = _haversine_m(lat, lon, loc["lat"], loc["lon"])
        if dist > radius_m:
            continue
        az = (r.get("camera") or {}).get("azimuth")
        out.append({"id": r["id"], "source": r["source"], "title": r.get("title"),
                    "year": (r.get("date") or {}).get("year_from"), "distance_m": round(dist),
                    "precision_m": loc.get("precision_m"), "heading_deg": round(az % 360) if az is not None else None,
                    "image_path": r["image"]["path"]})
    out.sort(key=lambda x: (x["distance_m"], x["id"]))
    return out[:limit]
