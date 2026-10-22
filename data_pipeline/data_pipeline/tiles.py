"""Offline swisstopo tile cache for the demo laptop (docs/CONTRACTS.md section 1, `data/tiles/`).

    python -m data_pipeline.tiles plan      # tile counts per layer, nothing downloaded
    python -m data_pipeline.tiles fetch     # download (resumable, at most 5 tiles/s)

Areas are the demo cards (`splits/demo.json`) plus the famous demo places. Per area:

    layer                     z12-14   z15-16   z17
    zeitreihen (one per TIME) 5 km     2 km     -
    swissimage current        5 km     2 km     1 km

Zeitreihen: one valid TIME per decade (1870s to 2020s), read from WMTS GetCapabilities, so the
backend never asks for a TIME that does not exist. Tiles land in
`data/tiles/<layer>/<time>/<z>/<x>/<y>.<ext>`; `data/tiles/manifest.json` lists what is cached
({layer: {times, zooms, ext, areas}}) so the backend can serve `map_years` offline.
"""

import argparse
import json
import math
import re
from datetime import datetime, timezone

from .http import PoliteClient
from .jsonl import write_json
from .paths import DATA_DIR, SPLITS, ensure

TILES = DATA_DIR / "tiles"
WMTS = "https://wmts.geo.admin.ch"
CAPS = f"{WMTS}/EPSG/3857/1.0.0/WMTSCapabilities.xml"
ZEITREIHEN = "ch.swisstopo.zeitreihen"
SWISSIMAGE = "ch.swisstopo.swissimage"
# (layer, ext, {zoom: radius in km})
BUDGET = [
    (ZEITREIHEN, "png", {12: 5, 13: 5, 14: 5, 15: 2, 16: 2}),
    (SWISSIMAGE, "jpeg", {12: 5, 13: 5, 14: 5, 15: 2, 16: 2, 17: 1}),
]
# demo places that must be covered even if demo.json changes (lat, lon)
PLACES = {
    "Schwyz Hauptplatz": (47.0207, 8.6541),
    "Brunnen": (46.9958, 8.6066),
    "Einsiedeln Kloster": (47.1265, 8.7516),
    "Rigi Kulm": (47.0565, 8.4851),
    "Grosser Mythen": (47.0294, 8.6838),
}


def zeitreihen_times(client: PoliteClient) -> list[str]:
    """One valid TIME per decade, the last year of each decade that has a map."""
    xml = client.get(CAPS, suffix=".xml").decode()
    i = xml.find(f"<ows:Identifier>{ZEITREIHEN}</ows:Identifier>")
    values = re.findall(r"<Value>(\d{8})</Value>", xml[i:xml.find("</Layer>", i)])
    by_decade = {}
    for v in sorted(values):
        if int(v[:4]) >= 1870:
            by_decade[int(v[:4]) // 10 * 10] = v  # sorted ascending: the last one per decade wins
    return [by_decade[d] for d in sorted(by_decade)]


def areas() -> dict[str, tuple[float, float]]:
    out = dict(PLACES)
    demo = SPLITS / "demo.json"
    if demo.exists():
        from .api import get_record
        for c in json.loads(demo.read_text()):
            loc = (get_record(c["id"]) or {}).get("location")
            if loc:
                out[c["id"]] = (loc["lat"], loc["lon"])
    return out


def _xy(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def tiles_around(lat: float, lon: float, z: int, radius_km: float) -> set[tuple[int, int, int]]:
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * math.cos(math.radians(lat)))
    x0, y0 = _xy(lat + dlat, lon - dlon, z)
    x1, y1 = _xy(lat - dlat, lon + dlon, z)
    return {(z, x, y) for x in range(int(x0), int(x1) + 1) for y in range(int(y0), int(y1) + 1)}


def plan(times: list[str]) -> list[tuple[str, str, str, set]]:
    """[(layer, time, ext, {(z, x, y)})]; overlapping areas share tiles."""
    pts = areas().values()
    jobs = []
    for layer, ext, zooms in BUDGET:
        tiles = set()
        for lat, lon in pts:
            for z, r in zooms.items():
                tiles |= tiles_around(lat, lon, z, r)
        for t in (times if layer == ZEITREIHEN else ["current"]):
            jobs.append((layer, t, ext, tiles))
    return jobs


def fetch(dry_run: bool = False) -> dict:
    client = PoliteClient(min_interval=0.2, cache_dir=TILES / ".caps")  # 5 tiles/s; only the caps XML is cached
    times = zeitreihen_times(client)
    jobs = plan(times)
    total = sum(len(t) for *_, t in jobs)
    print(f"{len(times)} zeitreihen times, {len(areas())} areas, {total} tiles", flush=True)
    if dry_run:
        for layer, t, _, tiles in jobs:
            print(f"  {layer} {t}: {len(tiles)}")
        return {"tiles": total}
    done = fetched = missing = 0
    for layer, t, ext, tiles in jobs:
        for z, x, y in sorted(tiles):
            path = TILES / layer / t / str(z) / str(x) / f"{y}.{ext}"
            done += 1
            if path.exists():
                continue
            try:
                data = client.get(f"{WMTS}/1.0.0/{layer}/default/{t}/3857/{z}/{x}/{y}.{ext}", cache=False)
            except FileNotFoundError:  # outside the layer's coverage
                missing += 1
                continue
            ensure(path.parent)
            path.write_bytes(data)
            fetched += 1
            if fetched % 500 == 0:
                print(f"  {done}/{total} ({fetched} fetched, {missing} missing)", flush=True)
    manifest = {
        layer: {"times": times if layer == ZEITREIHEN else ["current"], "ext": ext, "zooms": sorted(zooms),
                "radius_km": {str(z): r for z, r in zooms.items()}}
        for layer, ext, zooms in BUDGET
    }
    manifest["areas"] = {k: {"lat": lat, "lon": lon} for k, (lat, lon) in areas().items()}
    manifest["map_years"] = [int(t) for t in times]
    manifest["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_json(TILES / "manifest.json", manifest)
    print(f"done: {fetched} fetched, {missing} missing, {total} total -> {TILES}")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "fetch"])
    a = ap.parse_args()
    fetch(dry_run=a.cmd == "plan")


if __name__ == "__main__":
    main()
