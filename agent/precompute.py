"""CLI: analyse and cache a list of photos (demo cards, or the challenge batch).

    python -m agent.precompute [<photo_id> ...]                       # default: the demo cards
    python -m agent.precompute --split challenge [--priority 1]       # the challenge photos, Prio 1 first
        [--model M] [--workers 4] [--max-cost USD] [--fresh]

Cards that already have a cached result from the same model are skipped unless --fresh, so a stopped run
just continues. After the first 10 new results it prints their cost and a projection for the whole list.
Afterwards the server answers /analyze from the cache and the demo needs no API.
"""

import argparse
import sys
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import anthropic
import httpx

from . import config, llm, loop, results, schemas

REPORT_AFTER = 10
MAX_CONNECTION_ERRORS = 5  # in a row: the network is down, stop instead of failing every photo


def demo_ids() -> list[str]:
    from .server import catalogue

    return [it["id"] for it in catalogue.demo()]


def split_ids(split: str, priority: int | None = None) -> list[str]:
    from .server import catalogue

    return [r["id"] for r in catalogue.list_records(split, priority=priority)]


def precompute(ids: list[str], model: str = config.MODEL, fresh: bool = False, max_cost: float = 5.0,
               workers: int = 1, log=print) -> dict:
    """Analyse and cache each id. Returns {done, skipped, failed, cost_usd}."""
    stats = {"done": [], "skipped": [], "failed": [], "cost_usd": 0.0}
    todo = []
    for pid in ids:
        if not fresh and results.load(pid, model=model):
            stats["skipped"].append(pid)
        else:
            todo.append(pid)
    if stats["skipped"]:
        log(f"{len(stats['skipped'])} schon im Cache, {len(todo)} zu analysieren")
    stop = threading.Event()
    lock = threading.Lock()
    offline = {"streak": 0}

    def one(pid: str):
        if stop.is_set():
            return pid, None, "skip"
        try:
            return pid, loop.analyze(pid, model=model), None
        except (llm.MissingKey, llm.SessionBudgetExceeded) as e:  # every later card would fail too
            stop.set()
            return pid, None, f"Abbruch, {e}"
        except (anthropic.APIConnectionError, httpx.TransportError) as e:
            return pid, None, f"Keine Verbindung ({type(e).__name__})"
        except Exception as e:  # noqa: BLE001  one bad card must not stop the others
            return pid, None, f"Fehler {type(e).__name__}: {e}"

    def record(pid: str, r: dict | None, err: str | None) -> None:
        n = len(stats["done"]) + len(stats["failed"]) + 1
        tag = f"[{n}/{len(todo)}] {pid}"
        if err:
            stats["failed"].append(pid)
            if err != "skip":
                log(f"{tag}: {err}")
            offline["streak"] = offline["streak"] + 1 if err.startswith("Keine Verbindung") else 0
            if offline["streak"] >= MAX_CONNECTION_ERRORS and not stop.is_set():
                stop.set()
                log(f"Abbruch: {MAX_CONNECTION_ERRORS} Verbindungsfehler hintereinander, das Netz ist weg. "
                    "Den gleichen Befehl später erneut starten, fertige Fotos werden übersprungen.")
            return
        offline["streak"] = 0
        problems = schemas.errors({k: v for k, v in r.items() if k != "part_results"}, "analysis_result")
        results.save(r)
        cost = r["usage"]["cost_usd"]
        stats["cost_usd"] = round(stats["cost_usd"] + cost, 6)
        stats["done"].append(pid)
        f = r["fields"]
        where = ", ".join(str(v) for v in (f.get("locality", {}).get("value"), f["municipality"]["value"]) if v) \
            or "Ort nicht bestimmbar"
        parts = f", {len(r['composite']['parts'])} Teile" if r.get("composite") else ""
        warn = f", SCHEMA: {problems[0]}" if problems else ""
        flag = "Prüfung" if r.get("needs_review") else "ok"
        log(f"{tag}: {where} ({r['overall_confidence']:.2f}, {flag}){parts}, ${cost:.3f}{warn}")
        if len(stats["done"]) == REPORT_AFTER:
            avg = stats["cost_usd"] / REPORT_AFTER
            log(f"== Kosten nach {REPORT_AFTER} Fotos: ${stats['cost_usd']:.2f}, im Schnitt ${avg:.3f} pro Foto; "
                f"hochgerechnet auf alle {len(todo)}: ${avg * len(todo):.2f} "
                f"(Kostenlimit dieses Laufs ${max_cost:.2f}, Gesamtbudget ${config.SESSION_BUDGET_USD:.0f}, "
                f"bisher ${llm.ledger_total():.2f})")

    queue = list(reversed(todo))  # pop() keeps the list order (Prio 1 first)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        running = set()
        while queue or running:
            while queue and len(running) < max(1, workers) and not stop.is_set():
                avg = stats["cost_usd"] / len(stats["done"]) if stats["done"] else 0.0
                if stats["cost_usd"] + avg * (len(running) + 1) > max_cost:
                    log(f"Kostenlimit ${max_cost:.2f} erreicht: keine neuen Fotos mehr")
                    stop.set()
                    break
                running.add(pool.submit(one, queue.pop()))
            if not running:
                break
            finished, running = wait(running, return_when=FIRST_COMPLETED)
            for fut in finished:
                with lock:
                    record(*fut.result())
    stats["failed"] += list(reversed(queue))  # never started
    log(f"Fertig: {len(stats['done'])} neu, {len(stats['skipped'])} aus dem Cache, "
        f"{len(stats['failed'])} fehlgeschlagen oder nicht gestartet, ${stats['cost_usd']:.2f}")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m agent.precompute", description=__doc__.split("\n\n")[0])
    ap.add_argument("photo_ids", nargs="*", help="default: the demo cards (GET /demo)")
    ap.add_argument("--split", help="all photos of a split, e.g. challenge (Prio 1 first)")
    ap.add_argument("--priority", type=int, help="only this priority (1 = the 50 Prio-1 photos)")
    ap.add_argument("--model", default=config.MODEL, help=f"default {config.MODEL}")
    ap.add_argument("--workers", type=int, default=1, help="photos analysed at the same time (default 1)")
    ap.add_argument("--fresh", action="store_true", help="re-run photos that are already cached")
    ap.add_argument("--max-cost", type=float, default=5.0, help="stop starting new photos above this (USD)")
    args = ap.parse_args(argv)
    if args.photo_ids:
        ids = args.photo_ids
    elif args.split:
        ids = split_ids(args.split, args.priority)
    else:
        ids = demo_ids()
    if not ids:
        print("Keine Fotos gefunden: ohne Daten (DATA_PIPELINE_URL + DATA_PIPELINE_TOKEN in .env) gibt es keine "
              "Challenge-Fotos, und für die Demo-Karten fehlt noch eine demo()-Funktion in data_pipeline. "
              "Ids direkt angeben: python -m agent.precompute <id> ...", file=sys.stderr)
        return 2
    s = precompute(ids, args.model, args.fresh, args.max_cost, args.workers,
                   log=lambda m: print(m, file=sys.stderr, flush=True))
    return 0 if not s["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
