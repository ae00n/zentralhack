"""Export rows in the archive's field structure (CONTRACTS section 6, v3): CSV and the Excel deliverable.

One row per photo, keyed by file name. Reviewed values win over the agent's values. A field that could
not be determined stays empty and is named in Nicht_bestimmbar.
"""

import csv
import io

from .lv95 import wgs84_to_lv95

COLUMNS = [
    "Dateiname", "Signatur", "Prioritaet", "Ortschaft", "Gemeinde", "Gebaeude", "See_Fluss_Berg", "Strasse",
    "Aufnahmedatum", "Breite_WGS84", "Laenge_WGS84", "E_LV95", "N_LV95",
    "Konfidenz_Ortschaft", "Konfidenz_Gemeinde", "Konfidenz_Gebaeude", "Konfidenz_See_Fluss_Berg",
    "Konfidenz_Strasse", "Konfidenz_Gesamt", "Konfidenz_Begruendung", "Nicht_bestimmbar", "Pruefung_noetig",
    "Review_Status", "Quellen", "KI_Modell", "Analysedatum",
]
# v3 field -> (value column, confidence column, label in Nicht_bestimmbar)
FIELDS = {
    "locality": ("Ortschaft", "Konfidenz_Ortschaft", "Ortschaft"),
    "municipality": ("Gemeinde", "Konfidenz_Gemeinde", "Gemeinde"),
    "buildings": ("Gebaeude", "Konfidenz_Gebaeude", "Gebäude"),
    "landscape_features": ("See_Fluss_Berg", "Konfidenz_See_Fluss_Berg", "See/Fluss/Berg"),
    "street": ("Strasse", "Konfidenz_Strasse", "Strasse"),
}
CONFIDENCE_COLUMNS = [c for _, c, _ in FIELDS.values()] + ["Konfidenz_Gesamt"]
REVIEWED = ("bestaetigt", "korrigiert")


def _field(result: dict, name: str) -> dict:
    return (result.get("fields") or {}).get(name) or {}


def _joined(value) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)


def value(result: dict, name: str):
    """The field value as exported: a reviewer's correction wins over the agent's value."""
    review = result.get("review") or {}
    if review.get("status") in REVIEWED and name in (review.get("fields") or {}):
        return review["fields"][name]
    return _field(result, name).get("value")


def _sources(result: dict, ref_url, n: int = 3) -> str:
    """Top n supporting sources in field priority order, each with its link when there is one."""
    out, seen = [], set()
    for name in [*FIELDS, "coordinates"]:
        for ev in _field(result, name).get("evidence") or []:
            s = (ev.get("summary") or "").strip()
            if not s or ev.get("supports") is False or s in seen:
                continue
            seen.add(s)
            link = ev.get("url") or (ref_url(ev["ref_id"]) if ev.get("ref_id") else None)
            out.append(f"{s} ({link})" if link else s)
            if len(out) == n:
                return " | ".join(out)
    return " | ".join(out)


def row(result: dict, record: dict | None, ref_url=lambda ref_id: None) -> dict:
    """ref_url(ref_id) -> link of a referenced PhotoRecord (its source_url), or None."""
    record = record or {}
    raw = record.get("raw") or {}
    coords = _field(result, "coordinates").get("value") or {}
    lat, lon = coords.get("lat"), coords.get("lon")
    e = n = None
    if lat is not None and lon is not None:
        e, n = (round(v) for v in wgs84_to_lv95(lat, lon))
    review = result.get("review") or {}
    reviewed = review.get("status") in REVIEWED
    out = {
        "Dateiname": _file_name(record, result["photo_id"]),
        "Signatur": record.get("signature"),
        "Prioritaet": raw.get("priority"),
        "Aufnahmedatum": (record.get("date") or {}).get("raw"),
        "Breite_WGS84": lat,
        "Laenge_WGS84": lon,
        "E_LV95": e,
        "N_LV95": n,
        "Konfidenz_Gesamt": result.get("overall_confidence"),
        "Konfidenz_Begruendung": result.get("confidence_explanation"),
        "Pruefung_noetig": "nein" if reviewed or not _needs_review(result) else "ja",
        "Review_Status": review.get("status") or "offen",
        "Quellen": _sources(result, ref_url) or None,
        "KI_Modell": result.get("model"),
        "Analysedatum": result.get("created_at"),
    }
    unknown = []
    for name, (col, conf_col, label) in FIELDS.items():
        v = _joined(value(result, name))
        conf = _field(result, name).get("confidence", 0.0)
        out[col] = v
        out[conf_col] = conf
        # unknown = empty and unbacked (null + 0); an empty list with confidence means "none visible"
        if v is None and not conf and not (reviewed and name in (review.get("fields") or {})):
            unknown.append(label)
    out["Nicht_bestimmbar"] = ", ".join(unknown) or None
    return out


def _file_name(record: dict, photo_id: str) -> str:
    """The Excel key: the handed-out file name for challenge photos, else <source_id>.jpg."""
    raw = record.get("raw") or {}
    if record.get("source") == "challenge" and raw.get("file_name"):
        return raw["file_name"]
    return f"{record['source_id']}.jpg" if record.get("source_id") else photo_id


def _needs_review(result: dict) -> bool:
    """v3 rule, also applied to results written before v3: below 0.9, or Ortschaft / Gemeinde unknown,
    or independent runs of the consistency check named different places (agent.consistency)."""
    core_unknown = any(_field(result, n).get("value") in (None, "") for n in ("locality", "municipality"))
    unstable = (result.get("consistency") or {}).get("agree") is False
    return bool(result.get("needs_review")) or (result.get("overall_confidence") or 0) < 0.9 or core_unknown \
        or unstable


def _cell(col: str, v) -> str:
    if v is None:
        return ""
    if col in CONFIDENCE_COLUMNS and isinstance(v, (int, float)):
        return f"{v:.2f}"
    return v


def to_csv(rows: list[dict]) -> bytes:
    """UTF-8 with BOM, `;` separator, CRLF line ends (opens directly in Swiss Excel)."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, delimiter=";")
    w.writeheader()
    for r in rows:
        w.writerow({k: _cell(k, r.get(k)) for k in COLUMNS})
    return ("﻿" + buf.getvalue()).encode("utf-8")


PATHS = {"pick": "Claude erkennt denselben Ort auf einem geometrisch bestätigten Referenzfoto",
         "building": "Gebäudename gelesen oder erkannt und im Gebäuderegister gefunden",
         "street": "Strasse gelesen oder erkannt und im Adressregister gefunden",
         "match": "Stark geometrisch bestätigtes Referenzfoto, von Claude nicht widersprochen",
         "claude": "Nur Claudes Bildeinschätzung (sicher / wahrscheinlich / vermutet)"}


def method() -> list[tuple[str, str]]:
    """Sheet Methode: how a value and its confidence come about (agent.v6), with the measured table."""
    from .. import v6

    rows = [
        ("Ablauf", "1. Claude (Opus 5.5) sieht das Foto, das EXIF-Datum, Fotos derselben Aufnahmeserie und bis zu "
                   "4 geometrisch bestätigte Referenzfotos (MegaLoc-Suche, LightGlue-Prüfung) und nennt, was es liest "
                   "und erkennt. 2. Unser Code sucht Gebäude, Strasse oder Referenzpunkt in den amtlichen Registern. "
                   "3. Ortschaft, Gemeinde, Strasse und Gebäude kommen aus dem Register am gefundenen Punkt (GWR, "
                   "swissBOUNDARIES3D), Berge und Seen aus swissNAMES3D. Claude tippt nie Koordinaten."),
        ("Nicht bestimmbar", "Ohne Hinweis bleibt das Feld leer mit Konfidenz 0. Ein Name, der in keinem Register "
                             "steht, wird nicht übernommen; leere Felder stehen in der Spalte Nicht_bestimmbar."),
        ("Konfidenz", "Gemessene Trefferquote des Wegs, auf dem der Wert entstand, auf den von Hand geprüften "
                      "Prio-1-Fotos: (Treffer + 1) / (geprüfte + 2). Ein Weg mit weniger als 3 geprüften Fotos "
                      "trägt einen Schätzwert, das steht dann in Konfidenz_Begruendung."),
        ("Prüfung nötig", "ja, wenn die Gesamtkonfidenz unter 0.90 liegt oder die Gemeinde fehlt. Nach einem "
                          "Review (bestätigt oder korrigiert) nein; korrigierte Werte ersetzen die Vorschläge."),
    ]
    rows += [(f"Weg: {k}", v) for k, v in PATHS.items()]
    table = v6._table()
    for b, cells in sorted(table.items()):
        c = cells.get("municipality") or {}
        if c:
            rows.append((f"Gemessen {b}", f"Gemeinde {c['hits']} von {c['n']} richtig, Konfidenz {c['rate']:.2f}"))
    if not table:
        rows.append(("Gemessen", "Noch keine Handprüfung: alle Konfidenzen sind Schätzwerte."))
    return rows

def to_xlsx(rows: list[dict], image_url=lambda row: None) -> bytes:
    """The Excel deliverable: sheet Metadaten (one row per photo, file name linked to the image) and
    sheet Methode (how the confidence is computed). image_url(row) -> link for the Dateiname cell."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Metadaten"
    ws.append(COLUMNS)
    head = Font(bold=True)
    fill = PatternFill("solid", fgColor="DDE6EA")
    for c in ws[1]:
        c.font, c.fill = head, fill
    review_fill = PatternFill("solid", fgColor="FBE3C8")
    for r in rows:
        ws.append([r.get(k) for k in COLUMNS])
        i = ws.max_row
        link = image_url(r)
        if link:
            cell = ws.cell(row=i, column=1)
            cell.hyperlink = link
            cell.font = Font(color="1F5F7A", underline="single")
        for col in CONFIDENCE_COLUMNS:
            ws.cell(row=i, column=COLUMNS.index(col) + 1).number_format = "0.00"
        if r.get("Pruefung_noetig") == "ja":
            ws.cell(row=i, column=COLUMNS.index("Pruefung_noetig") + 1).fill = review_fill
    widths = {"Dateiname": 20, "Konfidenz_Begruendung": 60, "Quellen": 80, "Gebaeude": 32, "See_Fluss_Berg": 28,
              "Strasse": 22, "Nicht_bestimmbar": 24, "Analysedatum": 21}
    for j, col in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(j)].width = widths.get(col, max(11, min(len(col) + 2, 26)))
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{max(ws.max_row, 1)}"

    m = wb.create_sheet("Methode")
    m.append(["Thema", "Regel"])
    for c in m[1]:
        c.font, c.fill = head, fill
    for k, v in method():
        m.append([k, v])
    m.column_dimensions["A"].width = 24
    m.column_dimensions["B"].width = 110
    for row_cells in m.iter_rows(min_row=2):
        row_cells[1].alignment = Alignment(wrap_text=True, vertical="top")
        row_cells[0].alignment = Alignment(vertical="top")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
