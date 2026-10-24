"""Challenge QC: the team's hand check of Prio-1 results as ground truth in data/splits/challenge_qc.jsonl.

    python -m data_pipeline.qc import handcheck.csv     # or .json / .jsonl, writes splits/challenge_qc.jsonl
    python -m data_pipeline.qc show

One line per checked photo: {id, locality, municipality, buildings, street, unverified?, note?, checked_by?}
(docs/CHALLENGE_BRIEF.md section 4). null means "the checker could not tell", never "wrong", so scoring skips it.
Ortschaft and Gemeinde are rewritten to the official spelling (swissBOUNDARIES3D Gemeinden, GWR PLZ localities)
when they match one; names that match none (e.g. outside the canton) are kept as typed and listed in
`unverified`, so a typo shows up before it silently costs a hit.

The importer takes the export as it comes: CSV (any delimiter) or JSON/JSONL, German or English column names,
ids as "SG.CIV.17.3", "SG.CIV.17.3.jpg" or "challenge:SG.CIV.17.3", buildings as a list or "a; b".
"""

import argparse
import csv
import io
import json
import re
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path

from .jsonl import read_jsonl, write_jsonl
from .paths import GAZETTEER, RAW, RECORDS, SPLITS

QC_FILE = SPLITS / "challenge_qc.jsonl"
FIELDS = ("locality", "municipality", "buildings", "street")
COLUMNS = {  # normalised header -> field
    "id": "id", "photo_id": "id", "photo": "id", "file": "id", "filename": "id", "file_name": "id", "datei": "id",
    "dateiname": "id", "bild": "id", "signatur": "id",
    "locality": "locality", "ortschaft": "locality", "ort": "locality",
    "municipality": "municipality", "gemeinde": "municipality", "politische_gemeinde": "municipality",
    "buildings": "buildings", "building": "buildings", "gebaude": "buildings", "gebaeude": "buildings",
    "street": "street", "strasse": "street",
    "note": "note", "notiz": "note", "kommentar": "note", "bemerkung": "note",
    "checked_by": "checked_by", "geprueft_von": "checked_by", "gepruft_von": "checked_by", "wer": "checked_by",
}
EMPTY = {"", "-", "?", "null", "none", "unbekannt", "nicht bestimmbar", "n/a"}


def _norm(s) -> str:
    from .places import _norm as n
    return n(str(s or ""))


def _header(h: str) -> str:
    return re.sub(r"[^a-z]+", "_", _norm(h)).strip("_")


def photo_id(raw) -> str | None:
    m = re.search(r"SG\.CIV\.17\.\d+", str(raw or ""))
    return f"challenge:{m.group(0)}" if m else None


@lru_cache(maxsize=1)
def official_names() -> dict[str, dict[str, str]]:
    """{"municipality": {norm: official}, "locality": {norm: official}} from the local gazetteer and GWR."""
    gem, ort = {}, {}
    f = GAZETTEER / "gemeinden.json"
    if f.exists():
        for g in json.loads(f.read_text(encoding="utf-8")):
            for n in [g["name"], *g.get("aliases", [])]:
                gem[_norm(n)] = g["name"]
    db = RAW / "gwr" / "data.sqlite"
    if db.exists():
        con = sqlite3.connect(db)
        for (n,) in con.execute("select distinct DPLZNAME from entrance where DPLZNAME is not null"):
            ort[_norm(n)] = n
        for (n,) in con.execute("select distinct GGDENAME from building where GGDENAME is not null"):
            gem.setdefault(_norm(n), n)
    for d in (gem, ort):  # "Seewen" finds "Seewen SZ", "Küssnacht" finds "Küssnacht (SZ)"
        for k, v in list(d.items()):
            d.setdefault(re.sub(r"\s+sz$", "", k), v)
    return {"municipality": gem, "locality": ort}


def _value(v):
    if v is None or (isinstance(v, str) and v.strip().lower() in EMPTY):
        return None
    return v.strip() if isinstance(v, str) else v


def clean_row(raw: dict, prio1: set[str] | None = None) -> tuple[dict | None, list[str]]:
    """One export row -> (QC line or None, problems)."""
    row = {}
    for k, v in raw.items():
        f = COLUMNS.get(_header(k))
        if f and f not in row:
            row[f] = v
    pid = photo_id(row.get("id"))
    if not pid:
        return None, [f"no SG.CIV.17 id in {raw!r}"]
    problems = []
    if prio1 is not None and pid not in prio1:
        problems.append(f"{pid}: not a Prio-1 challenge photo")
    out = {"id": pid}
    names = official_names()
    unverified = []
    for f in ("locality", "municipality"):
        v = _value(row.get(f))
        if v is not None:
            official = names[f].get(_norm(v)) or names[f].get(re.sub(r"\s+sz$", "", _norm(v)))
            if official:
                v = official
            else:
                unverified.append(f)
        out[f] = v
    b = row.get("buildings")
    if isinstance(b, str):
        b = [x.strip() for x in re.split(r"[;|\n]", b)]
    out["buildings"] = [x for x in (b or []) if _value(x)] or None
    out["street"] = _value(row.get("street"))
    for f in ("note", "checked_by"):
        if _value(row.get(f)):
            out[f] = row[f].strip()
    if unverified:
        out["unverified"] = unverified
        problems.append(f"{pid}: not an official name: " + ", ".join(f"{f}={out[f]!r}" for f in unverified))
    return out, problems


def read_export(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix == ".json":
        data = json.loads(text)
        return data if isinstance(data, list) else data.get("rows") or data.get("items") or list(data.values())
    if path.suffix == ".jsonl":
        return list(read_jsonl(path))
    head = text.split("\n", 1)[0]
    delim = max(",;\t", key=head.count)  # the header has no quoted cells, so its commonest separator is the one
    return list(csv.DictReader(io.StringIO(text), delimiter=delim))


def import_export(path: Path) -> tuple[int, list[str]]:
    prio1 = {r["id"] for r in read_jsonl(RECORDS / "challenge.jsonl") if str((r.get("raw") or {}).get("priority")) == "1"}
    rows, problems, seen = [], [], set()
    for raw in read_export(path):
        row, p = clean_row(raw, prio1 or None)
        problems += p
        if row and row["id"] in seen:
            problems.append(f"{row['id']}: twice in the export, kept the first")
        elif row:
            seen.add(row["id"])
            rows.append(row)
    rows.sort(key=lambda r: int(r["id"].rsplit(".", 1)[1]))
    return write_jsonl(QC_FILE, rows), problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["import", "show"])
    ap.add_argument("file", nargs="?", type=Path)
    a = ap.parse_args()
    if a.cmd == "import":
        if not a.file:
            sys.exit("usage: python -m data_pipeline.qc import <export.csv|json|jsonl>")
        n, problems = import_export(a.file)
        print(n, "checked photos ->", QC_FILE)
        for p in problems:
            print("  !", p)
    else:
        for r in read_jsonl(QC_FILE):
            print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
