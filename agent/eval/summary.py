"""AnalysisResults -> metrics.score predictions -> EvalSummary (CONTRACTS section 7).

Prediction choices (documented here because they move the year numbers):
- municipality: fields.municipality.value, mapped to the gazetteer name when it matches a name or
  alias case-insensitively (with or without "(SZ)"); confidence = fields.municipality.confidence.
- year: an explicit integer fields.year.value if the loop ever adds one; else the midpoint of
  fields.year_range (rounded down); else decade + 5. year_low / year_high come from year_range,
  else from the decade (decade .. decade + 9).
- decade: fields.decade.value; else derived from year.
- place_name_printed: an explicit top-level or fields.place_name_printed boolean if present; else
  True when a supporting "text_on_card" evidence backs the municipality.

Decade metrics: the true decades are year_from // 10 .. year_to // 10 (a prediction inside that span
is correct). card_posted items are left out of decade_accuracy / decade_within_one, the same way
metrics.score leaves them out of the exact-year metrics, because their year is only an upper bound;
they get decade_posted_at_or_before instead (predicted decade <= decade of the bound).
"""

import json
import re
import statistics as st
from bisect import bisect_right
from collections.abc import Callable
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from .. import config, schemas
from . import baseline as bl

CAL_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
COORD_MAX_PRECISION_M = 1000  # ground truth coordinates coarser than this (municipality centroids) are skipped

# "Best so far" column of the benchmark table in docs/SCOPE_2_AGENT.md (Opus, single calls, 2026-10-21)
BEST_SO_FAR = {
    "muni_all": 0.83, "muni_printed": 0.95, "muni_not_printed": 0.68, "muni_card_exact": 0.87,
    "muni_photo_dated": 0.72, "conf_0.8_coverage": 0.69, "conf_0.8_accuracy": 0.975,
    "conf_0.9_coverage": 0.55, "conf_0.9_accuracy": 0.995, "year_median_error": 2,
    "year_within_5": 0.72, "year_within_10": 0.86, "range_coverage": 0.90, "range_median_width": 22,
    "posted_at_or_before": 0.86,
}


# ---------- predictions ----------

def _key(name: str) -> str:
    return re.sub(r"\s*\(sz\)\s*$", "", (name or "").strip().casefold())


def municipality_names() -> dict[str, str]:
    """casefolded name or alias -> canonical gazetteer name."""
    try:
        import data_pipeline as dp

        gaz = dp.gazetteer()
    except Exception:  # noqa: BLE001  no gazetteer: names are compared verbatim
        return {}
    out = {}
    for g in gaz:
        for n in [g["name"], *(g.get("aliases") or [])]:
            out.setdefault(_key(n), g["name"])
    return out


def canonical(name: str | None, names: dict[str, str]) -> str | None:
    if not name:
        return None
    return names.get(_key(name), name.strip())


def _field(result: dict, name: str) -> dict:
    return (result.get("fields") or {}).get(name) or {}


def _printed(result: dict) -> bool:
    for flag in (result.get("place_name_printed"), _field(result, "place_name_printed").get("value")):
        if isinstance(flag, bool):
            return flag
    return any(e.get("kind") == "text_on_card" and e.get("supports", True) is not False
               for e in _field(result, "municipality").get("evidence") or [])


def year_fields(result: dict) -> tuple[int | None, int | None, int | None, int | None]:
    """(year, year_low, year_high, decade) from an AnalysisResult."""
    yr = _field(result, "year_range").get("value") or {}
    lo, hi = yr.get("from"), yr.get("to")
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    dec = _field(result, "decade").get("value")
    dec = dec if isinstance(dec, int) else None
    year = _field(result, "year").get("value")
    if not isinstance(year, int):
        if lo is not None and hi is not None:
            year = (lo + hi) // 2
        elif lo is not None or hi is not None:
            year = lo if lo is not None else hi
        elif dec is not None:
            year = dec + 5
        else:
            year = None
    if lo is None and hi is None and dec is not None:
        lo, hi = dec, dec + 9
    if dec is None and year is not None:
        dec = year // 10 * 10
    return year, lo, hi, dec


def to_prediction(result: dict, names: dict[str, str] | None = None) -> dict:
    """AnalysisResult -> {id, municipality, municipality_confidence, year, year_low, year_high,
    place_name_printed} (the metrics.score shape; decade is an extra key)."""
    names = names if names is not None else {}
    m = _field(result, "municipality")
    year, lo, hi, dec = year_fields(result)
    return {"id": result["photo_id"], "municipality": canonical(m.get("value"), names),
            "municipality_confidence": float(m.get("confidence") or 0.0),
            "year": year, "year_low": lo, "year_high": hi, "decade": dec,
            "place_name_printed": _printed(result)}


# ---------- metric helpers ----------

def _share(xs: list[bool]) -> float:
    return round(sum(xs) / len(xs), 3) if xs else 0.0


def decade_distance(pred_decade: int, item: dict) -> int | None:
    """Decades between the prediction and the true decade span; None for upper-bound items."""
    if item.get("year_is_upper_bound") or item.get("year_from") is None:
        return None
    lo = item["year_from"] // 10 * 10
    hi = (item.get("year_to") or item["year_from"]) // 10 * 10
    if lo <= pred_decade <= hi:
        return 0
    return (lo - pred_decade if pred_decade < lo else pred_decade - hi) // 10


def calibration(rows: list[tuple[float, bool]]) -> list[dict]:
    """Confidence bins 0.0-0.2 .. 0.8-1.0 (1.0 falls in the last bin). n adds up to len(rows)."""
    bins = [[] for _ in range(len(CAL_EDGES) - 1)]
    for conf, ok in rows:
        i = min(max(bisect_right(CAL_EDGES, conf or 0.0) - 1, 0), len(bins) - 1)
        bins[i].append((conf or 0.0, ok))
    out = []
    for i, b in enumerate(bins):
        out.append({"bin": f"{CAL_EDGES[i]:.1f}-{CAL_EDGES[i + 1]:.1f}", "n": len(b),
                    "accuracy": _share([ok for _, ok in b]) if b else None,
                    "mean_confidence": round(st.mean(c for c, _ in b), 3) if b else None})
    return out


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


def _record_of(photo_id: str) -> dict | None:
    try:
        import data_pipeline as dp

        return dp.get_record(photo_id)
    except Exception:  # noqa: BLE001  no records on this machine
        return None


def why(result: dict, expected: str, names: dict[str, str]) -> str:
    """German one-liner for a wrong municipality: a rejected true answer, then the top evidence."""
    parts = []
    for h in result.get("rejected_hypotheses") or []:
        if h.get("field") == "municipality" and canonical(h.get("value"), names) == expected:
            parts.append(f"Richtige Gemeinde {expected} verworfen: {h.get('reason') or 'ohne Begründung'}")
            break
    ev = [e for e in _field(result, "municipality").get("evidence") or [] if e.get("supports", True) is not False]
    if ev:
        parts.append(f"Stärkste Evidenz: {ev[0].get('summary', '')}")
    return "; ".join(parts) or "Keine Evidenz angegeben"


# ---------- summary ----------

def build(items: list[dict], results_by_id: dict[str, dict | None], *, model: str,
          baseline_preds: dict[str, dict] | None = None,
          record_of: Callable[[str], dict | None] = _record_of,
          names: dict[str, str] | None = None) -> dict | None:
    """EvalSummary over the eval items that have a result, or None when none has one."""
    from data_pipeline.metrics import score

    names = municipality_names() if names is None else names
    scored = [(it, results_by_id[it["id"]]) for it in items if results_by_id.get(it["id"])]
    if not scored:
        return None
    preds = {it["id"]: to_prediction(r, names) for it, r in scored}

    hits = [(it, preds[it["id"]], r, preds[it["id"]]["municipality"] == it["municipality"]) for it, r in scored]

    dist = [decade_distance(p["decade"], it) if p["decade"] is not None else None
            for it, p, _, _ in hits]
    decade_rows = [(d, it) for d, (it, _, _, _) in zip(dist, hits) if not it.get("year_is_upper_bound")]
    posted = [(it, p) for it, p, _, _ in hits if it.get("year_is_upper_bound") and it.get("year_from") is not None]

    coord_err = []
    for it, _, r, _ in hits:
        c = _field(r, "coordinates").get("value") or {}
        loc = (record_of(it["id"]) or {}).get("location") or {}
        if c.get("lat") is None or loc.get("lat") is None:
            continue
        if (loc.get("precision_m") or 0) > COORD_MAX_PRECISION_M:
            continue
        coord_err.append(_km(c["lat"], c["lon"], loc["lat"], loc["lon"]))

    by_m: dict[str, list[bool]] = {}
    for it, _, _, ok in hits:
        by_m.setdefault(it["municipality"], []).append(ok)

    failures = []
    for it, p, r, ok in hits:
        if ok:
            continue
        failures.append({"photo_id": it["id"], "expected": it["municipality"],
                         "got": p["municipality"] or "keine Angabe", "why": why(r, it["municipality"], names),
                         "confidence": p["municipality_confidence"], "subset": it.get("subset"),
                         "place_name_printed": p["place_name_printed"]})
    failures.sort(key=lambda f: -f["confidence"])

    pred_list = [{k: v for k, v in p.items() if k != "decade"} for p in preds.values()]
    summary = {
        "n": len(hits),
        "model": model,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "municipality_accuracy": _share([ok for *_, ok in hits]),
        "decade_accuracy": _share([d == 0 for d, _ in decade_rows]),
        "decade_within_one": _share([d is not None and d <= 1 for d, _ in decade_rows]),
        "decade_n": len(decade_rows),
        "decade_posted_at_or_before": _share([p["decade"] is not None and p["decade"] <= it["year_from"] // 10 * 10
                                              for it, p in posted]) if posted else None,
        "median_coord_error_km": round(st.median(coord_err), 2) if coord_err else None,
        "coord_n": len(coord_err),
        "calibration": calibration([(p["municipality_confidence"], ok) for _, p, _, ok in hits]),
        "by_municipality": sorted(({"municipality": m, "n": len(v), "accuracy": _share(v)} for m, v in by_m.items()),
                                  key=lambda x: (-x["n"], x["municipality"])),
        "baseline": {},
        "failures": failures,
        "cost_usd": round(sum(((r.get("usage") or {}).get("cost_usd") or 0.0) for _, r in scored), 4),
        "n_eval": len(items),
        "n_missing": len(items) - len(hits),
        "metrics": score(pred_list, truth=items),
    }
    if baseline_preds:
        same = [it for it, *_ in hits]
        acc, n = bl.accuracy(baseline_preds, same)
        if acc is not None:
            base_list = [{k: v for k, v in baseline_preds[it["id"]].items() if k not in ("votes", "neighbours", "settings")}
                         for it in same if it["id"] in baseline_preds]
            summary["baseline"] = {"similarity_only_municipality_accuracy": acc, "n": n,
                                   "settings": next(iter(baseline_preds.values())).get("settings"),
                                   "metrics": score(base_list, truth=same)}
    return summary


def summary_path(model: str) -> Path:
    """The official model writes eval_summary.json (what /eval/summary serves); others a side file."""
    name = "eval_summary.json" if model == config.MODEL else f"eval_summary.{model}.json"
    return config.RESULTS_DIR / name


def write(summary: dict, predictions: list[dict] | None = None) -> Path:
    schemas.validate(summary, "eval_summary")
    p = summary_path(summary["model"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    if predictions is not None:  # rescore later with: python -m data_pipeline.metrics <file>
        pp = config.RESULTS_DIR / f"eval_predictions.{summary['model']}.jsonl"
        pp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in predictions), encoding="utf-8")
    return p


# ---------- report ----------

def _pct(x) -> str:
    return "-" if x is None else f"{x * 100:.1f}%"


def _num(x) -> str:
    return "-" if x is None else f"{x:g}"


def benchmark_rows(m: dict) -> list[tuple[str, str, str]]:
    """(label, value, best so far) rows from a metrics.score dict."""
    def g(*path):
        cur = m
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        return cur

    mu, yr = ("all", "municipality"), ("all", "year")
    rows = [
        ("Gemeinde, alle", _pct(g(*mu, "accuracy")), "muni_all", _pct),
        ("Ortsname gedruckt", _pct(g(*mu, "accuracy_printed")), "muni_printed", _pct),
        ("Kein Ortsname gedruckt", _pct(g(*mu, "accuracy_not_printed")), "muni_not_printed", _pct),
        ("card_exact", _pct(g("card_exact", "municipality", "accuracy")), "muni_card_exact", _pct),
        ("photo_dated", _pct(g("photo_dated", "municipality", "accuracy")), "muni_photo_dated", _pct),
        ("Konfidenz >= 0.8: Anteil", _pct(g(*mu, "conf_0.8", "coverage")), "conf_0.8_coverage", _pct),
        ("Konfidenz >= 0.8: korrekt", _pct(g(*mu, "conf_0.8", "accuracy")), "conf_0.8_accuracy", _pct),
        ("Konfidenz >= 0.9: Anteil", _pct(g(*mu, "conf_0.9", "coverage")), "conf_0.9_coverage", _pct),
        ("Konfidenz >= 0.9: korrekt", _pct(g(*mu, "conf_0.9", "accuracy")), "conf_0.9_accuracy", _pct),
        ("Jahr, Median-Fehler", _num(g(*yr, "median_error")), "year_median_error", _num),
        ("Jahr innerhalb +-5", _pct(g(*yr, "within_5")), "year_within_5", _pct),
        ("Jahr innerhalb +-10", _pct(g(*yr, "within_10")), "year_within_10", _pct),
        ("Spanne enthält Jahr", _pct(g(*yr, "range_coverage")), "range_coverage", _pct),
        ("Spanne, Median-Breite", _num(g(*yr, "range_median_width")), "range_median_width", _num),
        ("Gelaufen: <= Poststempel", _pct(g("card_posted", "year", "at_or_before_bound")), "posted_at_or_before", _pct),
    ]
    return [(label, val, fmt(BEST_SO_FAR[key])) for label, val, key, fmt in rows]


def report(summary: dict, log: Callable[[str], None] = print, top_failures: int = 5) -> None:
    m = summary.get("metrics") or {}
    base = summary.get("baseline") or {}
    base_rows = {r[0]: r[1] for r in benchmark_rows(base["metrics"])} if base.get("metrics") else {}
    log("")
    log(f"Eval {summary['model']}: {summary['n']} von {summary.get('n_eval', summary['n'])} Items bewertet, "
        f"Kosten ${summary['cost_usd']:.2f}")
    log(f"{'Metrik':<28}{'Agent':>10}{'Best so far':>13}{'Baseline':>10}")
    for label, val, best in benchmark_rows(m):
        log(f"{label:<28}{val:>10}{best:>13}{base_rows.get(label, '-'):>10}")
    log(f"Jahrzehnt korrekt / +-1: {_pct(summary['decade_accuracy'])} / {_pct(summary['decade_within_one'])} "
        f"(n={summary.get('decade_n')}, ohne card_posted)")
    if summary.get("median_coord_error_km") is not None:
        log(f"Koordinaten, Median-Fehler: {summary['median_coord_error_km']} km (n={summary.get('coord_n')})")
    if base:
        diff = summary["municipality_accuracy"] - base["similarity_only_municipality_accuracy"]
        log(f"Baseline nur Ähnlichkeit: {_pct(base['similarity_only_municipality_accuracy'])} "
            f"(n={base.get('n')}); Agent {diff * 100:+.1f} Punkte")
    log("Kalibrierung: " + ", ".join(f"{c['bin']}: n={c['n']} {_pct(c['accuracy'])}" for c in summary["calibration"]))
    wrong = summary["failures"][:top_failures]
    if wrong:
        log(f"Die {len(wrong)} sichersten Fehler (Kandidaten für den ehrlichen Fehlerfall im Pitch):")
        for f in wrong:
            log(f"  {f['photo_id']} ({f.get('subset')}): erwartet {f['expected']}, bekommen {f['got']} "
                f"(Konfidenz {f.get('confidence', 0):.2f}). {f['why']}")
