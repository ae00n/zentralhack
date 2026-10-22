"""HelveticArchives (Swiss National Library, scopeArchiv Query): Photoglob-Wehrli negatives.

    python -m data_pipeline.scrapers.helveticarchives wehrli [--limit-series N] [--max-windows N]
    python -m data_pipeline.scrapers.helveticarchives stats

`wehrli` builds a table negative number -> date for the fonds "Photoglob-Wehrli: Archiv
Wehrli" (ID 97219). The fonds has one series per 1,000 negatives (EAD-WEHR-1-999 ...
EAD-WEHR-39000-39999). Tree labels already carry number, title and date, e.g.
"EAD-WEHR-20678-B Herrliberg, Schipfgut, Teilaussenansicht (1911.06)", so no detail pages
are needed: one tree window (about 100 siblings) per 50 negatives.

Same software as the Staatsarchiv Schwyz, so the tree walk mirrors staatsarchiv.py: a
window around ID x shows ~100 siblings and requesting the last id moves it on by 50.
A series' first child comes from the "lower-level entry" link on its detail page.

Postcard card numbers ("Karten Nr.") on Wehrli cards appear to be these negative numbers,
so the table helps date undated cards. `stats` prints number vs year per 1,000 bucket and
cross-checks against Staatsarchiv Wehrli/Photoglob cards in data/records/all.jsonl.

Output: data/raw/helveticarchives/wehrli_negatives.jsonl (resumable per series).
"""

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict

from bs4 import BeautifulSoup

from ..http import PoliteClient
from ..jsonl import read_jsonl
from ..paths import RAW, RECORDS, ensure
from .staatsarchiv import _find, _node_data, parse_date

BASE = "https://www.helveticarchives.admin.ch"
WEHRLI_FONDS = "97219"

OUT_DIR = RAW / "helveticarchives"
WEHRLI_FILE = OUT_DIR / "wehrli_negatives.jsonl"

client = PoliteClient(min_interval=2.0, cache_dir=OUT_DIR / "http")

LABEL_RE = re.compile(r"^(EAD-WEHR-(\d+)(?:-([A-Za-z0-9]+))?)\s*(.*)$")


# ---------- tree walk ----------

def _tree(entry_id: str) -> tuple[str, dict[str, str]]:
    """Tree page around entry_id: (html, {id: label}) over the whole rendered tree."""
    html = client.text(f"{BASE}/archivplansuche.aspx?ID={entry_id}")
    soup = BeautifulSoup(html, "lxml")
    labels = [s.get_text(" ", strip=True) for s in soup.select("span.rtIn")]
    flat = []

    def walk(ns):
        for n in ns:
            flat.append(n["value"])
            walk(n.get("items", []))

    walk(_node_data(html))
    return html, dict(zip(flat, labels))


def _window(entry_id: str, node: str) -> tuple[list[tuple[str, str]], bool]:
    """Siblings under `node` around entry_id: ([(id, label)], has_next).

    Paging entries ("Open the next 100 entries", "Go to the last entry") are nodes with a
    negative id; any of them after the last real item means more items follow."""
    html, by_id = _tree(entry_id)
    parent = _find(_node_data(html), node)
    if parent is None:
        raise RuntimeError(f"{entry_id} is not under node {node}")
    values = [n["value"] for n in parent.get("items", [])]
    real = [i for i, v in enumerate(values) if not v.startswith("-")]
    has_next = bool(real) and any(v.startswith("-") for v in values[real[-1] + 1:])
    return [(values[i], by_id.get(values[i], "")) for i in real], has_next


def _children(node: str) -> list[tuple[str, str]]:
    """Children of a small node (under 100): the tree only expands a node around a selected child."""
    seed = _first_child(node)
    return _window(seed, node)[0] if seed else []


def _first_child(node: str) -> str | None:
    """First child id, from the "lower-level entry" link on the node's detail page."""
    html = client.text(f"{BASE}/detail.aspx?ID={node}")
    m = re.search(r'_ap_lnkUntergeordneterEintrag"\s+href="detail\.aspx\?ID=(\d+)"', html) or \
        re.search(r'_ap_imgUntergeordneterEintrag"\s+href="detail\.aspx\?ID=(\d+)"', html)
    return m.group(1) if m else None


def walk_series(node: str, max_windows: int | None = None) -> list[tuple[str, str]]:
    seed = _first_child(node)
    if not seed:
        return []
    seen: dict[str, str] = {}
    order: list[str] = []
    last, windows = seed, 0
    while True:
        rows, has_next = _window(last, node)
        windows += 1
        new = 0
        for v, text in rows:
            if v not in seen:
                seen[v] = text
                order.append(v)
                new += 1
        if not has_next or not rows or (new == 0 and rows[-1][0] == last):
            break
        if max_windows and windows >= max_windows:
            break
        last = rows[-1][0]
    return [(v, seen[v]) for v in order]


# ---------- label parsing ----------

def _split_date(rest: str) -> tuple[str, str | None]:
    """'Axenstrasse, Landschaft (1911 (ca.))' -> ('Axenstrasse, Landschaft', '1911 (ca.)')."""
    rest = rest.strip()
    if not rest.endswith(")"):
        return rest, None
    depth = 0
    for i in range(len(rest) - 1, -1, -1):
        if rest[i] == ")":
            depth += 1
        elif rest[i] == "(":
            depth -= 1
            if depth == 0:
                inner = rest[i + 1:-1].strip()
                if re.search(r"\d{4}|Jh", inner):
                    return rest[:i].strip(), inner
                return rest, None
    return rest, None


def parse_label(ha_id: str, label: str, series: str) -> dict | None:
    m = LABEL_RE.match(label)
    if not m:
        return None
    title, date_raw = _split_date(m.group(4))
    d = parse_date(date_raw)
    return {
        "ha_id": ha_id,
        "ead_id": m.group(1),
        "number": int(m.group(2)),
        "suffix": m.group(3),
        "date_raw": date_raw,
        "year_from": d["year_from"],
        "year_to": d["year_to"],
        "approximate": d["approximate"],
        "title": title or None,
        "place": title.split(",")[0].strip() if title else None,
        "series_id": series,
    }


def wehrli(limit_series: int | None, max_windows: int | None) -> None:
    ensure(OUT_DIR)
    series = _children(WEHRLI_FONDS)
    series = [(v, t) for v, t in series if t.startswith("EAD-WEHR-")]
    done = {r.get("series_id") for r in read_jsonl(WEHRLI_FILE)}
    todo = [s for s in series if s[0] not in done]
    if limit_series:
        todo = todo[:limit_series]
    print(f"wehrli: {len(series)} series, {len(done)} done, walking {len(todo)}", flush=True)
    with WEHRLI_FILE.open("a") as out:
        for node, name in todo:
            rows = walk_series(node, max_windows)
            parsed = [p for v, t in rows if (p := parse_label(v, t, node))]
            bad = len(rows) - len(parsed)
            # write a series in one go so a crash never leaves half a series behind
            out.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in parsed))
            out.flush()
            dated = sum(1 for r in parsed if r["year_from"] or r["year_to"])
            print(f"  {name}: {len(parsed)} negatives, {dated} dated, {bad} unparsed labels"
                  f" ({client.requests} requests so far)", flush=True)


# ---------- analysis ----------

def _year(r: dict) -> float | None:
    a, b = r.get("year_from"), r.get("year_to")
    if a and b:
        return (a + b) / 2
    return a or b


def _q(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    f = int(k)
    return xs[f] + (xs[min(f + 1, len(xs) - 1)] - xs[f]) * (k - f)


def stats() -> None:
    rows = list(read_jsonl(WEHRLI_FILE))
    print(f"{len(rows)} negatives, {sum(1 for r in rows if _year(r))} dated, "
          f"{sum(1 for r in rows if r['approximate'])} approximate")
    print("suffixes:", Counter(r["suffix"] for r in rows).most_common(8))

    print("\nbucket       n  median  IQR")
    buckets = defaultdict(list)
    for r in rows:
        if (y := _year(r)):
            buckets[r["number"] // 1000].append(y)
    meds = []
    for b in sorted(buckets):
        ys = buckets[b]
        med = statistics.median(ys)
        meds.append(med)
        print(f"{b * 1000:>6}-{b * 1000 + 999:<6} {len(ys):>5} {med:>6.0f}  {_q(ys, .25):.0f}-{_q(ys, .75):.0f}")
    drops = sum(1 for a, b in zip(meds, meds[1:]) if b < a)
    print(f"median decreases between consecutive buckets: {drops} of {len(meds) - 1}")

    print("\nsuffix  n  median year by number range (same number, different suffix)")
    by_num = defaultdict(dict)
    for r in rows:
        if (y := _year(r)):
            by_num[r["number"]][r["suffix"]] = y
    pairs = [(d["A"], d["B"]) for d in by_num.values() if "A" in d and "B" in d]
    if pairs:
        diffs = [b - a for a, b in pairs]
        print(f"numbers with both -A and -B dated: {len(pairs)}, median B-A {statistics.median(diffs):+.1f} y, "
              f"|B-A|<=2: {sum(1 for x in diffs if abs(x) <= 2) / len(diffs):.0%}")
    for s in ("A", "B", None):
        ys = [_year(r) for r in rows if r["suffix"] == s and _year(r)]
        if ys:
            print(f"  suffix {s}: {len(ys)} dated, median {statistics.median(ys):.0f}, IQR {_q(ys, .25):.0f}-{_q(ys, .75):.0f}")

    crosscheck(rows)


def crosscheck(rows: list[dict]) -> None:
    neg = defaultdict(list)
    for r in rows:
        neg[r["number"]].append(r)
    cards = matched = 0
    diffs, examples = [], []
    for rec in read_jsonl(RECORDS / "all.jsonl"):
        if rec.get("source") != "staatsarchiv":
            continue
        raw = rec.get("raw") or {}
        who = raw.get("Autor/Fotograf/Künstler") or ""
        nr = (raw.get("Karten Nr.") or "").strip()
        if not ("Wehrli" in who or "Photoglob" in who) or not nr.isdigit():
            continue
        cards += 1
        hits = neg.get(int(nr))
        if not hits:
            continue
        matched += 1
        cy = _year(rec.get("date") or {})
        ny = [y for h in hits if (y := _year(h))]
        if cy and ny:
            n = statistics.median(ny)
            diffs.append(abs(cy - n))
            if len(examples) < 10:
                examples.append((nr, rec.get("title"), (rec.get("date") or {}).get("raw"), hits[0]["ead_id"],
                                 hits[0]["title"], hits[0]["date_raw"]))
    print(f"\ncross-check: {cards} Staatsarchiv Wehrli/Photoglob cards with a digits-only Karten Nr., "
          f"{matched} match a negative number, {len(diffs)} have a year on both sides")
    if diffs:
        print(f"  median |card year - negative year| {statistics.median(diffs):.1f}, "
              f"<=2 y: {sum(1 for d in diffs if d <= 2) / len(diffs):.0%}, <=5 y: {sum(1 for d in diffs if d <= 5) / len(diffs):.0%}")
    for e in examples:
        print("  Nr {} | card {!r} ({}) | {} {!r} ({})".format(*e))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["wehrli", "stats"])
    ap.add_argument("--limit-series", type=int, help="walk at most N series (test runs)")
    ap.add_argument("--max-windows", type=int, help="at most N tree windows per series (test runs)")
    a = ap.parse_args()
    if a.cmd == "wehrli":
        wehrli(a.limit_series, a.max_windows)
    else:
        stats()


if __name__ == "__main__":
    main()
