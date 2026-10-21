"""Staatsarchiv Schwyz (scopeArchiv Query) scraper.

    python -m data_pipeline.scrapers.staatsarchiv ids   --collection SG.CIV.12
    python -m data_pipeline.scrapers.staatsarchiv fetch --collection SG.CIV.12 --limit 50

`ids` walks the archive tree: archivplansuche.aspx?ID=<x> shows a window of about 100
siblings centred on x, so requesting the last (or first) id of a window moves it 50 on.
`fetch` reads each detail page and the largest preview (767 px), crops the watermark strip
and appends a PhotoRecord (docs/CONTRACTS.md section 2). Both steps resume where they stopped.

Images are NOT openly licensed: they stay in data/ (gitignored) and are never published.
"""

import argparse
import hashlib
import io
import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from PIL import Image

from .. import gazetteer
from ..http import PoliteClient
from ..paths import IMAGES, RAW, RECORDS, ensure

BASE = "https://query.staatsarchiv.sz.ch"
COLLECTIONS = {
    "SG.CIV.12": {"node": "267225", "seed": "514200", "kind": "postcard"},
    "SG.CIV.04": {"node": "267220", "seed": "841227", "kind": "aerial"},  # seed found via OpenSearch: the tree hides this node's children
}
WATERMARK_PX = 20  # "Staatsarchiv Schwyz" + signature burned into the bottom strip
MAX_EDGE = 1024

OUT_DIR = RAW / "staatsarchiv"
RECORDS_FILE = RECORDS / "staatsarchiv.jsonl"
IMG_DIR = IMAGES / "staatsarchiv"

client = PoliteClient(min_interval=2.0, cache_dir=OUT_DIR / "http")


# ---------- tree walk ----------

def _node_data(html: str) -> list:
    i = html.find('"nodeData":')
    data, _ = json.JSONDecoder().raw_decode(html[i + len('"nodeData":'):])
    return data


def _find(nodes: list, value: str) -> dict | None:
    for n in nodes:
        if n.get("value") == value:
            return n
        r = _find(n.get("items", []), value)
        if r:
            return r
    return None


def _window(entry_id: str, node: str) -> tuple[list[tuple[str, str]], bool, bool]:
    """Siblings under `node` around entry_id: ([(id, label)], has_prev, has_next)."""
    html = client.text(f"{BASE}/archivplansuche.aspx?ID={entry_id}", cache=False)
    parent = _find(_node_data(html), node)
    if parent is None:
        raise RuntimeError(f"{entry_id} is not under node {node}")
    soup = BeautifulSoup(html, "lxml")
    labels = [s.get_text(" ", strip=True) for s in soup.select("span.rtIn")]
    ids = [n["value"] for n in parent["items"]]
    by_id = {}
    # tree spans are rendered in node order; map label text by position over the full flattened tree
    flat = []

    def walk(ns):
        for n in ns:
            flat.append(n["value"])
            walk(n.get("items", []))

    walk(_node_data(html))
    for v, text in zip(flat, labels):
        by_id[v] = text
    rows = [(v, by_id.get(v, "")) for v in ids if not v.startswith("-")]
    has_prev = "vorhergehenden 100" in html
    has_next = "nächsten 100" in html
    return rows, has_prev, has_next


def _seed_for(collection: str) -> str:
    seed = COLLECTIONS[collection]["seed"]
    if seed:
        return seed
    # open the collection node itself and take its first real child if the tree shows it
    node = COLLECTIONS[collection]["node"]
    html = client.text(f"{BASE}/archivplansuche.aspx?ID={node}", cache=False)
    parent = _find(_node_data(html), node)
    kids = [n["value"] for n in (parent or {}).get("items", []) if not n["value"].startswith("-")]
    if not kids:
        raise RuntimeError(f"no seed id for {collection}; add one to COLLECTIONS")
    return kids[0]


def collect_ids(collection: str) -> list[dict]:
    ensure(OUT_DIR)
    out = OUT_DIR / f"ids_{collection}.jsonl"
    node = COLLECTIONS[collection]["node"]
    seen: dict[str, str] = {}
    order: list[str] = []

    def add(rows):
        new = 0
        for v, text in rows:
            if v not in seen:
                seen[v] = text
                order.append(v)
                new += 1
        return new

    seed = _seed_for(collection)
    rows, has_prev, has_next = _window(seed, node)
    add(rows)
    first, last = rows[0][0], rows[-1][0]
    while has_next:
        rows, _, has_next = _window(last, node)
        if add(rows) == 0 and rows[-1][0] == last:
            break
        last = rows[-1][0]
        print(f"  forward: {len(seen)} ids", flush=True)
    while has_prev:
        rows, has_prev, _ = _window(first, node)
        if add(rows) == 0 and rows[0][0] == first:
            break
        first = rows[0][0]
        print(f"  backward: {len(seen)} ids", flush=True)

    def sig_key(v):
        m = re.match(r"(SG\.CIV\.\d+)\.(\d+)", seen[v])
        return (int(m.group(2)) if m else 10**9, v)

    rows = [{"id": v, "label": seen[v]} for v in sorted(order, key=sig_key)]
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"{collection}: {len(rows)} ids -> {out}")
    return rows


# ---------- detail + image ----------

def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    fields = {}
    for td in soup.select("td.veXDetailAttributLabel"):
        label = td.get_text(" ", strip=True).rstrip(":").strip()
        val = td.find_next_sibling("td")
        if val is None or label in fields:
            continue
        fields[label] = val.get_text(" ", strip=True)
    fields.pop("Ansichtsbild", None)
    return fields


def parse_date(raw: str | None) -> dict:
    raw = (raw or "").strip()
    out = {"raw": raw or None, "year_from": None, "year_to": None, "approximate": False}
    if not raw or raw.lower().startswith("keine angabe"):
        return out
    out["approximate"] = bool(re.search(r"\bca\.?|\?|circa", raw, re.I))
    years = [int(y) for y in re.findall(r"\b(1[6-9]\d\d|20[0-2]\d)\b", raw)]
    century = re.search(r"\b(1[6-9]|20)\.\s*Jh", raw)
    if years:
        out["year_from"], out["year_to"] = min(years), max(years)
    elif century:
        c = int(century.group(1))
        out["year_from"], out["year_to"], out["approximate"] = (c - 1) * 100 + 1, c * 100, True
    # "vor 1920" / "bis 1920" is only an upper bound, "nach 1920" / "ab 1920" only a lower one
    if years and re.match(r"(vor|bis)\b", raw, re.I):
        out["year_from"], out["approximate"] = None, True
    elif years and re.match(r"(nach|ab)\b", raw, re.I):
        out["year_to"], out["approximate"] = None, True
    return out


def save_image(veid: str) -> dict | None:
    url = f"{BASE}/getimage.aspx?veid={veid}&deid=10&sqnznr=1&width=767&klid=9"
    try:
        blob = client.get(url, suffix=".jpg")
    except FileNotFoundError:
        return None
    im = Image.open(io.BytesIO(blob)).convert("RGB")
    if im.height <= WATERMARK_PX * 3:
        return None
    im = im.crop((0, 0, im.width, im.height - WATERMARK_PX))
    im.thumbnail((MAX_EDGE, MAX_EDGE))
    ensure(IMG_DIR)
    path = IMG_DIR / f"{veid}.jpg"
    im.save(path, "JPEG", quality=90)
    return {
        "path": str(path.relative_to(IMAGES.parent)),
        "width": im.width,
        "height": im.height,
        "sha1": hashlib.sha1(path.read_bytes()).hexdigest(),
    }


def build_record(veid: str, collection: str, f: dict, image: dict | None) -> dict:
    places = [p.strip() for p in (f.get("Thema") or "").split(";") if p.strip()]
    muni, loc = gazetteer.resolve(places) if places else (None, None)
    sig = f.get("Signatur")
    return {
        "id": f"stasz:{veid}",
        "source": "staatsarchiv",
        "source_id": veid,
        "source_url": f"{BASE}/detail.aspx?ID={veid}",
        "signature": sig,
        "collection": collection,
        "kind": COLLECTIONS[collection]["kind"],
        "title": f.get("Titel"),
        "date": parse_date(f.get("Entstehungszeitraum")),
        "places": places,
        "municipality": muni,
        "location": loc,
        "camera": None,
        "photographer": f.get("Autor/Fotograf/Künstler"),
        "license": {
            "code": "stasz-private",
            "credit": f"Staatsarchiv Schwyz, {sig}" if sig else "Staatsarchiv Schwyz",
            "url": None,
        },
        "image": image,
        "parent_id": None,
        "crop_bbox": None,
        "split": "none",
        "raw": f,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def fetch(collection: str, limit: int | None, spread: bool = False) -> None:
    ids_file = OUT_DIR / f"ids_{collection}.jsonl"
    if not ids_file.exists():
        collect_ids(collection)
    ids = [json.loads(l)["id"] for l in ids_file.read_text().splitlines()]
    ensure(RECORDS)
    done = set()
    if RECORDS_FILE.exists():
        done = {json.loads(l)["source_id"] for l in RECORDS_FILE.read_text().splitlines() if l.strip()}
    todo = [v for v in ids if v not in done]
    if limit:
        # --spread takes evenly spaced ids so a test batch covers the whole collection
        todo = todo[:: max(1, len(todo) // limit)][:limit] if spread else todo[:limit]
    print(f"{collection}: {len(ids)} ids, {len(done)} already done, fetching {len(todo)}", flush=True)
    with RECORDS_FILE.open("a") as out:
        for n, veid in enumerate(todo, 1):
            try:
                f = parse_detail(client.text(f"{BASE}/detail.aspx?ID={veid}"))
            except FileNotFoundError:
                print(f"  {veid}: detail 404, skipped", flush=True)
                continue
            if not f.get("Signatur", "").startswith(collection):
                print(f"  {veid}: signature {f.get('Signatur')!r} not in {collection}, skipped", flush=True)
                continue
            image = save_image(veid) if f.get("Digitalisat vorhanden", "").lower().startswith(("ja", "yes")) else None
            rec = build_record(veid, collection, f, image)
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            if n % 10 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)} {rec['signature']} {rec['date']['raw']!r} -> {rec['municipality']}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ids", "fetch"])
    ap.add_argument("--collection", default="SG.CIV.12", choices=list(COLLECTIONS))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--spread", action="store_true", help="with --limit: sample evenly across the collection")
    a = ap.parse_args()
    if a.cmd == "ids":
        collect_ids(a.collection)
    else:
        fetch(a.collection, a.limit, a.spread)


if __name__ == "__main__":
    main()
