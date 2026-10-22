"""Export rows in the archive field structure (CONTRACTS section 6)."""

import csv
import io

from .lv95 import wgs84_to_lv95

COLUMNS = [
    "Signatur", "Titel", "Entstehungszeitraum", "Entstehungszeitraum_KI", "Jahrzehnt_KI", "Thema",
    "Gemeinde_KI", "Ort_KI", "Gebaeude_KI", "Landschaft_KI", "Breite_WGS84", "Laenge_WGS84",
    "E_LV95", "N_LV95", "Konfidenz_Gemeinde", "Konfidenz_Jahrzehnt", "Konfidenz_Koordinaten",
    "Konfidenz_Gesamt", "Pruefung_noetig", "Evidenz", "KI_Modell", "Analysedatum", "URL",
]
FIELD_ORDER = ["municipality", "place", "buildings", "landscape_features", "decade", "year_range", "coordinates"]


def _field(result: dict, name: str) -> dict:
    return (result.get("fields") or {}).get(name) or {}


def _joined(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)


def _evidence(result: dict, n: int = 3) -> str:
    """Top n evidence summaries: supporting evidence first, in field order, without duplicates."""
    items = [ev for f in FIELD_ORDER for ev in _field(result, f).get("evidence") or []]
    items.sort(key=lambda ev: ev.get("supports") is False)  # stable
    out = []
    for ev in items:
        s = (ev.get("summary") or "").strip()
        if s and s not in out:
            out.append(s)
        if len(out) == n:
            break
    return " | ".join(out)


def row(result: dict, record: dict | None) -> dict:
    record = record or {}
    yr = _field(result, "year_range").get("value") or {}
    coords = _field(result, "coordinates").get("value") or {}
    lat, lon = coords.get("lat"), coords.get("lon")
    e = n = None
    if lat is not None and lon is not None:
        e, n = (round(v) for v in wgs84_to_lv95(lat, lon))
    years = None
    if yr.get("from") is not None or yr.get("to") is not None:
        years = f"{yr.get('from') if yr.get('from') is not None else ''}-{yr.get('to') if yr.get('to') is not None else ''}"
    return {
        "Signatur": record.get("signature"),
        "Titel": record.get("title"),
        "Entstehungszeitraum": (record.get("date") or {}).get("raw"),
        "Entstehungszeitraum_KI": years,
        "Jahrzehnt_KI": _field(result, "decade").get("value"),
        "Thema": _joined(record.get("places")) if record.get("places") else None,
        "Gemeinde_KI": _field(result, "municipality").get("value"),
        "Ort_KI": _field(result, "place").get("value"),
        "Gebaeude_KI": _joined(_field(result, "buildings").get("value")),
        "Landschaft_KI": _joined(_field(result, "landscape_features").get("value")),
        "Breite_WGS84": lat,
        "Laenge_WGS84": lon,
        "E_LV95": e,
        "N_LV95": n,
        "Konfidenz_Gemeinde": _field(result, "municipality").get("confidence"),
        "Konfidenz_Jahrzehnt": _field(result, "decade").get("confidence"),
        "Konfidenz_Koordinaten": _field(result, "coordinates").get("confidence"),
        "Konfidenz_Gesamt": result.get("overall_confidence"),
        "Pruefung_noetig": "ja" if result.get("needs_review") else "nein",
        "Evidenz": _evidence(result),
        "KI_Modell": result.get("model"),
        "Analysedatum": result.get("created_at"),
        "URL": record.get("source_url"),
    }


def to_csv(rows: list[dict]) -> bytes:
    """UTF-8 with BOM, `;` separator, CRLF line ends (opens directly in Swiss Excel)."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, delimiter=";")
    w.writeheader()
    for r in rows:
        w.writerow({k: "" if r.get(k) is None else r[k] for k in COLUMNS})
    return ("﻿" + buf.getvalue()).encode("utf-8")
