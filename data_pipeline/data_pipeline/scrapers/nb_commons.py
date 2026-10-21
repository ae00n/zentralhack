"""Swiss National Library (NB) photos on Wikimedia Commons: public domain, dated.

    python -m data_pipeline.scrapers.nb_commons fetch --limit 20                # test (Schwyz first)
    python -m data_pipeline.scrapers.nb_commons fetch                           # full run
    python -m data_pipeline.scrapers.nb_commons fetch --cantons schwyz,uri

Source: the NB upload to Commons (Photoglob-Wehrli EAD-WEHR, Rudolf Zinggeler EAD-ZING).
- Files are listed from "Category:CH-NB-Photographs of <canton> (canton of Switzerland)".
  These hold only the photos; the wider "CH-NB-<canton> (Kanton)" categories also hold
  prints (GS-GRAF-ANSI) and are not used. One file can sit in several canton categories
  (lake panoramas): it becomes one record, raw.canton_categories lists all of them.
- prop=imageinfo (extmetadata + a thumbnail URL) and wbgetentities on M<pageid>
  (P571 inception with circa / earliest / latest qualifiers), 50 titles per request.
- Commons coordinates are the library in Bern, not the place: ignored.
- Municipality + location only for files in the Schwyz category (gazetteer.resolve on
  place names from the title). Other cantons keep both null.
- Images: the Commons JPEG thumbnail (never the TIFF), downscaled to 1024 px.

Commons wants a User-Agent with a contact URL (the default one gets HTTP 429) and maxlag.
1 request per second, resumable (skips EAD ids already in data/records/nb.jsonl).
"""

import argparse
import hashlib
import html
import io
import json
import re
import time
from datetime import datetime, timezone

from PIL import Image

from .. import gazetteer
from ..http import PoliteClient
from ..paths import IMAGES, RAW, RECORDS, ensure

API = "https://commons.wikimedia.org/w/api.php"
UA = "ZentralHack2026-team/0.1 (https://github.com/ae00n; hackathon research) python-httpx"
MAX_EDGE = 1024
BATCH = 50
CANTONS = {  # CLI name -> Commons category name
    "schwyz": "Schwyz",
    "uri": "Uri",
    "luzern": "Lucerne",
    "zug": "Zug",
    "nidwalden": "Nidwalden",
    "obwalden": "Obwalden",
}
COLLECTIONS = {"WEHR": ("Photoglob-Wehrli", "Photoglob-Wehrli"), "ZING": ("Zinggeler", "Archive Rudolf Zinggeler")}
EAD_RE = re.compile(r"EAD-(WEHR|ZING)-(\d+)([a-z]?)(?:-([A-Z0-9]+))?")  # 1893a-B: part a, suffix B
CIRCA = "Q5727902"
# title segments that describe the view, not the place
VIEW_RE = re.compile(r"ansicht|landschaft|panorama|porträt|person|detail|gruppe|weideland|baustelle", re.I)

RECORDS_FILE = RECORDS / "nb.jsonl"
IMG_DIR = IMAGES / "nb"
API_CACHE = RAW / "nb" / "api"

client = PoliteClient(min_interval=1.0, cache_dir=RAW / "nb" / "http", headers={"User-Agent": UA})


def api(params: dict, cache: bool = True) -> dict:
    """One MediaWiki API call. Only error-free answers are cached (maxlag answers are retried)."""
    params = {**params, "format": "json", "formatversion": 2, "maxlag": 5}
    key = json.dumps(params, sort_keys=True)
    path = API_CACHE / hashlib.sha1(key.encode()).hexdigest()[:2] / (hashlib.sha1(key.encode()).hexdigest() + ".json")
    if cache and path.exists():
        return json.loads(path.read_text())
    for attempt in range(6):
        data = json.loads(client.get(API, params=params, cache=False))
        err = data.get("error")
        if not err:
            if cache:
                ensure(path.parent)
                path.write_text(json.dumps(data, ensure_ascii=False))
            return data
        if err.get("code") != "maxlag":
            raise RuntimeError(f"Commons API error {err}")
        wait = 5 * (attempt + 1)
        print(f"  maxlag ({err.get('info')}), waiting {wait}s", flush=True)
        time.sleep(wait)
    raise RuntimeError("Commons API: maxlag did not clear")


def category_files(category: str) -> list[dict]:
    out, cont = [], {}
    while True:
        d = api({"action": "query", "list": "categorymembers", "cmtitle": f"Category:{category}",
                 "cmtype": "file", "cmlimit": 500, **cont}, cache=False)
        out += d["query"]["categorymembers"]
        if "continue" not in d:
            return out
        cont = d["continue"]


def canton_category(name: str) -> str:
    return f"CH-NB-Photographs of {name} (canton of Switzerland)"


def strip(s: str | None) -> str:
    s = re.sub(r'<div style="display: none;">.*?</div>', "", s or "", flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _year(t: dict | None) -> int | None:
    m = re.match(r"([+-]\d+)-", (t or {}).get("time", ""))
    return int(m.group(1)) if m else None


def _qual_time(stmt: dict, prop: str) -> dict | None:
    for q in stmt.get("qualifiers", {}).get(prop, []):
        if q.get("snaktype") == "value":
            return q["datavalue"]["value"]
    return None


def parse_date(raw_text: str, statements: dict, qs: str | None) -> dict:
    """P571 -> {raw, year_from, year_to, approximate} plus the parsed P571 details for raw."""
    y0 = y1 = None
    approx = False
    info = {}
    stmt = next((s for s in statements.get("P571", []) if s["mainsnak"].get("snaktype") == "value"), None)
    if stmt:
        v = stmt["mainsnak"]["datavalue"]["value"]
        prec = v["precision"]
        y = _year(v)
        circa = any(q.get("datavalue", {}).get("value", {}).get("id") == CIRCA
                    for q in stmt.get("qualifiers", {}).get("P1480", []))
        lo = _year(_qual_time(stmt, "P1319") or _qual_time(stmt, "P580"))
        hi = _year(_qual_time(stmt, "P1326") or _qual_time(stmt, "P582"))
        info = {"p571": v["time"], "precision": prec, "circa": circa, "earliest": lo, "latest": hi}
        if lo or hi:
            y0, y1, approx = lo or hi, hi or lo, True
        elif prec >= 9:
            y0 = y1 = y
            approx = circa
        elif prec == 8:
            y0, y1, approx = y - y % 10, y - y % 10 + 9, True
        elif prec == 7:
            c = (y - 1) // 100 * 100 + 1
            y0, y1, approx = c, c + 99, True
    elif qs:
        # fallback: the hidden "date QS:P571,+1909-00-00T00:00:00Z/9,P1480,Q5727902" string
        m = re.search(r"P571,\+(\d{4})-\d\d-\d\dT[^/]*/(\d+)", qs)
        if m and int(m.group(2)) >= 9:
            y0 = y1 = int(m.group(1))
            approx = CIRCA in qs
            info = {"p571_qs": m.group(0)}
    if re.search(r"\b(ca\.|circa|um|etwa)\b", raw_text, re.I):
        approx = True
    return {"raw": raw_text or None, "year_from": y0, "year_to": y1, "approximate": approx}, info


def places_from(title: str, description: str, archive: str) -> list[str]:
    """Place names: leading title segments up to the first view word, plus the Zinggeler card place."""
    out = []
    segs = [s.strip() for s in title.split(",") if s.strip()]
    if segs and segs[0].lower().startswith("porträt"):
        segs = [s for s in segs[1:] if not VIEW_RE.search(s)]  # "Porträt, Weibliche Person, Sattel (SZ)"
    for s in segs:
        if VIEW_RE.search(s):
            break
        out.append(s)
    if archive == "ZING":
        m = re.search(r"Karteikarte Zinggeler\]:\s*'?([^.,;]+?)\s+SZ\b", description)
        if m:
            out.append(m.group(1).strip())
    seen, res = set(), []
    for p in out:
        p = re.sub(r"\s*\((SZ|Schwyz)\)$", "", p.split("/")[0]).strip()  # "Hauptfront/1909"
        if p and not re.search(r"\d", p) and p.lower() not in seen:
            seen.add(p.lower())
            res.append(p)
    return res


def kind_of(text: str) -> str:
    t = text.lower()
    if "ansichtskarte" in t or "postkarte" in t:
        return "postcard"
    if "flugaufnahme" in t or "luftaufnahme" in t or "fliegeraufnahme" in t:
        return "aerial"
    return "ground"


def fetch_image(thumb_url: str, ead: str) -> dict | None:
    try:
        data = client.get(thumb_url, suffix=".jpg")
    except (FileNotFoundError, RuntimeError) as e:
        print(f"  image failed {ead}: {e}", flush=True)
        return None
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((MAX_EDGE, MAX_EDGE))
    path = IMG_DIR / f"{ead}.jpg"
    ensure(path.parent)
    im.save(path, "JPEG", quality=90)
    return {"path": str(path.relative_to(IMAGES.parent)), "width": im.width, "height": im.height,
            "sha1": hashlib.sha1(path.read_bytes()).hexdigest()}


def build_record(page: dict, entity: dict, cantons: list[str]) -> dict | None:
    m = EAD_RE.search(page["title"])
    ii = (page.get("imageinfo") or [{}])[0]
    if not m or not ii.get("thumburl"):
        return None
    archive, neg, part, suffix = m.groups()
    ead = m.group(0)
    collection, archive_name = COLLECTIONS[archive]
    em = ii.get("extmetadata", {})
    title = strip(em.get("ObjectName", {}).get("value")) or None
    desc = strip(em.get("ImageDescription", {}).get("value"))
    dto = em.get("DateTimeOriginal", {}).get("value", "")
    statements = entity.get("statements") or {}
    date, date_info = parse_date(strip(dto), statements, dto)
    credit_html = em.get("Credit", {}).get("value", "")
    ha = re.search(r"helveticarchives\.ch/detail\.aspx\?id=(\d+)", credit_html, re.I)
    artist = strip(em.get("Artist", {}).get("value"))
    places = places_from(title or "", desc, archive)
    muni = loc = None
    geo_error = None
    if "Schwyz" in cantons and places:
        # swisstopo answers some odd queries with HTTP 503: fall back to the first place only
        for attempt in (places, places[:1]):
            try:
                muni, loc = gazetteer.resolve(attempt)
                geo_error = None
                break
            except RuntimeError as e:
                geo_error = str(e)
    url = ii.get("descriptionurl")
    return {
        "id": f"nb:{ead}",
        "source": "nb",
        "source_id": ead,
        "source_url": url,
        "signature": ead,
        "collection": collection,
        "kind": kind_of(f"{title} {desc}"),
        "title": title,
        "date": date,
        "places": places,
        "municipality": muni,
        "location": loc,
        "camera": None,
        "photographer": None if not artist or "unknown" in artist.lower() else artist,
        "license": {"code": "PDM", "credit": f"Schweizerische Nationalbibliothek, {archive_name} {ead}", "url": url},
        "image": None,
        "parent_id": None,
        "crop_bbox": None,
        "split": "reference",
        "raw": {
            "commons_title": page["title"],
            "commons_pageid": page["pageid"],
            "archive": archive_name,
            "negative_number": neg,
            "negative_part": part or None,
            "suffix": suffix,
            "helveticarchives_id": ha.group(1) if ha else None,
            "helveticarchives_url": f"https://www.helveticarchives.ch/detail.aspx?id={ha.group(1)}" if ha else None,
            "canton_categories": cantons,
            "gazetteer_error": geo_error,
            "description": desc or None,
            "date_text": strip(dto) or None,
            "date_p571": date_info,
            "artist": artist or None,
            "license_short": strip(em.get("LicenseShortName", {}).get("value")) or None,
            "thumb_url": ii.get("thumburl"),
            "original_size": [ii.get("width"), ii.get("height")],
        },
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def fetch(limit: int | None, cantons: list[str]) -> None:
    ensure(RECORDS)
    done = set()
    if RECORDS_FILE.exists():
        done = {json.loads(l)["source_id"] for l in RECORDS_FILE.read_text().splitlines() if l.strip()}
    # list every canton category; a file in several cantons keeps all of them, in --cantons order
    files: dict[int, dict] = {}
    for c in cantons:
        cat = canton_category(CANTONS[c])
        ms = category_files(cat)
        print(f"  {cat}: {len(ms)} files", flush=True)
        for mm in ms:
            f = files.setdefault(mm["pageid"], {"pageid": mm["pageid"], "title": mm["title"], "cantons": []})
            f["cantons"].append(CANTONS[c])
    by_ead: dict[str, dict] = {}
    other = 0
    for f in files.values():
        m = EAD_RE.search(f["title"])
        if not m:
            other += 1
            continue
        by_ead.setdefault(m.group(0), f)  # first upload wins if an EAD id appears twice
    todo = [f for e, f in by_ead.items() if e not in done]
    print(f"{len(files)} files ({other} not WEHR/ZING), {len(by_ead)} EAD ids, {len(done)} done, "
          f"{len(todo)} to fetch", flush=True)
    kept = failed = 0
    with RECORDS_FILE.open("a") as out:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            if limit:
                chunk = chunk[: limit - kept]
            if not chunk:
                break
            ids = "|".join(str(f["pageid"]) for f in chunk)
            pages = {p["pageid"]: p for p in api({"action": "query", "pageids": ids, "prop": "imageinfo",
                                                   "iiprop": "url|extmetadata|size", "iiurlwidth": MAX_EDGE,
                                                   "iiextmetadatalanguage": "de"})["query"]["pages"]}
            ents = api({"action": "wbgetentities", "ids": "|".join(f"M{f['pageid']}" for f in chunk)})["entities"]
            for f in chunk:
                page = pages.get(f["pageid"])
                if not page or page.get("missing"):
                    failed += 1
                    continue
                rec = build_record(page, ents.get(f"M{f['pageid']}", {}), f["cantons"])
                if not rec:
                    failed += 1
                    continue
                rec["image"] = fetch_image(rec["raw"]["thumb_url"], rec["source_id"])
                if not rec["image"]:
                    failed += 1  # no record, so the next run retries it
                    continue
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                kept += 1
                if kept % 25 == 0:
                    print(f"  {kept} kept; last {rec['id']} {rec['date']['raw']} {rec['raw']['canton_categories']}"
                          f" -> {rec['municipality']}", flush=True)
            if limit and kept >= limit:
                break
    print(f"done: {kept} kept this run, {failed} failed, {client.requests} requests", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--cantons", default=",".join(CANTONS), help=f"comma list from {','.join(CANTONS)}")
    a = ap.parse_args()
    cantons = [c.strip().lower() for c in a.cantons.split(",") if c.strip()]
    bad = [c for c in cantons if c not in CANTONS]
    if bad:
        ap.error(f"unknown canton(s) {bad}; choose from {list(CANTONS)}")
    fetch(a.limit, cantons)


if __name__ == "__main__":
    main()
