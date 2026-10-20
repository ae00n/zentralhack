"""ETH-Bibliothek E-Pics Bildarchiv collector (Sharedien API behind ba.e-pics.ethz.ch).

    python -m data_pipeline.scrapers.epics fetch --limit 50          # geotagged, pre-1970, Schwyz box
    python -m data_pipeline.scrapers.epics fetch --postcards          # PK_ / Ans_ items in the box, any date
    python -m data_pipeline.scrapers.epics fetch                      # full run

The API is undocumented. The read-only token is the one the public site embeds in its
homepage HTML; it is read fresh at runtime and never stored. Only CC BY-SA 4.0 and
Public Domain Mark images without eth_download_forbidden are kept. Images: the "Screen"
derivation (805x1200) downscaled to 1024 px. 1 request per second, resumable.
"""

import argparse
import hashlib
import io
import json
import re
from datetime import datetime, timezone

from PIL import Image

from .. import geo
from ..http import PoliteClient
from ..paths import IMAGES, RAW, RECORDS, ensure

API = "https://api.ethz.sharedien.com/api/v10"
HOME = "https://ba.e-pics.ethz.ch/"
BOX = ["47.22,8.38", "46.88,9.03"]  # [N,W], [S,E]
DATE_MAX = "1969-12-31"
LICENSES = {"Public Domain Mark": "PDM", "CC BY-SA 4.0": "CC-BY-SA-4.0"}
PROPS = [
    "file_name", "title", "description", "eth_license", "eth_geo_location", "eth_geo_azimuth",
    "eth_geo_altitude", "eth_dating", "eth_date_range", "eth_photographer", "eth_doi_link",
    "eth_download_forbidden", "eth_copyright_notice", "eth_is_part_of", "eth_image_stock_number",
    "eth_sMapshot_Link", "eth_sMaphot_Swissnames", "eth_originaltitel",
]
MAX_EDGE = 1024
PAGE = 200

RECORDS_FILE = RECORDS / "epics.jsonl"
IMG_DIR = IMAGES / "epics"
STATE = RAW / "epics"

client = PoliteClient(min_interval=1.0)
_token: str | None = None


def token() -> str:
    global _token
    if _token is None:
        html = client.text(HOME, cache=False)
        m = re.search(r'<sharedien-adapter[^>]*\btoken="([0-9A-Fa-f]+)"', html) or re.search(r'token="([0-9A-F]{32,})"', html)
        if not m:
            raise RuntimeError("E-Pics token not found in homepage HTML")
        _token = m.group(1)
    return _token


def _auth() -> dict:
    return {"Authorization": f"Bearer {token()}"}


def search(filters: list[dict], cursor: str | None = None, limit: int = PAGE) -> tuple[list[dict], str | None, int]:
    params = {"limit": limit}
    if cursor:
        params["cursor"] = cursor
    body = {"q": "", "advancedSearchFilters": filters, "includePropertyDefinitionIdentifiers": PROPS}
    r = client.client.post(f"{API}/assets/search", params=params, json=body, headers=_auth())
    client.requests += 1
    client._wait()
    r.raise_for_status()
    data = r.json()
    return data.get("items", []), data.get("cursor"), int(r.headers.get("x-total-count", -1))


def props(item: dict) -> dict:
    out = {}
    for p in item.get("properties", []):
        vals = p.get("propertyValues") or []
        if not vals:
            continue
        v = vals[0]
        val = (v.get("propertyValue") or [{}])[0].get("value")
        out[p["propertyDefinitionIdentifier"]] = val
        if v.get("propertyListItemIdentifier"):
            out[p["propertyDefinitionIdentifier"] + "__id"] = v["propertyListItemIdentifier"]
    return out


def kind_for(stem: str) -> str:
    if stem.startswith("PK_"):
        return "postcard"
    if stem.startswith(("LBS_", "Com_", "DES_")):
        return "aerial"
    return "unknown"


def parse_dating(raw: str | None) -> dict:
    raw = (raw or "").strip() or None
    years = [int(y) for y in re.findall(r"\b(1[6-9]\d\d|20[0-2]\d)\b", raw or "")]
    return {
        "raw": raw,
        "year_from": min(years) if years else None,
        "year_to": max(years) if years else None,
        "approximate": bool(raw and re.search(r"ca\.|\?|um |circa", raw, re.I)),
    }


def screen_image(asset_id: str, stem: str) -> dict | None:
    """Download the Screen derivation once to data/images/epics/<stem>.jpg (shared with smapshot.py)."""
    ensure(IMG_DIR)
    path = IMG_DIR / f"{stem}.jpg"
    if not path.exists():
        r = client.client.get(f"{API}/assets/{asset_id}/derivations", headers=_auth())
        client.requests += 1
        client._wait()
        r.raise_for_status()
        screen = next((d for d in r.json() if d.get("derivationTypeIdentifier") == "Screen"), None)
        if not screen:
            return None
        blob = client.get(screen["uri"], cache=False)
        im = Image.open(io.BytesIO(blob)).convert("RGB")
        im.thumbnail((MAX_EDGE, MAX_EDGE))
        im.save(path, "JPEG", quality=90)
    with Image.open(path) as im:
        w, h = im.size
    return {"path": str(path.relative_to(IMAGES.parent)), "width": w, "height": h,
            "sha1": hashlib.sha1(path.read_bytes()).hexdigest()}


def find_by_file_name(stem: str) -> dict | None:
    """Look up one asset by file name (used by smapshot.py to get ETH images)."""
    items, _, _ = search([{"op": "Contains", "propertyDefinitionIdentifier": "file_name", "q": [stem]}], limit=5)
    for it in items:
        if it.get("fileName", "").rsplit(".", 1)[0] == stem:
            return it
    return None


def allowed(p: dict) -> str | None:
    if str(p.get("eth_download_forbidden", "")).lower() == "true":
        return None
    return LICENSES.get(p.get("eth_license") or "")


def visible_names(raw: str | None, n: int = 15) -> list[str]:
    """eth_sMaphot_Swissnames ("Gersau 9991 m; Seelisberg 13483 m; ...") -> nearest place names first."""
    out = []
    for part in (raw or "").split(";"):
        m = re.match(r"\s*(.+?)\s+(\d+)\s*m\s*$", part)
        if m:
            out.append((int(m.group(2)), m.group(1).split(",")[0].strip()))
    return [name for _, name in sorted(out)[:n]]


def build_record(item: dict, p: dict, lic: str, image: dict | None) -> dict:
    stem = item["fileName"].rsplit(".", 1)[0]
    lat = lon = None
    if p.get("eth_geo_location"):
        try:
            lat, lon = (float(x) for x in p["eth_geo_location"].split(","))
        except ValueError:
            pass
    muni = geo.municipality_at(lat, lon)
    photographer = p.get("eth_photographer")
    camera = None
    if p.get("eth_geo_azimuth") or p.get("eth_geo_altitude"):
        camera = {"lat": lat, "lon": lon,
                  "altitude_m": float(p["eth_geo_altitude"]) if p.get("eth_geo_altitude") else None,
                  "azimuth": float(p["eth_geo_azimuth"]) if p.get("eth_geo_azimuth") else None,
                  "tilt": None, "roll": None, "focal": None}
    return {
        "id": f"epics:{stem}",
        "source": "epics",
        "source_id": stem,
        "source_url": p.get("eth_doi_link") or f"https://ba.e-pics.ethz.ch/catalog/ETHBIB.Bildarchiv/r/{item['identifier']}",
        "signature": stem,
        "collection": p.get("eth_is_part_of"),
        "kind": kind_for(stem),
        "title": p.get("title") or p.get("eth_originaltitel"),
        "date": parse_dating(p.get("eth_dating")),
        "places": visible_names(p.get("eth_sMaphot_Swissnames")),  # names Smapshot computed as visible, nearest first
        "municipality": muni["name"] if muni else None,
        "location": {"lat": lat, "lon": lon, "method": "epics_geo", "precision_m": 500} if lat is not None else None,
        "camera": camera,
        "photographer": photographer,
        "license": {
            "code": lic,
            "credit": f"ETH-Bibliothek Zürich, Bildarchiv / {photographer or 'Unbekannt'} / {stem} / {p.get('eth_license')}",
            "url": p.get("eth_doi_link"),
        },
        "image": image,
        "parent_id": None,
        "crop_bbox": None,
        "split": "reference",
        "raw": {**p, "asset_identifier": item["identifier"], "in_canton": muni is not None},
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _done_ids() -> set[str]:
    if not RECORDS_FILE.exists():
        return set()
    return {json.loads(l)["id"] for l in RECORDS_FILE.read_text().splitlines() if l.strip()}


def fetch(limit: int | None, postcards: bool) -> None:
    ensure(RECORDS, STATE)
    box = {"op": "InBoundingBox", "propertyDefinitionIdentifier": "eth_geo_location", "q": BOX}
    if postcards:
        runs = [("postcards_" + pre, [box, {"op": "Contains", "propertyDefinitionIdentifier": "file_name", "q": [pre]}])
                for pre in ("PK_", "Ans_")]
    else:
        runs = [("geo_pre1970", [box, {"op": "LessThanOrEquals", "propertyDefinitionIdentifier": "eth_date_range", "q": [DATE_MAX]}])]
    done = _done_ids()
    kept = skipped = 0
    with RECORDS_FILE.open("a") as out:
        for name, filters in runs:
            cursor_file = STATE / f"cursor_{name}.txt"
            cursor = cursor_file.read_text().strip() or None if cursor_file.exists() else None
            if cursor == "END":
                print(f"{name}: already complete", flush=True)
                continue
            total_printed = False
            while True:
                items, nxt, total = search(filters, cursor)
                if not total_printed:
                    print(f"{name}: {total} assets match (x-total-count)", flush=True)
                    total_printed = True
                for it in items:
                    stem = it.get("fileName", "").rsplit(".", 1)[0]
                    if postcards and not stem.startswith(("PK_", "Ans_")):
                        continue
                    if f"epics:{stem}" in done:
                        continue
                    p = props(it)
                    lic = allowed(p)
                    if not lic:
                        skipped += 1
                        continue
                    image = screen_image(it["identifier"], stem)
                    rec = build_record(it, p, lic, image)
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                    done.add(rec["id"])
                    kept += 1
                    if kept % 10 == 0:
                        print(f"  {kept} kept, {skipped} skipped by license; last {stem} {rec['date']['raw']!r} -> {rec['municipality']}", flush=True)
                    if limit and kept >= limit:
                        print(f"limit reached: {kept} kept, {skipped} skipped", flush=True)
                        return
                if not nxt or not items:
                    cursor_file.write_text("END")
                    break
                cursor = nxt
                cursor_file.write_text(cursor)
    print(f"done: {kept} kept, {skipped} skipped by license", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--postcards", action="store_true", help="PK_ / Ans_ items in the Schwyz box, any date")
    a = ap.parse_args()
    fetch(a.limit, a.postcards)


if __name__ == "__main__":
    main()
