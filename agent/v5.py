"""v5 analysis: agent.pipeline (retrieval + check + registers) and, only when that is not enough, one
agent.decide call. Returns the same AnalysisResult (CONTRACTS section 3) as the v3 loop, so the server,
the report and the Excel export work unchanged. loop.analyze() routes here when AGENT_PIPELINE=5.
"""

import secrets
import time
from typing import Callable

import data_pipeline as dp

from . import calibration, decide, llm, pipeline, results
from .config import MODEL
from .tools import submit

STRONG_INLIERS = 100  # a verified match this strong is accepted without a Claude call


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _context(rec: dict) -> tuple[str, list[dict]]:
    """(text for Claude, session siblings already placed by v5 as extra candidates)."""
    raw = rec.get("raw") or {}
    exif = raw.get("exif") or {}
    lines = []
    if (rec.get("date") or {}).get("raw"):
        lines.append(f"Aufgenommen (EXIF): {rec['date']['raw']}, Brennweite {exif.get('focal_35mm') or '?'} mm (KB)")
    sibs = []
    for sid in raw.get("session") or []:
        r = results.load(sid)
        c = (((r or {}).get("fields") or {}).get("coordinates") or {}).get("value")
        if not r or not c or (r.get("settings") or {}).get("pipeline") != 5:
            continue
        f = r["fields"]
        sibs.append({"id": sid, "source": "challenge", "score": 0.0, "inliers": None, "lat": c["lat"], "lon": c["lon"],
                     "precision_m": c.get("radius_m") or 300, "municipality": f["municipality"]["value"],
                     "title": "Foto aus derselben Aufnahmeserie (bereits bestimmt)", "places": [],
                     "year": (rec.get("date") or {}).get("year_from"), "image": None})
    return "\n".join(lines), sibs


def _ev(kind: str, summary: str, ref_id: str | None = None, score: float | None = None) -> dict:
    return {"kind": kind, "summary": summary, "ref_id": ref_id, "url": None, "score": score, "supports": True}


def analyze(photo_id: str | None = None, image_path: str | None = None, *, model: str = MODEL,
            exclude_ids: list[str] = (), on_event: Callable[[dict], None] | None = None) -> dict:
    rec = dp.get_record(photo_id) if photo_id else {}
    if image_path is None:
        image_path = str(dp.image_file(rec))
    trace: list[dict] = []

    def emit(item: dict) -> None:
        item = {"step": len(trace) + 1, **item}
        trace.append(item)
        if on_event:
            on_event(item)

    excl = ([photo_id] if photo_id else []) + [i for i in exclude_ids if i]
    t0 = time.monotonic()
    loc = pipeline.locate(image_path, exclude_ids=excl)
    fe = loc["features"]
    emit({"type": "tool_call", "tool": "similar_images", "input": {"k": pipeline.K_RETRIEVE, "verify": True},
          "output_summary": f"{fe['n_verified']} geometrisch bestätigte Referenzfotos, bestes mit "
                            f"{fe['top_inliers']} Punkten", "ms": round((time.monotonic() - t0) * 1000)})

    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
             "cache_creation_input_tokens": 0, "cost_usd": 0.0, "budget_hit": False}
    path, point, nm, answer, ref = loc["decided_by"], loc["point"], loc["names"], None, None
    if point:
        g = loc["groups"][0]
        ref = next(h for h in loc["hits"] if h["id"] == g["members"][0])
    if path != "match" or fe["top_inliers"] < STRONG_INLIERS:
        context, sibs = _context(rec or {})
        cands = sibs[:2] + decide.candidates(loc["hits"])
        cands = cands[:decide.N_CANDIDATES]
        t1 = time.monotonic()
        answer, usd = decide.ask(llm.make_client(), image_path, cands, context,
                                 meta={"photo_id": photo_id, "pipeline": 5})
        usage["cost_usd"] = round(usd, 6)
        emit({"type": "tool_call", "tool": "claude_decide", "input": {"candidates": len(cands)},
              "output_summary": (answer or {}).get("reason") or "keine Antwort",
              "ms": round((time.monotonic() - t1) * 1000)})
        if answer:
            path, point, nm, ref = _combine(path, point, nm, ref, answer, cands)
    return _result(photo_id, model, path, point, nm or {}, answer, ref, fe, trace, usage, emit)


def _combine(path, point, nm, ref, answer: dict, cands: list[dict]):
    """Retrieval answer + Claude's answer -> (path, point, names, ref). Rules, first that applies:
    1. Claude picks a candidate with a precise location: the same place as the match confirms it,
       another place replaces it.
    2. Claude read or recognised a name: looked up in the registers, inside the Gemeinde Claude (or
       a picked municipality-level candidate) names.
    3. The retrieval answer stays when Claude names no other Gemeinde (unconfirmed, lower confidence).
    4. Else Claude's Gemeinde alone (always reviewed)."""
    k = answer.get("candidate")
    pick = cands[k - 1] if isinstance(k, int) and 1 <= k <= len(cands) else None
    mun = answer.get("municipality")
    if pick and pick["lat"] is not None and pick["precision_m"] <= pipeline.PRECISE_M:
        if point and pipeline.haversine_m((point["lat"], point["lon"]), (pick["lat"], pick["lon"])) <= pipeline.CLUSTER_M:
            return "match_confirmed", point, nm, pick
        p = {"lat": pick["lat"], "lon": pick["lon"], "radius_m": pick["precision_m"]}
        return "claude_pick", p, pipeline.names(pick["lat"], pick["lon"], [pick]), pick
    if pick and pick["municipality"]:
        mun = pick["municipality"]
        ref = pick
    if answer.get("place_query") and (hit := decide.lookup(answer["place_query"], mun)):
        p = {k: hit[k] for k in ("lat", "lon", "radius_m")}
        out = pipeline.names(hit["lat"], hit["lon"])
        out["lookup_source"] = hit["source"]
        return "claude_text", p, out, (pick if pick else None)
    if path in ("match", "municipality") and (not mun or decide._in(mun, (nm or {}).get("municipality"))):
        return (path + "_unconfirmed"), point, nm, ref
    if mun:
        return "claude_name", None, {"locality": answer.get("locality"), "municipality": mun,
                                     "street": None, "building": None}, (pick if pick else None)
    return None, None, None, None


def _result(photo_id, model, path, point, nm, answer, ref, fe, trace, usage, emit) -> dict:
    f = submit.empty_fields()
    conf = calibration.score(fe, path)
    why = {
        "match": "Geometrisch bestätigtes Referenzfoto",
        "match_confirmed": "Geometrisch bestätigtes Referenzfoto, von Claude als gleicher Ort bestätigt",
        "claude_pick": "Claude erkennt denselben Ort auf einem Referenzfoto",
        "claude_text": "Name im Bild gelesen bzw. Wahrzeichen erkannt, im Register nachgeschlagen",
        "claude_name": "Nur Claudes Einschätzung, kein Referenzfoto und kein Registereintrag",
        "municipality": "Bestätigte Referenzfotos, nur auf Gemeindeebene verortet",
        "match_unconfirmed": "Schwach bestätigtes Referenzfoto, von Claude nicht bestätigt",
        "municipality_unconfirmed": "Schwach bestätigte Referenzfotos auf Gemeindeebene, von Claude nicht bestätigt",
    }.get(path)
    ref_ev = []
    if ref:
        ref_ev = [_ev("similar_image", f"{why}: {ref.get('title') or ref['id']}"
                                       + (f" ({ref['inliers']} passende Punkte)" if ref.get("inliers") else ""),
                      ref["id"], ref.get("inliers"))]
    reg = [_ev("address_register", "Amtliches Verzeichnis am bestimmten Punkt")] if point else []
    claude = [_ev("visual_cue", answer["reason"])] if answer and answer.get("reason") else []
    if answer and answer.get("text_read"):
        claude.append(_ev("text_on_card", f"Gelesen: {answer['text_read'][:200]}"))

    def put(name: str, value, evidence: list[dict]) -> None:
        if value in (None, [], ""):
            return
        f[name] = {"value": value, "confidence": conf.get(name, 0.0), "evidence": evidence}

    put("municipality", nm.get("municipality"), ref_ev + reg + (claude if path == "claude_name" else []))
    put("locality", nm.get("locality"), ref_ev + reg + (claude if path == "claude_name" else []))
    put("street", nm.get("address") or nm.get("street"), ref_ev + reg)
    buildings = [nm["building"]] if nm.get("building") else []
    bev = [_ev("named_building", nm.get("building_reason") or "Gebäudeverzeichnis")] if buildings else []
    if answer:
        for b in answer.get("buildings") or []:
            if b not in buildings:
                buildings.append(b)
                bev = bev + claude
    put("buildings", buildings, bev)
    put("landscape_features", (answer or {}).get("landscape_features") or [], claude)
    if point:
        f["coordinates"] = {"value": point, "confidence": conf.get("coordinates", 0.0), "evidence": ref_ev + reg}
    overall = min(f["municipality"]["confidence"], f["locality"]["confidence"] or f["municipality"]["confidence"])
    needs_review = overall < calibration.ACCEPT
    expl = (f"{why or 'Kein Treffer'}. Konfidenz aus gemessener Trefferquote ({calibration.source(path)})."
            if path else "Kein Referenzfoto passt und im Bild ist kein Ort erkennbar: offen gelassen.")
    emit({"type": "final", "text": f"{nm.get('locality') or '?'}, {nm.get('municipality') or '?'} "
                                   f"(Konfidenz {overall:.2f})", "ms": 0})
    return {
        "photo_id": photo_id, "run_id": f"{_now()}-{secrets.token_hex(2)}",
        "status": "needs_review" if needs_review else "done", "model": model, "composite": None,
        "fields": f, "overall_confidence": round(overall, 3), "confidence_explanation": expl,
        "needs_review": needs_review, "review": None, "rejected_hypotheses": [], "trace": trace,
        "usage": {**usage, "api_calls": 1 if answer is not None else 0}, "created_at": _now(),
        "estimates": {"place_name_printed": None},
        "settings": {"pipeline": 5, "path": path, "features": fe},
    }
