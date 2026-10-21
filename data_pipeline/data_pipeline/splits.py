"""Eval / showcase / timeline / demo splits (docs/CONTRACTS.md section 1).

    python -m data_pipeline.splits [--seed 42]

- eval:     three subsets, each stratified by municipality (ground truth = municipality + year):
            card_exact   unposted SG.CIV.12 cards with an exact catalogue year
            card_posted  posted cards: the catalogue year is often the postmark, so it is only an
                         upper bound for the photo (year_is_upper_bound)
            photo_dated  LUBIS / NB photos with a capture date (clean truth for dating)
- showcase: undated Staatsarchiv cards with an image (the "Keine Angabe" story)
- reference: everything else (E-Pics, Smapshot, remaining Staatsarchiv cards)
The split is written back into data/records/all.jsonl (and only there). Same seed + same records
gives the same eval set. Re-run once after the full scrape, then treat eval.jsonl as frozen.
"""

import argparse
import random
import re
from collections import Counter, defaultdict

from .jsonl import read_jsonl, write_json, write_jsonl
from .paths import RECORDS, SPLITS

FAMOUS = [
    ("Hauptplatz", "Schwyz", "Hauptplatz Schwyz: viele datierte Karten, ideal für die Zeitreise"),
    ("Brunnen", "Ingenbohl", "Brunnen am See: bekanntes Motiv mit Mythen und Urmiberg"),
    ("Kloster", "Einsiedeln", "Kloster Einsiedeln: markantes Gebäude, gut für Evidenz"),
    ("Rigi", None, "Rigi: Gipfelpanorama, Test für Gelände- und Bergerkennung"),
    ("Mythen", "Schwyz", "Mythen: ikonische Silhouette, Test für Landschaftsmerkmale"),
]


def _has_image(r: dict) -> bool:
    return bool((r.get("image") or {}).get("path"))


def _decade(r: dict) -> int | None:
    y = r["date"].get("year_from")
    return y // 10 * 10 if y else None


def _composite_hint(r: dict) -> bool:
    t = (r.get("title") or "").lower()
    return " und " in t or " mit " in t or "gruss aus" in t or len(r.get("places") or []) >= 3


def stratified_eval(pool: list[dict], target: int, seed: int) -> list[dict]:
    """Proportional allocation per municipality, at least 3 per municipality where available."""
    rng = random.Random(seed)
    by_m = defaultdict(list)
    for r in sorted(pool, key=lambda r: r["id"]):
        by_m[r["municipality"]].append(r)
    if len(pool) <= target:
        return sorted(pool, key=lambda r: r["id"])
    alloc = {}
    for m, rs in by_m.items():
        alloc[m] = min(len(rs), max(3, round(target * len(rs) / len(pool))))
    # trim the largest municipalities until the total fits
    while sum(alloc.values()) > target:
        m = max(alloc, key=lambda k: alloc[k])
        alloc[m] -= 1
    out = []
    for m, rs in by_m.items():
        out += rng.sample(rs, alloc[m])
    return sorted(out, key=lambda r: r["id"])


def timeline_sets(dated: list[dict], min_cards: int = 4) -> list[dict]:
    """Group dated cards that resolved to the same place (same gazetteer point)."""
    groups = defaultdict(list)
    for r in dated:
        loc = r.get("location")
        if not loc:
            continue
        groups[(round(loc["lat"], 4), round(loc["lon"], 4))].append(r)
    sets = []
    for (lat, lon), rs in groups.items():
        years = {r["date"]["year_from"] for r in rs}
        if len(rs) < min_cards or len(years) < 2:
            continue
        muni = Counter(r["municipality"] for r in rs if r["municipality"]).most_common(1)
        tags = Counter(p for r in rs for p in r["places"] if not muni or p != muni[0][0]).most_common(1)
        place = tags[0][0] if tags else (muni[0][0] if muni else "?")
        rs = sorted(rs, key=lambda r: (r["date"]["year_from"], r["id"]))
        sets.append({
            "place": place,
            "municipality": muni[0][0] if muni else None,
            "lat": lat, "lon": lon,
            "n": len(rs),
            "years": [rs[0]["date"]["year_from"], rs[-1]["date"]["year_from"]],
            "ids": [r["id"] for r in rs],
        })
    return sorted(sets, key=lambda s: -s["n"])


def demo_candidates(stasz: list[dict], eval_ids: set[str], n: int = 10) -> list[dict]:
    """A deterministic mix: famous places, undated cards, composite-looking cards. Never eval cards."""
    pool = [r for r in stasz if _has_image(r) and r["id"] not in eval_ids]
    picked: list[dict] = []

    def take(r, why):
        if r and r["id"] not in {p["id"] for p in picked} and len(picked) < n:
            picked.append({"id": r["id"], "why": why, "signature": r.get("signature"), "title": r.get("title")})

    def text(r):
        return ((r.get("title") or "") + " " + " ".join(r.get("places") or [])).lower()

    for word, muni, why in FAMOUS:
        hit = next((r for r in pool if word.lower() in text(r) and (muni is None or r["municipality"] == muni)), None)
        take(hit, why)
    for r in pool:
        if r["date"].get("year_from") is None and r["municipality"] and len(picked) < 7:
            take(r, "Undatierte Karte (Entstehungszeitraum: keine Angabe): Kernstory des Pitches")
    for r in pool:
        if _composite_hint(r):
            take(r, "Wahrscheinlich Mehrbildkarte: zeigt das automatische Zerlegen")
    return picked


EVAL_SUBSETS = {"card_exact": 150, "card_posted": 100, "photo_dated": 100}
DATED_PHOTO_SOURCES = ("lubis", "nb")


def _exact_year(r: dict) -> int | None:
    d = r.get("date") or {}
    y = d.get("year_from")
    return y if y and y == d.get("year_to") and not d.get("approximate") else None


def _posted(r: dict) -> bool:
    z = ((r.get("raw") or {}).get("Zusatzinfos") or "").lower()
    return "gelaufen" in z and "ungelaufen" not in z


def eval_subsets(rows: list[dict], seed: int, sizes: dict = EVAL_SUBSETS) -> dict[str, list[dict]]:
    ok = [r for r in rows if _has_image(r) and r.get("municipality") and _exact_year(r)]
    cards = [r for r in ok if r["source"] == "staatsarchiv" and r.get("collection") == "SG.CIV.12"]
    pools = {
        "card_exact": [r for r in cards if not _posted(r)],
        "card_posted": [r for r in cards if _posted(r)],
        # Zinggeler plates show the negative number in the image, so they stay references only
        "photo_dated": [r for r in ok if r["source"] in DATED_PHOTO_SOURCES and r.get("collection") != "Zinggeler"],
    }
    return {name: stratified_eval(pool, sizes[name], seed) for name, pool in pools.items()}


def build(seed: int = 42) -> dict:
    rows = list(read_jsonl(RECORDS / "all.jsonl"))
    if not rows:
        raise SystemExit("data/records/all.jsonl is empty: run python -m data_pipeline.merge first")
    stasz = [r for r in rows if r["source"] == "staatsarchiv"]
    dated = [r for r in stasz if r["date"].get("year_from") and _has_image(r)]
    subsets = eval_subsets(rows, seed)
    ev = [r for rs in subsets.values() for r in rs]
    subset_of = {r["id"]: name for name, rs in subsets.items() for r in rs}
    ev_ids = set(subset_of)
    showcase = [r for r in stasz if not r["date"].get("year_from") and _has_image(r)]
    sc_ids = {r["id"] for r in showcase}

    for r in rows:
        r["split"] = "eval" if r["id"] in ev_ids else "showcase" if r["id"] in sc_ids else "reference"
    write_jsonl(RECORDS / "all.jsonl", rows)

    write_jsonl(SPLITS / "eval.jsonl", (
        {"id": r["id"], "subset": subset_of[r["id"]], "municipality": r["municipality"],
         "year_from": r["date"]["year_from"], "year_to": r["date"]["year_to"],
         "approximate": r["date"].get("approximate", False),
         "year_is_upper_bound": subset_of[r["id"]] == "card_posted"}
        for r in ev))
    write_jsonl(SPLITS / "showcase.jsonl", ({"id": r["id"]} for r in showcase))
    # timeline sets use all dated cards except eval ones, so the time slider never shows eval answers
    tsets = timeline_sets([r for r in dated if r["id"] not in ev_ids])
    write_json(SPLITS / "timeline_sets.json", tsets)
    demo = demo_candidates(stasz, ev_ids)
    write_json(SPLITS / "demo.json", demo)

    stats = {
        "records": len(rows),
        "by_source": dict(Counter(r["source"] for r in rows)),
        "staatsarchiv": {
            "total": len(stasz),
            "with_image": sum(1 for r in stasz if _has_image(r)),
            "dated": sum(1 for r in stasz if r["date"].get("year_from")),
            "undated": sum(1 for r in stasz if not r["date"].get("year_from")),
            "approximate_dates": sum(1 for r in stasz if r["date"].get("approximate")),
            "with_municipality": sum(1 for r in stasz if r.get("municipality")),
            "by_collection": dict(Counter(r.get("collection") for r in stasz)),
        },
        "references_with_coordinates": sum(1 for r in rows if r["source"] != "staatsarchiv" and r.get("location")),
        "references_in_canton": sum(1 for r in rows if (r.get("raw") or {}).get("in_canton")),
        "eval": {
            "n": len(ev),
            "by_subset": {name: len(rs) for name, rs in subsets.items()},
            "seed": seed,
            "by_municipality": dict(Counter(r["municipality"] for r in ev).most_common()),
            "by_decade": dict(sorted(Counter(_decade(r) for r in ev).items())),
        },
        "showcase": len(showcase),
        "timeline_sets": len(tsets),
        "timeline_top": [{"place": s["place"], "n": s["n"], "years": s["years"]} for s in tsets[:10]],
        "demo_candidates": len(demo),
        "licenses": dict(Counter((r.get("license") or {}).get("code") for r in rows)),
    }
    write_json(SPLITS / "stats.json", stats)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    s = build(seed=a.seed)
    print({k: s[k] for k in ("records", "by_source", "showcase", "timeline_sets", "demo_candidates")})
    print("eval", s["eval"]["n"], s["eval"]["by_subset"])


if __name__ == "__main__":
    main()
