"""v7 analyze(): attempts -> candidates -> image check -> judge -> tier -> AnalysisResult (CONTRACTS 3).

CLI: python -m agent.v7.pipeline [ids...] (default: all Prio 1), --workers N.
"""

import random
import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import data_pipeline as dp

from .. import fields as submit
from .. import results
from ..config import MODEL
from . import attempt, check, ground, judge, tiers, vision
from .common import dist_m, gem, generic_name, original, small, upload_record
from .tools import NOT_PLACES

MAX_CANDIDATES = 5
ACCEPT = 0.9  # the brief: above 90% is accepted without review
# kinds that look alike from outside: a guessed care home is compared with hospitals and schools too
LOOKALIKE = [{"Spital", "Alters-/Pflegeheim", "Soziale Einrichtung", "Schule"},
             {"Hotel", "Restaurant", "Tourismus"}, {"Kirche/Kapelle", "Kloster"},
             {"Bahnhof", "Station", "Bergbahnstation"}]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ev(kind: str, summary: str, ref_id: str | None = None, score: float | None = None, url: str | None = None,
        supports: bool = True) -> dict:
    return {"kind": kind, "summary": summary, "ref_id": ref_id, "url": url, "score": score, "supports": supports}


def merge(cands: list[dict]) -> list[dict]:
    """One candidate per place (150 m): the attempts that proposed it are listed together."""
    out: list[dict] = []
    for c in cands:
        same = next((o for o in out if ground.same_place(o, c) or (
            o.get("lat") is None and c.get("lat") is None and o.get("outside") and o["outside"] == c.get("outside"))), None)
        if same:
            same["attempts"].append(c["attempt"])
            for k in ("building", "street", "locality"):
                same[k] = same[k] or c.get(k)
            if c["anchor"] in ("building", "address") and same["anchor"] not in ("building", "address"):
                same.update({k: c[k] for k in ("anchor", "lat", "lon", "radius_m")})
        else:
            out.append({**c, "attempts": [c["attempt"]]})
    return out


def lookalikes(cands: list[dict], answers: list[dict]) -> list[dict]:
    """Same-kind named buildings within 3 km of a guessed building, when no attempt was sure of it."""
    if any((a or {}).get("building_certainty") == "sicher" for a in answers):
        return []
    base = next((c for c in cands if c["anchor"] == "building" and c.get("building")), None)
    if not base:
        return []
    hits = [h for h in dp.find_building(base["building"], base["municipality"]) if h["kind"] not in NOT_PLACES]
    group = next((g for g in LOOKALIKE if hits and hits[0]["kind"] in g), None)
    if not group:
        return []
    from data_pipeline.places import named_buildings
    out = []
    for b in named_buildings(lat=base["lat"], lon=base["lon"], radius_m=3000, limit=400):
        if b["kind"] not in group or b.get("generic") or any(dist_m(b, x) < 80 for x in cands + out):
            continue
        out.append({"anchor": "building", "attempt": "lookalike", "lat": b["lat"], "lon": b["lon"], "radius_m": 50,
                    "building": b["name"], "municipality": b.get("municipality"),
                    "locality": dp.address_at(b["lat"], b["lon"], 40).get("ortschaft"),
                    "street": b.get("address") or next((x["address"] for x in
                                                        dp.address_at(b["lat"], b["lon"], 40).get("addresses") or []), None),
                    "outside": None, "claude_municipality": None, "landmarks": [], "attempts": ["Register (ähnliches Gebäude)"]})
        if len(out) == 3:
            break
    return out


def landmarks(names: list[str], center: dict | None) -> list[str]:
    """Landmark names that swissNAMES3D knows within 40 km, in the official spelling."""
    out = []
    for n in names:
        q = re.sub(r"^(der|die|das|the)\s+", "", n.strip(), flags=re.I)
        q = re.sub(r"^Grosse[rs]?\s", "Gross ", re.sub(r"^Kleine[rs]?\s", "Chli ", q))  # swisstopo: "Chli Mythen"
        lat, lon = (center["lat"], center["lon"]) if center and center.get("lat") else (47.02, 8.75)
        hits = dp.landmarks_near(lat, lon, 40, name=q, limit=1)
        if hits and hits[0]["name"] not in out:
            out.append(hits[0]["name"])
    return out


def analyze(photo_id: str | None = None, image_path: str | None = None, *, model: str = MODEL,
            exclude_ids: list[str] = (), on_event: Callable[[dict], None] | None = None) -> dict:
    rec = dp.get_record(photo_id) if photo_id else (upload_record(image_path) if image_path else None)
    if not rec:
        raise ValueError(f"unknown photo_id {photo_id!r}")
    photo_id = rec["id"]
    trace: list[dict] = []

    def emit(item: dict) -> None:
        item = {"step": len(trace) + 1, **item}
        trace.append(item)
        if on_event:
            on_event(item)

    meta = {"photo_id": photo_id, "pipeline": 7}
    t0 = time.monotonic()
    v = vision.detect(photo_id, original(rec))
    emit({"type": "tool_call", "tool": "web_detection", "input": {},
          "output_summary": ("Websuche: " + ", ".join(e["name"] for e in v["entities"][:5])) if v else "keine Websuche",
          "ms": round((time.monotonic() - t0) * 1000)})

    t0 = time.monotonic()
    with ThreadPoolExecutor(3) as ex:
        runs = list(ex.map(lambda var: attempt.run(rec, var, meta), attempt.VARIANTS))
    usd = sum(r["usd"] for r in runs if not r.get("cached"))
    for r in runs:
        a = r["answer"] or {}
        emit({"type": "tool_call", "tool": f"attempt:{r['variant']}", "input": {"cached": r.get("cached")},
              "output_summary": f"{a.get('building') or a.get('locality') or '?'}, {a.get('municipality') or a.get('outside_canton') or '?'}: "
                                f"{a.get('reason') or 'keine Antwort'}", "ms": round((time.monotonic() - t0) * 1000)})

    cands = [c for c in (ground.candidate(r) for r in runs) if c]
    cands = merge(cands)
    cands += lookalikes(cands, [r["answer"] for r in runs])
    cands = sorted(cands, key=lambda c: -len([a for a in c["attempts"] if a in attempt.VARIANTS]))[:MAX_CANDIDATES]

    t0 = time.monotonic()
    strong = attempt.strong_refs(rec)
    photo = str(small(rec))
    for c in cands:
        c["check"] = check.check(photo, c, strong) if c.get("municipality") else {"best_inliers": 0, "pass": False,
                                                                                  "photos": [], "by_match": None}
    emit({"type": "tool_call", "tool": "check", "input": {"candidates": len(cands)},
          "output_summary": "; ".join(f"{c.get('building') or c.get('locality') or c.get('municipality') or c.get('outside')}: "
                                      f"{c['check']['best_inliers']} Punkte" for c in cands) or "keine Kandidaten",
          "ms": round((time.monotonic() - t0) * 1000)})

    pick, chosen = None, None
    if any(c.get("municipality") for c in cands):  # only outside-canton verdicts: nothing to compare
        t0 = time.monotonic()
        random.Random(rec["id"]).shuffle(cands)  # the judge must not read the attempts' vote from the order
        pick, cost = judge.judge(rec, cands, meta)
        usd += cost
        k = (pick or {}).get("candidate")
        chosen = cands[k - 1] if isinstance(k, int) and 1 <= k <= len(cands) else None
        emit({"type": "tool_call", "tool": "judge", "input": {"candidates": len(cands)},
              "output_summary": (pick or {}).get("reason") or "keine Entscheidung",
              "ms": round((time.monotonic() - t0) * 1000)})
    if chosen is None:
        # judge rejected all: the outside-canton verdict of a majority still counts
        outside = [c for c in cands if c.get("outside") and len(c["attempts"]) >= 2]
        chosen = {**outside[0], "municipality": None, "locality": None, "building": None, "street": None,
                  "lat": None, "lon": None} if outside else None
    r = result(rec, model, runs, cands, chosen, pick, v, usd, trace, emit)
    from ..photo_marks import marks
    r["photo_marks"], cost = marks(rec, r)
    r["usage"]["cost_usd"] = round(r["usage"]["cost_usd"] + cost, 6)
    return r


def result(rec, model, runs, cands, chosen, pick, v, usd, trace, emit) -> dict:
    answers = [r["answer"] or {} for r in runs]
    t, facts = tiers.tier(chosen, answers, pick)
    conf, measured = tiers.value(t)
    f = submit.empty_fields()
    reasons = [_ev("visual_cue", f"Untersuchung '{r['variant']}': {a['reason']}") for r, a in zip(runs, answers)
               if a.get("reason") and chosen and r["variant"] in chosen["attempts"]]
    texts = [_ev("text_on_card", f"Gelesen: {a['text_read'][:200]}") for a in answers[:1] if a.get("text_read")]
    chk = (chosen or {}).get("check") or {}
    img_ev = [_ev("similar_image", f"Vergleichsfoto vor Ort: {p.get('title') or p['id']} ({p['distance_m']} m, "
                                   f"{p['inliers']} passende Punkte)", p["id"], p["inliers"]) for p in chk.get("photos", [])[:2]
              if p["inliers"] >= check.WEAK_INLIERS]
    if chk.get("by_match"):
        img_ev.append(_ev("similar_image", f"Bildsuche: {chk['by_match'].get('title') or chk['by_match']['id']} "
                                           f"({chk['by_match']['inliers']} passende Punkte)", chk["by_match"]["id"],
                          chk["by_match"]["inliers"]))
    reg_ev = [_ev("named_building" if chosen["anchor"] == "building" else "address_register",
                  "Amtliches Register (GWR, OSM, KGS) am Ort des Motivs")] if chosen and chosen["anchor"] in ("building", "address") else []
    agree_ev = [_ev("visual_cue", f"{facts['agree']} von 3 unabhängigen Untersuchungen nennen diese Gemeinde")] if facts else []
    web_ev = [_ev("web_page", f"Websuche: {pg['title']}", url=pg["url"]) for pg in (v or {}).get("pages", [])[:2]
              if chosen and pg.get("title") and any(w and w.casefold() in pg["title"].casefold()
                                                     for w in (chosen.get("building"), chosen.get("locality")))]

    def put(name, value, c, evidence):
        if value in (None, [], ""):
            return
        f[name] = {"value": value, "confidence": round(c, 3), "evidence": evidence}

    if chosen and chosen.get("municipality"):
        reg = chosen["anchor"] in ("building", "address")
        common = img_ev + reg_ev + agree_ev + web_ev + reasons
        put("municipality", chosen["municipality"], conf, common)
        put("locality", chosen.get("locality"), conf, common)
        named = chosen.get("building") and not generic_name(chosen["building"])  # "Kirche" is no name
        put("buildings", [chosen["building"]] if named else [], conf if reg else min(conf, 0.5),
            reg_ev + img_ev + web_ev + reasons)
        put("street", chosen.get("street"), conf if reg else min(conf, 0.4), reg_ev)
        if chosen.get("lat") is not None:
            f["coordinates"] = {"value": {"lat": chosen["lat"], "lon": chosen["lon"], "radius_m": chosen["radius_m"]},
                                "confidence": round(conf, 3), "evidence": img_ev + reg_ev}
        marks = landmarks(sorted({m for a in answers for m in a.get("landmarks") or []}), chosen)
        put("landscape_features", marks, min(conf, 0.8), [_ev("map_layer", "swissNAMES3D (swisstopo)")] + reasons)
    overall = f["municipality"]["confidence"]
    needs_review = overall < ACCEPT or not f["municipality"]["value"]
    expl = tiers.explain(t, facts, f, (chosen or {}).get("anchor"), chk.get("best_inliers"), overall, measured,
                         upload=bool(rec.get("upload_path")))
    if chosen and chosen.get("outside") and not chosen.get("municipality"):
        expl = f"Nicht im Kanton Schwyz: vermutlich {chosen['outside']}. Felder offen gelassen."
    rejected = [{"hypothesis": f"{c.get('building') or c.get('locality') or c.get('municipality') or c.get('outside')}"
                               f" ({', '.join(c['attempts'])})", "reason": f"Bildvergleich {c['check']['best_inliers']} Punkte"}
                for c in cands if c is not chosen]
    emit({"type": "final", "text": f"{f['locality']['value'] or '?'}, {f['municipality']['value'] or '?'} "
                                   f"(Stufe {t}, Konfidenz {overall:.2f})", "ms": 0})
    return {
        "photo_id": rec["id"], "run_id": f"{_now()}-{secrets.token_hex(2)}",
        "status": "needs_review" if needs_review else "done", "model": model, "composite": None,
        "fields": f, "overall_confidence": round(overall, 3), "confidence_explanation": expl,
        "needs_review": needs_review, "review": None, "rejected_hypotheses": rejected, "trace": trace,
        "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
                  "cost_usd": round(usd, 6), "budget_hit": False, "api_calls": 0},
        "created_at": _now(), "estimates": {"place_name_printed": None},
        "settings": {"pipeline": 7, "tier": t, "facts": facts, "judge": pick,
                     "answers": {r["variant"]: r["answer"] for r in runs},
                     "candidates": [{k: c.get(k) for k in ("attempts", "anchor", "building", "street", "locality",
                                                           "municipality", "outside", "lat", "lon")}
                                    | {"inliers": c["check"]["best_inliers"]} for c in cands]},
    }


def run(photo_ids: list[str], save: bool = True) -> list[dict]:
    out = []
    for pid in photo_ids:
        try:
            r = analyze(pid)
        except Exception as e:  # one photo must not stop the batch
            print(f"{pid}: FEHLER {type(e).__name__}: {e}", flush=True)
            continue
        if save:
            results.archive(pid)
            results.save(r)
        out.append(r)
        print(f"{pid}: {r['trace'][-1]['text']}  ${r['usage']['cost_usd']:.3f}", flush=True)
    return out


def main() -> None:
    import argparse

    from data_pipeline.jsonl import read_jsonl
    from data_pipeline.paths import RECORDS

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ids", nargs="*", help="photo ids; default: all Prio 1")
    ap.add_argument("--all", action="store_true", help="all 603 challenge photos")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    ids = a.ids or [r["id"] for r in read_jsonl(RECORDS / "challenge.jsonl")
                    if a.all or (r.get("raw") or {}).get("priority") == 1]
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(lambda pid: run([pid]), ids))


if __name__ == "__main__":
    main()
