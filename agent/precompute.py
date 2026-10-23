"""CLI: analyse and cache a list of photos (demo cards, or the challenge batch).

    python -m agent.precompute [<photo_id> ...]                       # default: the demo cards
    python -m agent.precompute --split challenge [--priority 1]       # the challenge photos, Prio 1 first
        [--model M] [--workers 4] [--max-cost USD] [--fresh] [--runs 2]

Cards that already have a cached result from the same model are skipped unless --fresh, so a stopped run
just continues. Photos of one session (record.raw.session) run one after another in the same worker, so a
later sibling sees the earlier siblings' results in its prompt. With --runs 2 every photo is analysed twice
and both runs must name the same place (agent.consistency), else the result needs review. After the first
10 new results it prints their cost and a projection for the whole list.
Afterwards the server answers /analyze from the cache and the demo needs no API.
"""

import argparse
import sys
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import anthropic
import httpx

from . import config, consistency, llm, loop, results, schemas

REPORT_AFTER = 10
MAX_CONNECTION_ERRORS = 5  # in a row: the network is down, stop instead of failing every photo


def demo_ids() -> list[str]:
    from .server import catalogue

    return [it["id"] for it in catalogue.demo()]


def split_ids(split: str, priority: int | None = None) -> list[str]:
    from .server import catalogue

    return [r["id"] for r in catalogue.list_records(split, priority=priority)]


def sessions(ids: list[str]) -> list[list[str]]:
    """Group the ids into sessions (connected via record.raw.session, only ids in this list), in the
    order of first appearance; each group keeps the list order. Photos without a session are alone."""
    from .server import catalogue

    order = list(dict.fromkeys(ids))
    pos = {pid: i for i, pid in enumerate(order)}
    parent = {pid: pid for pid in order}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for pid in order:
        try:
            rec = catalogue.get_record(pid) or {}
        except Exception:  # noqa: BLE001  no record, no session: the photo runs on its own
            rec = {}
        for sid in (rec.get("raw") or {}).get("session") or []:
            if sid in parent:
                a, b = find(pid), find(sid)
                if a != b:  # the earlier member stays the root
                    first, other = (a, b) if pos[a] < pos[b] else (b, a)
                    parent[other] = first
    groups: dict[str, list[str]] = {}
    for pid in order:
        groups.setdefault(find(pid), []).append(pid)
    return sorted(groups.values(), key=lambda g: pos[g[0]])


def precompute(ids: list[str], model: str = config.MODEL, fresh: bool = False, max_cost: float = 5.0,
               workers: int = 1, log=print, runs: int = 1) -> dict:
    """Analyse and cache each id. Returns {done, skipped, failed, cost_usd}.

    runs >= 2: every photo is analysed that many times; the most confident run is kept and marked with
    its consistency (agent.consistency.combine), every run goes into the history. The photos of one
    session are one unit of work: they run one after another in the same worker (all runs of a photo
    before its next sibling); different sessions run in parallel."""
    runs = max(1, runs)
    stats = {"done": [], "skipped": [], "failed": [], "cost_usd": 0.0}
    todo = []
    for pid in dict.fromkeys(ids):
        if not fresh and results.load(pid, model=model):
            stats["skipped"].append(pid)
        else:
            todo.append(pid)
    if stats["skipped"]:
        log(f"{len(stats['skipped'])} schon im Cache, {len(todo)} zu analysieren")
    groups = sessions(todo)
    multi = [g for g in groups if len(g) > 1]
    if multi:
        log(f"{len(multi)} Sessions mit {sum(map(len, multi))} Fotos: Geschwister laufen nacheinander")
    if runs > 1:
        log(f"Jedes Foto wird {runs} Mal unabhängig analysiert (Konsistenzprüfung)")
    stop = threading.Event()
    lock = threading.Lock()
    state = {"streak": 0, "runs_done": 0, "in_flight": 0}

    def reserve() -> bool:
        """May one more photo start? Checks the stop flag and the cost cap (estimate: runs x cost per run)."""
        with lock:
            if stop.is_set():
                return False
            per_run = stats["cost_usd"] / state["runs_done"] if state["runs_done"] else 0.0
            if stats["cost_usd"] + per_run * runs * (state["in_flight"] + 1) > max_cost:
                log(f"Kostenlimit ${max_cost:.2f} erreicht: keine neuen Fotos mehr")
                stop.set()
                return False
            state["in_flight"] += 1
            return True

    def analyze_runs(pid: str) -> tuple[list[dict], str | None]:
        out = []
        try:
            for _ in range(runs):
                out.append(loop.analyze(pid, model=model))
            return out, None
        except (llm.MissingKey, llm.SessionBudgetExceeded) as e:  # every later card would fail too
            stop.set()
            return out, f"Abbruch, {e}"
        except (anthropic.APIConnectionError, httpx.TransportError) as e:
            return out, f"Keine Verbindung ({type(e).__name__})"
        except Exception as e:  # noqa: BLE001  one bad card must not stop the others
            return out, f"Fehler {type(e).__name__}: {e}"

    def record(pid: str, done_runs: list[dict], err: str | None) -> None:
        n = len(stats["done"]) + len(stats["failed"]) + 1
        tag = f"[{n}/{len(todo)}] {pid}"
        cost = round(sum((r.get("usage") or {}).get("cost_usd", 0.0) for r in done_runs), 6)
        stats["cost_usd"] = round(stats["cost_usd"] + cost, 6)
        state["runs_done"] += len(done_runs)
        if err:
            for r in done_runs:  # paid for: keep it comparable, but not as the current result
                results.add_history(r)
            stats["failed"].append(pid)
            log(f"{tag}: {err}")
            state["streak"] = state["streak"] + 1 if err.startswith("Keine Verbindung") else 0
            if state["streak"] >= MAX_CONNECTION_ERRORS and not stop.is_set():
                stop.set()
                log(f"Abbruch: {MAX_CONNECTION_ERRORS} Verbindungsfehler hintereinander, das Netz ist weg. "
                    "Den gleichen Befehl später erneut starten, fertige Fotos werden übersprungen.")
            return
        state["streak"] = 0
        r = consistency.combine(done_runs)
        for other in done_runs:  # the runs not kept go straight into the history
            if other.get("run_id") != r.get("run_id"):
                results.add_history(other)
        problems = schemas.errors({k: v for k, v in r.items() if k != "part_results"}, "analysis_result")
        results.save(r)
        stats["done"].append(pid)
        f = r["fields"]
        where = ", ".join(str(v) for v in (f.get("locality", {}).get("value"), f["municipality"]["value"]) if v) \
            or "Ort nicht bestimmbar"
        parts = f", {len(r['composite']['parts'])} Teile" if r.get("composite") else ""
        warn = f", SCHEMA: {problems[0]}" if problems else ""
        flag = "Prüfung" if r.get("needs_review") else "ok"
        c = r.get("consistency")
        stable = "" if not c else ", stabil" if c["agree"] else \
            ", INSTABIL: " + " / ".join(dict.fromkeys(consistency.place(v) for v in c["values"]))
        log(f"{tag}: {where} ({r['overall_confidence']:.2f}, {flag}){parts}{stable}, ${cost:.3f}{warn}")
        if len(stats["done"]) == REPORT_AFTER:
            avg = stats["cost_usd"] / REPORT_AFTER
            log(f"== Kosten nach {REPORT_AFTER} Fotos: ${stats['cost_usd']:.2f}, im Schnitt ${avg:.3f} pro Foto; "
                f"hochgerechnet auf alle {len(todo)}: ${avg * len(todo):.2f} "
                f"(Kostenlimit dieses Laufs ${max_cost:.2f}, Gesamtbudget ${config.SESSION_BUDGET_USD:.0f}, "
                f"bisher ${llm.ledger_total():.2f})")

    def unit(group: list[str]) -> None:
        """One session: its photos one after another, in the same worker."""
        for i, pid in enumerate(group):
            if not reserve():
                with lock:
                    stats["failed"] += group[i:]  # never started
                return
            done_runs, err = analyze_runs(pid)
            with lock:
                state["in_flight"] -= 1
                try:
                    record(pid, done_runs, err)
                except Exception as e:  # noqa: BLE001  a broken result must not stop the batch
                    stats["failed"].append(pid)
                    log(f"{pid}: Fehler beim Speichern {type(e).__name__}: {e}")

    queue = list(reversed(groups))  # pop() keeps the list order (Prio 1 first)
    width = max(1, workers)
    with ThreadPoolExecutor(max_workers=width) as pool:
        running = set()
        while queue or running:
            while queue and len(running) < width and not stop.is_set():
                running.add(pool.submit(unit, queue.pop()))
            if not running:
                break
            finished, running = wait(running, return_when=FIRST_COMPLETED)
            for fut in finished:
                fut.result()
    for group in reversed(queue):  # never started
        stats["failed"] += group
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
    ap.add_argument("--runs", type=int, default=1,
                    help="independent analyses per photo; 2 or more checks that they name the same place")
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
                   log=lambda m: print(m, file=sys.stderr, flush=True), runs=args.runs)
    return 0 if not s["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
