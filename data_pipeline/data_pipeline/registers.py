"""Offline registers for the agent: find_building, address_at, landmarks_near.

    python -m data_pipeline.registers build    # GWR entrances -> addresses.json, swissNAMES3D -> landmarks.json
    python -m data_pipeline.registers check    # known answers (Acherhof, Mythen) must come out right

- addresses.json: every official GWR entrance in the canton (data/raw/gwr/data.sqlite, 63,922 entrances)
  with street, number, PLZ, Ortschaft (postal locality), Gemeinde, building name, class, year built,
  floors (GASTW) and footprint (GAREA).
  Buildings that exist, or were demolished in 2003 or later (the photos are 2003 to 2013).
- landmarks.json: named peaks, hills, passes, lakes, islands, rivers, valleys and cable cars from
  swissNAMES3D (swisstopo, data/raw/swissnames3d/swissnames3d_2026.csv.zip), canton plus 25 km around,
  because the mountains seen from Schwyz (Pilatus, Rigi, Glärnisch) are partly outside it.

No network at query time. address_at falls back to the live swisstopo lookup (places.address_lookup)
only for a point outside the canton, where the GWR dump has no entrances.
"""

import argparse
import csv
import io
import json
import re
import sqlite3
import zipfile
from functools import lru_cache

from . import geo
from .paths import GAZETTEER, RAW, ensure
from .places import CARE, GBD_NR, GWR_KINDS, _haversine_m, _lv95_to_wgs84, _norm, is_generic, named_buildings

GWR_FILE = RAW / "gwr" / "data.sqlite"
NAMES_ZIP = RAW / "swissnames3d" / "swissnames3d_2026.csv.zip"
ADDRESSES_FILE = GAZETTEER / "addresses.json"
LANDMARKS_FILE = GAZETTEER / "landmarks.json"
# canton box in LV95 (E, N) plus 25 km
BOX = (2655000, 1165000, 2760000, 1260000)
# swissNAMES3D OBJEKTART -> kind shown to the agent; rank: lower comes first at equal distance band
LANDMARK_KINDS = {
    "Hauptgipfel": ("Berg", 0), "Alpiner Gipfel": ("Berg", 0), "Gipfel": ("Berg", 1), "Haupthuegel": ("Hügel", 2),
    "Huegel": ("Hügel", 3), "Felskopf": ("Berg", 3), "Massiv": ("Bergmassiv", 1), "Pass": ("Pass", 2),
    "Strassenpass": ("Pass", 2), "See": ("See", 0), "Seeteil": ("See", 1), "Seeinsel": ("Insel", 1),
    "Fliessgewaesser": ("Fluss/Bach", 2), "Wasserfall": ("Wasserfall", 2), "Tal": ("Tal", 3), "Haupttal": ("Tal", 1),
    "Gletscher": ("Gletscher", 2), "Luftseilbahn": ("Bergbahn", 2), "Gondelbahn": ("Bergbahn", 2),
    "Sesselbahn": ("Bergbahn", 3), "Aussichtspunkt": ("Aussichtspunkt", 3),
}
OTHER_LANGUAGES = {"Franzoesisch inkl. Lokalsprachen", "Italienisch inkl. Lokalsprachen",
                   "Rumantsch Grischun inkl. Lokalsprachen"}  # "Lac des Quatre-Cantons" next to the German name
CELL = 0.005  # about 550 x 380 m grid cell for the point index


# ---------------------------------------------------------------- build

def build_addresses() -> int:
    db = sqlite3.connect(GWR_FILE)
    bld = {}
    for egid, name, klass, gem, built, status, gone, floors, area in db.execute(
            "select EGID, GBEZ, GKLAS, GGDENAME, GBAUJ, GSTAT, GABBJ, GASTW, GAREA from building"):
        if not (status == 1004 or (status == 1007 and (gone or 0) >= 2003)):
            continue
        name = GBD_NR.sub("", (name or "").strip()).strip() or None
        if name and (is_generic(name) or re.match(r"^[^,]+, ?\d", name)):
            name = None
        kind = "Alters-/Pflegeheim" if name and CARE.search(name) else GWR_KINDS.get(klass)
        bld[egid] = {"name": name, "kind": kind, "municipality": gem, "year_built": built,
                     "demolished": gone if status == 1007 else None, "floors": floors, "area_m2": area}
    out = []
    for egid, street, num, plz, ort, e, n, official in db.execute(
            "select EGID, STRNAME, DEINR, DPLZ4, DPLZNAME, DKODE, DKODN, DOFFADR from entrance"):
        b = bld.get(egid)
        if b is None or not street or e is None:
            continue
        lat, lon = _lv95_to_wgs84(e, n)
        out.append({"egid": egid, "street": street, "number": num or None,
                    "address": f"{street} {num or ''}".strip(), "zip": str(plz) if plz else None,
                    "ortschaft": ort, "lat": round(lat, 6), "lon": round(lon, 6),
                    "official": official == 1, **b})
    _write(ADDRESSES_FILE, out)
    return len(out)


def build_landmarks() -> int:
    z = zipfile.ZipFile(NAMES_ZIP)
    out, seen = [], set()
    for member in z.namelist():
        if not member.endswith(".csv"):
            continue
        for row in csv.DictReader(io.TextIOWrapper(z.open(member), encoding="utf-8-sig"), delimiter=";"):
            kind = LANDMARK_KINDS.get(row["OBJEKTART"])
            if not kind or not row["NAME"] or not row["E"] or row["SPRACHCODE"] in OTHER_LANGUAGES:
                continue
            e, n = float(row["E"]), float(row["N"])
            if not (BOX[0] <= e <= BOX[2] and BOX[1] <= n <= BOX[3]):
                continue
            key = (row["NAME"], kind[0], round(e, -3), round(n, -3))  # river parts and name variants once
            if key in seen:
                continue
            seen.add(key)
            lat, lon = _lv95_to_wgs84(e, n)
            mun = geo.municipality_at(lat, lon)
            out.append({"name": row["NAME"], "kind": kind[0], "rank": kind[1], "type": row["OBJEKTART"],
                        "lat": round(lat, 6), "lon": round(lon, 6),
                        "ele": round(float(row["Z"])) if row.get("Z") else None,
                        "municipality": mun["name"] if mun else None})
    _write(LANDMARKS_FILE, out)
    return len(out)


def _write(path, rows) -> None:
    ensure(GAZETTEER)
    tmp = path.with_suffix(".json.tmp")  # rename, so a running agent never reads half a file
    tmp.write_text(json.dumps(rows, ensure_ascii=False))
    tmp.replace(path)


# ---------------------------------------------------------------- query

def _grid(rows: list[dict]) -> dict:
    g = {}
    for r in rows:
        g.setdefault((int(r["lat"] // CELL), int(r["lon"] // CELL)), []).append(r)
    return g


@lru_cache(maxsize=1)
def _addresses() -> tuple[list[dict], dict]:
    rows = json.loads(ADDRESSES_FILE.read_text(encoding="utf-8")) if ADDRESSES_FILE.exists() else []
    return rows, _grid(rows)


@lru_cache(maxsize=1)
def _landmarks() -> list[dict]:
    return json.loads(LANDMARKS_FILE.read_text(encoding="utf-8")) if LANDMARKS_FILE.exists() else []


def _near(lat: float, lon: float, radius_m: float) -> list[tuple[float, dict]]:
    _, grid = _addresses()
    reach = int(radius_m / 380) + 1
    ci, cj = int(lat // CELL), int(lon // CELL)
    out = []
    for i in range(ci - reach, ci + reach + 1):
        for j in range(cj - reach, cj + reach + 1):
            for r in grid.get((i, j), ()):
                d = _haversine_m(lat, lon, r["lat"], r["lon"])
                if d <= radius_m:
                    out.append((d, r))
    out.sort(key=lambda x: x[0])
    return out


def address_at(lat: float, lon: float, radius_m: int = 100, limit: int = 10, year: int | None = None) -> dict:
    """What is at a point, offline: {lat, lon, ortschaft, plz, municipality, bfs_nr, canton, in_canton,
    addresses, source}. Same shape as places.address_lookup, so callers can swap them.

    ortschaft and plz: from the nearest official entrance within 500 m. municipality: the Gemeinde
    polygon containing the point. addresses: official entrances within radius_m, nearest first, each with
    the building name (null when the register only has a type like "Einfamilienhaus"). year: the photo's
    capture year; buildings built after it are left out (they were not there yet).
    """
    mun = geo.municipality_at(lat, lon)
    if mun is None:  # outside the canton: no GWR entrances here, ask swisstopo
        from .places import address_lookup
        return address_lookup(lat, lon, radius_m, limit)
    near = [(d, r) for d, r in _near(lat, lon, max(radius_m, 500))
            if year is None or not r["year_built"] or r["year_built"] <= year]
    first = near[0][1] if near else {}
    addrs = [{"street": r["street"], "number": r["number"], "address": r["address"], "zip": r["zip"],
              "ortschaft": r["ortschaft"], "municipality": r["municipality"], "distance_m": round(d),
              "lat": r["lat"], "lon": r["lon"], "egid": r["egid"], "building": r["name"], "kind": r["kind"],
              "year_built": r["year_built"]}
             for d, r in near if d <= radius_m]
    return {"lat": lat, "lon": lon, "ortschaft": first.get("ortschaft"), "plz": first.get("zip"),
            "municipality": mun["name"], "bfs_nr": mun["bfs_nr"], "canton": "SZ", "in_canton": True,
            "addresses": addrs[:limit], "source": "GWR (Gebäude- und Wohnungsregister), swissBOUNDARIES3D"}


STOP = {"hotel", "restaurant", "gasthaus", "kirche", "kapelle", "pfarrkirche", "schulhaus", "schule", "haus",
        "zentrum", "alterszentrum", "altersheim", "pflegeheim", "bahnhof", "station", "kloster", "strasse",
        "gasthof", "pension", "cafe", "café", "bad", "camping", "sport", "sportanlage", "turnhalle", "villa"}


def _gem(s: str | None) -> str:
    return _norm(re.sub(r"\s*\((SZ|sz)\)\s*$", "", s or ""))


def find_building(name: str, gemeinde: str | None = None, limit: int = 10) -> list[dict]:
    """Named buildings and places by name, with their official address.

    [{name, kind, lat, lon, address, ortschaft, municipality, source, egid?, match}]
    match: "name" when the whole query is in the name, "word" when only a distinctive word of it is
    (e.g. "Hotel Waldstätterhof Brunnen" -> "Waldstätterhof"). gemeinde narrows the search (with or
    without "(SZ)"). Generic register entries ("Einfamilienhaus") are never returned.
    """
    def pick(query: str) -> list[dict]:
        hits = named_buildings(name=query, limit=200)
        if gemeinde:
            hits = [h for h in hits if _gem(h.get("municipality")) == _gem(gemeinde)]
        return [h for h in hits if not h.get("generic")]

    hits, match = pick(name), "name"
    if not hits:
        words = sorted((w for w in _norm(name).split() if len(w) >= 5 and w not in STOP
                        and (not gemeinde or w != _gem(gemeinde))), key=len, reverse=True)
        for w in words:
            if (hits := pick(w)):
                match = "word"
                break
    out = []
    for h in hits[:limit]:
        near = _near(h["lat"], h["lon"], 80)
        r = near[0][1] if near else {}
        out.append({"name": h["name"], "kind": h["kind"], "lat": h["lat"], "lon": h["lon"],
                    "address": h.get("address") or r.get("address"),
                    "ortschaft": h.get("locality") or r.get("ortschaft"),
                    "municipality": h.get("municipality"), "source": h.get("source"), "egid": h.get("egid"),
                    "match": match})
    return out


def building_facts(lat: float, lon: float, radius_m: int = 60) -> dict | None:
    """The largest register building within radius_m: {egid, name, floors, area_m2, year_built} (GWR).
    Floors and footprint tell look-alike buildings apart (a 6-storey care home vs a 3-storey hospital)."""
    rows = [r for _, r in _near(lat, lon, radius_m) if r.get("area_m2")]
    if not rows:
        return None
    r = max(rows, key=lambda r: r["area_m2"])
    return {k: r.get(k) for k in ("egid", "name", "floors", "area_m2", "year_built")}


def find_address(street: str, number: str | None = None, gemeinde: str | None = None, limit: int = 10) -> list[dict]:
    """Official entrances on a street ("Grundstrasse", or "Grundstr."), optionally a house number and Gemeinde.

    [{address, street, number, zip, ortschaft, municipality, lat, lon, egid, building}], the exact number
    first, else the street's entrances in register order. Street matching ignores case and accents.
    """
    q = _norm(street)
    q = q + "asse" if q.endswith("str") else q.replace("str ", "strasse ")  # "Grundstr." -> "grundstrasse"
    rows = [r for r in _addresses()[0] if _norm(r["street"]) == q
            and (not gemeinde or _gem(r["municipality"]) == _gem(gemeinde))]
    if number:
        exact = [r for r in rows if _norm(r["number"] or "") == _norm(number)]
        digits = re.match(r"\d+", number)
        same = [r for r in rows if digits and re.fullmatch(rf"{digits.group(0)}\D*", r["number"] or "")]  # 32 -> 32a
        rows = exact or same or rows
    return [{k: r[k] for k in ("address", "street", "number", "zip", "ortschaft", "municipality", "lat", "lon", "egid")}
            | {"building": r["name"]} for r in rows[:limit]]


def landmarks_near(lat: float, lon: float, radius_km: float = 15, kinds: list[str] | None = None,
                   name: str | None = None, limit: int = 15) -> list[dict]:
    """Named peaks, lakes, rivers, islands, passes and cable cars around a point (swissNAMES3D).

    [{name, kind, type, lat, lon, ele, municipality, distance_km}], big landmarks first within each
    5 km band (a Hauptgipfel 4 km away before a hill 3 km away). kinds: "Berg", "Hügel", "See",
    "Fluss/Bach", "Insel", "Pass", "Bergbahn", "Tal", ... name: substring match, accent-insensitive.
    """
    q = _norm(name) if name else None
    out = []
    for m in _landmarks():
        if kinds and m["kind"] not in kinds:
            continue
        if q and q not in _norm(m["name"]):
            continue
        d = _haversine_m(lat, lon, m["lat"], m["lon"]) / 1000
        if d <= radius_km:
            out.append(m | {"distance_km": round(d, 2)})
    out.sort(key=lambda m: (int(m["distance_km"] // 5), m["rank"], m["distance_km"]))
    return [{k: v for k, v in m.items() if k != "rank"} for m in out[:limit]]


def check() -> dict:
    """Known answers, printed and asserted (the brief's worked example and two obvious landmarks)."""
    b = find_building("Acherhof", "Schwyz")
    a = address_at(b[0]["lat"], b[0]["lon"], 60) if b else {}
    m = landmarks_near(47.02, 8.65, 10, kinds=["Berg"], name="Mythen")
    # a lake's point is its label point (the Vierwaldstättersee's is 8 km from Brunnen), so search wider
    lake = landmarks_near(46.995, 8.605, 10, kinds=["See"], limit=30)
    res = {"acherhof": b[:1], "acherhof_address": (a.get("addresses") or [{}])[0].get("address"),
           "ortschaft": a.get("ortschaft"), "municipality": a.get("municipality"),
           "mythen": [x["name"] for x in m], "lake_at_brunnen": [x["name"] for x in lake],
           "addresses": len(_addresses()[0]), "landmarks": len(_landmarks())}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    assert b and "Acherhof" in b[0]["name"] and (b[0]["address"] or "").startswith("Grundstrasse 32"), b[:1]
    assert a.get("municipality") == "Schwyz" and a.get("ortschaft") == "Schwyz", a
    assert any("Mythen" in x for x in res["mythen"]), res["mythen"]
    assert any("Vierwaldstättersee" in x or "Urnersee" in x for x in res["lake_at_brunnen"]), res["lake_at_brunnen"]
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "check"])
    a = ap.parse_args()
    if a.cmd == "build":
        print(build_addresses(), "entrances ->", ADDRESSES_FILE, flush=True)
        print(build_landmarks(), "landmarks ->", LANDMARKS_FILE, flush=True)
        _addresses.cache_clear()
        _landmarks.cache_clear()
    check()


if __name__ == "__main__":
    main()
