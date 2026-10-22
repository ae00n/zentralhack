"""Eval runner: analyse the eval cards, compute the baseline, write the EvalSummary.

    python -m agent.eval.runner --baseline-only                          # free, similarity only
    python -m agent.eval.runner --limit 50 --model claude-haiku-5-5      # cheap debug pass
    python -m agent.eval.runner --model claude-opus-5-5 --max-cost 40    # the official run
    python -m agent.eval.runner --summary-only                           # rescore cached results

Resumable: an item with a cached result for the same model (results.load) is skipped, and every
result is saved as soon as it finishes. A failing item is logged to RESULTS_DIR/eval_errors.jsonl
and retried on the next run. New items stop being scheduled when the spend of this run plus the
estimated cost of the items in flight would pass --max-cost.
"""

import argparse
import json
import sys
import time
import traceback
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone

from .. import config, loop, results, schemas
from . import baseline as bl
from . import items as eval_items
from . import summary as sm

# rough cost per item before the first results come in (the cap uses the running mean after that)
PRIOR_COST = {"claude-opus-5-5": 0.06, "claude-haiku-5-5": 0.003}


def _exclusions(photo_id: str) -> list[str]:
    from data_pipeline.dating import eval_exclusions

    return eval_exclusions(photo_id)


def analyze_one(photo_id: str, model: str) -> dict:
    result = loop.analyze(photo_id, None, model=model, exclude_ids=_exclusions(photo_id))
    if result.get("status") == "error":
        raise RuntimeError(result.get("error") or "AnalysisResult mit status error")
    return result


def _log_error(photo_id: str, model: str, err: str) -> None:
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    row = {"photo_id": photo_id, "model": model, "error": err,
           "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with (config.RESULTS_DIR / "eval_errors.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _cost(result: dict) -> float:
    return float((result.get("usage") or {}).get("cost_usd") or 0.0)


def run_agent(items: list[dict], *, model: str, workers: int = 4, max_cost: float = 40.0,
              fresh: bool = False, log: Callable[[str], None] = print) -> dict:
    """Analyse every item without a cached result for `model`. Returns run stats."""
    todo = [it for it in items if fresh or results.load(it["id"], model=model) is None]
    log(f"{len(items)} Eval-Items, {len(items) - len(todo)} schon im Cache für {model}, {len(todo)} offen")
    stats = {"done": 0, "errors": [], "spent": 0.0, "budget_stop": False, "not_scheduled": 0}
    if not todo:
        return stats
    prior = PRIOR_COST.get(model, 0.06)
    names = sm.municipality_names()
    queue = list(reversed(todo))  # pop() from the end keeps the item order
    in_flight: dict = {}
    t0 = time.monotonic()

    def estimate() -> float:
        return stats["spent"] / stats["done"] if stats["done"] >= 3 else prior

    def fill(pool: ThreadPoolExecutor) -> None:
        while queue and len(in_flight) < workers and not stats["budget_stop"]:
            if stats["spent"] + (len(in_flight) + 1) * estimate() > max_cost:
                stats["budget_stop"] = True
                log(f"Kostenlimit ${max_cost:.2f}: keine neuen Items mehr (bisher ${stats['spent']:.2f}, "
                    f"{len(in_flight)} laufen noch)")
                break
            it = queue.pop()
            in_flight[pool.submit(analyze_one, it["id"], model)] = (it, time.monotonic())

    with ThreadPoolExecutor(max_workers=workers) as pool:
        fill(pool)
        while in_flight:
            finished, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for fut in finished:
                it, started = in_flight.pop(fut)
                n = stats["done"] + len(stats["errors"]) + 1
                try:
                    result = fut.result()
                except Exception as e:  # noqa: BLE001  one failing item must not stop the run
                    err = f"{type(e).__name__}: {e}"
                    stats["errors"].append({"photo_id": it["id"], "error": err})
                    _log_error(it["id"], model, err + "\n" + traceback.format_exc(limit=5))
                    log(f"[{n}/{len(todo)}] {it['id']} FEHLER {err}")
                    continue
                problems = schemas.errors(result, "analysis_result")
                if problems:
                    log(f"  Warnung: {it['id']} verletzt das Schema: {problems[0]}")
                results.save(result)
                cost = _cost(result)
                stats["done"] += 1
                stats["spent"] += cost
                m = (result.get("fields") or {}).get("municipality") or {}
                ok = "ok" if sm.canonical(m.get("value"), names) == it["municipality"] else "falsch"
                log(f"[{n}/{len(todo)}] {it['id']} {m.get('value')} ({m.get('confidence', 0):.2f}, {ok}) "
                    f"{time.monotonic() - started:.0f}s ${cost:.3f}, gesamt ${stats['spent']:.2f}")
            fill(pool)
    stats["not_scheduled"] = len(queue)
    log(f"Fertig in {time.monotonic() - t0:.0f}s: {stats['done']} neu, {len(stats['errors'])} Fehler, "
        f"{stats['not_scheduled']} nicht gestartet, ${stats['spent']:.2f} ausgegeben")
    return stats


def explain_missing(path) -> str:
    return (f"Keine Eval-Items gefunden: {path} fehlt oder ist leer.\n"
            "Die Ground Truth kommt von Data (Dijar): data/splits/eval.jsonl, gebaut mit "
            "`python -m data_pipeline.splits`, oder aus dem Offline-Bundle.\n"
            "Den Ordner mit ZH_DATA_DIR=/pfad/zu/data setzen, oder eine eigene Datei mit --eval-file angeben. "
            "Im Stub-Modus (DATA_PIPELINE_STUB=1) gibt es keine Eval-Items.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="only the first N items (interleaved across subsets)")
    ap.add_argument("--model", default=config.MODEL, help=f"default {config.MODEL}, debug {config.DEBUG_MODEL}")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--subset", action="append", choices=eval_items.SUBSETS, help="repeatable")
    ap.add_argument("--max-cost", type=float, default=40.0, help="USD cap for new analyses in this run")
    ap.add_argument("--fresh", action="store_true", help="ignore cached results (paid again)")
    ap.add_argument("--baseline-only", action="store_true", help="similarity baseline only, no Claude calls")
    ap.add_argument("--summary-only", action="store_true", help="no Claude calls, summarise cached results")
    ap.add_argument("--no-baseline", action="store_true", help="use cached baseline rows only, compute none")
    ap.add_argument("--baseline-model", default="fused", help="similar_images model for the baseline")
    ap.add_argument("--no-verify", action="store_true", help="baseline without LightGlue verification (faster)")
    ap.add_argument("--eval-file", help="eval items JSONL (default data/splits/eval.jsonl)")
    a = ap.parse_args(argv)

    items = eval_items.load(a.eval_file, a.subset, a.limit)
    if not items:
        print(explain_missing(a.eval_file or eval_items.eval_file()))
        return 1

    if not (a.baseline_only or a.summary_only):
        run_agent(items, model=a.model, workers=a.workers, max_cost=a.max_cost, fresh=a.fresh)

    base = bl.run(items, model=a.baseline_model, verify=not a.no_verify, compute=not a.no_baseline)
    if a.baseline_only:
        acc, n = bl.accuracy(base, items)
        if acc is None:
            print("Keine Baseline-Vorhersagen (kein Index oder keine Bilder auf diesem Rechner).")
            return 1
        print(f"Baseline nur Ähnlichkeit (top {bl.TOP}, Mehrheit): Gemeinde {acc * 100:.1f}% auf {n} Items")
        from data_pipeline.metrics import score

        base_list = [{k: v for k, v in base[it["id"]].items() if k not in ("votes", "neighbours", "settings")}
                     for it in items if it["id"] in base]
        for label, val, best in sm.benchmark_rows(score(base_list, truth=items)):
            print(f"  {label:<28}{val:>10}  (Best so far {best})")
        return 0

    by_id = {it["id"]: results.load(it["id"], model=a.model) for it in items}
    names = sm.municipality_names()
    summary = sm.build(items, by_id, model=a.model, baseline_preds=base, names=names)
    if summary is None:
        print(f"Keine Ergebnisse für {a.model} im Cache ({config.RESULTS_DIR}) für diese {len(items)} Items. "
              "Zuerst ohne --summary-only laufen lassen.")
        return 1
    preds = [sm.to_prediction(r, names) for r in by_id.values() if r]
    path = sm.write(summary, [{k: v for k, v in p.items() if k != "decade"} for p in preds])
    sm.report(summary)
    print(f"\nGeschrieben: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
