"""Date hints for one photo: hard and soft year clues the agent combines with what it sees.

    from data_pipeline.dating import date_hints, rule_checklist
    date_hints("stasz:514200", exclude_ids=["stasz:514200"])
    python -m data_pipeline.dating train-probe     # fit the CLIP year probe (eval cards left out)
    python -m data_pipeline.dating check           # leave-one-out accuracy of each hint on eval cards

Hint kinds (each {kind, year, year_low, year_high, weight, evidence, source?}):
- near_duplicate  the same picture elsewhere with a known date (CLIP cosine >= 0.92)
- card_number     neighbouring publisher numbers in the same series (archive cards)
- nb_negative     the Swiss National Library's dated Wehrli negative with the card's number and place
- publisher_rule  imprint eras from dating_rules.json (e.g. "Gebr. Wehrli" 1895 to 1924)
- year_probe      logistic regression on CLIP vectors of dated photos ("Blind Dates", 2023)
A posted card's catalogue year is often the postmark, so it only bounds the photo from above.
Eval cards are never used as a source of a hint (same rule as archive_lookup).
"""

import argparse
import json
import pickle
import re
import statistics as st
from functools import lru_cache
from pathlib import Path

import numpy as np

from .api import _base, eval_ids, get_record, image_file
from .jsonl import read_jsonl
from .paths import DATA_DIR, INDEX, RAW, RECORDS, SPLITS

RULES_FILE = Path(__file__).with_name("dating_rules.json")
NB_NEGATIVES = RAW / "helveticarchives" / "wehrli_negatives.jsonl"
PROBE_FILE = INDEX / "year_probe.pkl"
DUP_MIN_SCORE = 0.92
NUMBER_MAX_GAP = 200
PROBE_BINS = list(range(1880, 2000, 5))  # 5-year classes, label = bin start
WEHRLI_FAMILIES = ("wehrli", "photoglob-wehrli")


# ---------- record helpers ----------

def exact_year(r: dict) -> int | None:
    d = r.get("date") or {}
    y = d.get("year_from")
    return y if y and y == d.get("year_to") else None


def posted(r: dict) -> bool:
    z = ((r.get("raw") or {}).get("Zusatzinfos") or "").lower()
    return "gelaufen" in z and "ungelaufen" not in z


def publisher(r: dict) -> str:
    return ((r.get("raw") or {}).get("Autor/Fotograf/Künstler") or "").strip()


def family(pub: str) -> str | None:
    """Publisher family: the many spellings of one firm collapse to one key."""
    p = (pub or "").split(";")[0].lower()
    if not p.strip() or "unbekannt" in p:
        return None
    if "photoglob" in p and ("wehrli" in p or "vouga" in p):
        return "photoglob-wehrli"
    for k in ("photoglob", "wehrli", "goetz", "globetrotter", "beeler", "kopp", "benziger", "gaberell",
              "suter", "engelberger", "gross"):
        if k in p:
            return k
    return re.split(r"[-,(]", p)[0].strip(" .") or None


def card_number(raw: str | None) -> tuple[str, int] | None:
    """'k 4139' -> ('k', 4139); '1430 Fl.' -> ('fl', 1430); '11547' -> ('', 11547). Letters mark a series."""
    s = (raw or "").strip()
    m = re.fullmatch(r"([A-Za-z]{1,3})\.?\s*(\d+)", s)
    if m:
        return m.group(1), int(m.group(2))
    m = re.fullmatch(r"(\d+)\s*([A-Za-z]{1,3})\.?", s)
    if m:
        return m.group(2).lower(), int(m.group(1))
    m = re.fullmatch(r"\d+", s)
    return ("", int(s)) if m else None


def _hint(kind, year, low, high, weight, evidence, source=None) -> dict:
    h = {"kind": kind, "year": year, "year_low": low, "year_high": high, "weight": round(weight, 3),
         "evidence": evidence}
    if source:
        h["source"] = source
    return h


# ---------- sources ----------

@lru_cache(maxsize=1)
def rules() -> list[dict]:
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))["rules"]


def rule_checklist() -> list[dict]:
    """Visual rules for the agent prompt: [{id, feature, year_min, year_max, confidence, source}]."""
    keys = ("id", "category", "feature", "year_min", "year_max", "confidence", "source")
    return [{k: r.get(k) for k in keys} for r in rules() if r["applies"] == "visual"]


@lru_cache(maxsize=1)
def _dated_pool() -> list[dict]:
    """Records usable as hint sources: exact year, not an eval card."""
    ev = eval_ids()
    return [r for r in read_jsonl(RECORDS / "all.jsonl") if exact_year(r) and r["id"] not in ev]


@lru_cache(maxsize=1)
def _series_index() -> dict[tuple, list[tuple[int, int, bool, str]]]:
    """(family, series) -> [(number, year, is_upper_bound, id)]."""
    idx: dict[tuple, list] = {}
    for r in _dated_pool():
        f, c = family(publisher(r)), card_number((r.get("raw") or {}).get("Karten Nr."))
        if f and c:
            idx.setdefault((f, c[0]), []).append((c[1], exact_year(r), posted(r), r["id"]))
    return idx


@lru_cache(maxsize=1)
def _nb_negatives() -> dict[int, list[dict]]:
    """Swiss National Library Wehrli negatives by number (scrapers/helveticarchives.py)."""
    out: dict[int, list[dict]] = {}
    if NB_NEGATIVES.exists():
        for n in read_jsonl(NB_NEGATIVES):
            if n.get("number") and n.get("year_from"):
                out.setdefault(n["number"], []).append(n)
    return out


@lru_cache(maxsize=1)
def _clip():
    ids = json.loads((INDEX / "clip.ids.json").read_text())
    return np.load(INDEX / "clip.npy").astype(np.float32), ids, {i: n for n, i in enumerate(ids)}


def _vector(photo_id: str | None, image_path: str | None) -> np.ndarray | None:
    X, _, row = _clip()
    if photo_id and photo_id in row:
        return X[row[photo_id]]
    p = image_path or (image_file(get_record(photo_id)) if photo_id and get_record(photo_id) else None)
    if not p:
        return None
    from .embed import _encoder, _load_image

    p = Path(p)
    return _encoder("clip").encode([_load_image(p if p.exists() else DATA_DIR / p)])[0]


# ---------- the four hint kinds ----------

def near_duplicate_hints(vec: np.ndarray, excluded: set[str], k: int = 3) -> list[dict]:
    X, ids, _ = _clip()
    scores = X @ vec
    pool = {r["id"]: r for r in _dated_pool()}
    out = []
    for n in np.argsort(-scores)[:50]:
        s, pid = float(scores[n]), ids[n]
        if s < DUP_MIN_SCORE:
            break
        r = pool.get(pid)
        if not r or _base(pid) in excluded:
            continue
        y = exact_year(r)
        if posted(r):
            out.append(_hint("near_duplicate", None, None, y, s,
                             f"Gleiches Bild wie {r.get('signature') or pid} (Ähnlichkeit {s:.2f}), "
                             f"verschickt {y}: Aufnahme spätestens {y}"))
        else:
            out.append(_hint("near_duplicate", y, y - 2, y + 2, s,
                             f"Gleiches Bild wie {r.get('signature') or pid} (Ähnlichkeit {s:.2f}), datiert {y}"))
        if len(out) >= k:
            break
    return out


def card_number_hints(rec: dict, excluded: set[str]) -> list[dict]:
    f, c = family(publisher(rec)), card_number((rec.get("raw") or {}).get("Karten Nr."))
    if not f or not c:
        return []
    refs = [x for x in _series_index().get((f, c[0]), []) if _base(x[3]) not in excluded]
    near = sorted(refs, key=lambda x: abs(x[0] - c[1]))
    exact = [x for x in near if not x[2]][:3]
    use = exact if len(exact) >= 2 else near[:3]
    if len(use) < 2 or abs(use[0][0] - c[1]) > NUMBER_MAX_GAP:
        return []
    years = [x[1] for x in use]
    gap = abs(use[0][0] - c[1])
    series = f" Serie {c[0]}" if c[0] else ""
    return [_hint("card_number", round(st.median(years)), min(years) - 3, max(years) + 3,
                  0.8 if gap <= 50 else 0.6,
                  f"Verlag {f}{series} Nr. {c[1]}: Nachbarnummern " +
                  ", ".join(f"{n} ({y}{', Poststempel' if b else ''})" for n, y, b, _ in use))]


def _norm(s: str) -> str:
    return re.sub(r"[^a-zäöü]+", " ", (s or "").lower()).strip()


def nb_negative_hints(rec: dict) -> list[dict]:
    """A Wehrli card number is often the negative number, but only when the place agrees: a number
    match alone hits the wrong place most of the time (94 of 359 matches agree on the place).
    The match uses the card's Thema tags, so the evidence text must never name the place."""
    if family(publisher(rec)) not in WEHRLI_FAMILIES:
        return []
    c = card_number((rec.get("raw") or {}).get("Karten Nr."))
    if not c or c[0]:
        return []
    names = {_norm(p) for p in (rec.get("places") or []) + [rec.get("municipality") or ""] if len(_norm(p)) >= 4}
    out = []
    for n in _nb_negatives().get(c[1], []):
        text = _norm(f"{n.get('title')} {n.get('place')}")
        if any(name in text for name in names):
            lo, hi = n["year_from"], n.get("year_to") or n["year_from"]
            pad = 3 if n.get("approximate") else 1
            out.append(_hint("nb_negative", round((lo + hi) / 2), lo - pad, hi + pad, 0.8,
                             f"Negativ {n['ead_id']} der Nationalbibliothek, datiert {n['date_raw']}",
                             f"https://www.helveticarchives.admin.ch/detail.aspx?ID={n['ha_id']}"))
            break
    return out


def publisher_rule_hints(rec: dict) -> list[dict]:
    pub = publisher(rec)
    if not pub:
        return []
    return [_hint("publisher_rule", None, r["year_min"], r["year_max"],
                  {"high": 0.9, "medium": 0.7, "low": 0.4}[r["confidence"]],
                  f"Verlagsangabe '{pub}': {r['feature']}", r["source"])
            for r in rules() if r["applies"] == "publisher" and re.search(r["match"], pub, re.I)]


def _bin(y: int) -> int:
    return min(max(y, PROBE_BINS[0]), PROBE_BINS[-1]) // 5 * 5


def train_probe() -> dict:
    from sklearn.linear_model import LogisticRegression

    X, _, row = _clip()
    pool = [r for r in _dated_pool() if r["id"] in row and not posted(r)]
    xs = X[[row[r["id"]] for r in pool]]
    ys = np.array([_bin(exact_year(r)) for r in pool])
    clf = LogisticRegression(max_iter=2000, C=2.0)
    clf.fit(xs, ys)
    PROBE_FILE.write_bytes(pickle.dumps(clf))
    _probe.cache_clear()
    return {"trained_on": len(pool), "classes": len(clf.classes_)}


@lru_cache(maxsize=1)
def _probe():
    return pickle.loads(PROBE_FILE.read_bytes()) if PROBE_FILE.exists() else None


def year_probe_hint(vec: np.ndarray) -> list[dict]:
    clf = _probe()
    if clf is None:
        return []
    p = clf.predict_proba(vec.reshape(1, -1))[0]
    cls = clf.classes_
    cum = np.cumsum(p)
    low = int(cls[np.searchsorted(cum, 0.1)])
    high = int(cls[min(np.searchsorted(cum, 0.9), len(cls) - 1)]) + 4
    mid = int(cls[np.searchsorted(cum, 0.5)]) + 2
    return [_hint("year_probe", mid, low, high, 0.4,
                  f"Bildstil-Modell (CLIP, trainiert auf datierten Fotos): wahrscheinlich {low} bis {high}")]


@lru_cache(maxsize=1)
def _ids_by_source() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in read_jsonl(RECORDS / "all.jsonl"):
        out.setdefault(r["source"], []).append(r["id"])
    return out


def eval_exclusions(photo_id: str) -> list[str]:
    """Extra ids to exclude when scoring photo_id. LUBIS and NB photos come in survey campaigns and
    numbered series whose members look alike and share dates, so for an eval photo from those
    collections the whole collection is excluded. Stricter than real use, on purpose."""
    source = photo_id.split(":", 1)[0]
    return [i for i in _ids_by_source().get(source, []) if i != photo_id] if source in ("lubis", "nb") else []


# ---------- contract ----------

def date_hints(photo_id: str | None = None, image_path: str | None = None, exclude_ids=()) -> list[dict]:
    """All date hints for a photo. Pass the query's own id in exclude_ids (eval leakage rule)."""
    excluded = {_base(i) for i in exclude_ids} | ({_base(photo_id)} if photo_id else set())
    rec = get_record(photo_id) if photo_id else None
    out: list[dict] = []
    vec = _vector(photo_id, image_path)
    if vec is not None:
        out += near_duplicate_hints(vec, excluded)
        out += year_probe_hint(vec)
    if rec:
        out += card_number_hints(rec, excluded)
        out += nb_negative_hints(rec)
        out += publisher_rule_hints(rec)
    return sorted(out, key=lambda h: -h["weight"])


# ---------- check ----------

def check() -> dict:
    """Accuracy of each hint kind on eval cards with an exact, unposted year (sources exclude eval)."""
    truth = [t for t in read_jsonl(SPLITS / "eval.jsonl")
             if not t.get("year_is_upper_bound") and t.get("year_from") and t.get("year_from") == t.get("year_to")]
    by_kind: dict[str, list] = {}
    for t in truth:
        y = t["year_from"]
        for h in date_hints(t["id"], exclude_ids=eval_exclusions(t["id"])):
            row = by_kind.setdefault(h["kind"], [])
            inside = (h["year_low"] is None or h["year_low"] <= y) and (h["year_high"] is None or y <= h["year_high"])
            row.append((abs(h["year"] - y) if h["year"] is not None else None, inside))
    out = {"eval_cards": len(truth)}
    for kind, rows in by_kind.items():
        errs = sorted(e for e, _ in rows if e is not None)
        out[kind] = {"cards": len(rows), "range_contains_truth": round(sum(i for _, i in rows) / len(rows), 3)}
        if errs:
            out[kind] |= {"median_error": errs[len(errs) // 2],
                          "within_5": round(sum(e <= 5 for e in errs) / len(errs), 3)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["train-probe", "check", "hints"])
    ap.add_argument("photo_id", nargs="?")
    a = ap.parse_args()
    if a.cmd == "train-probe":
        print(train_probe())
    elif a.cmd == "check":
        print(json.dumps(check(), indent=1))
    else:
        print(json.dumps(date_hints(a.photo_id), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
