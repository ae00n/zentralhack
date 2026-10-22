"""CLI: pre-compute and cache the agent results for the demo cards (build order step 8).

    python -m agent.precompute [--model M] [--fresh] [--max-cost USD] [<photo_id> ...]

Without ids it takes the demo list in pitch order (GET /demo). Cards that already have a cached result
from the same model are skipped unless --fresh. Afterwards the demo needs no API: the server answers
/analyze from the cache and the frontend demo mode replays the cached trace.
"""

import argparse
import sys

from . import config, llm, loop, results, schemas


def demo_ids() -> list[str]:
    from .server import catalogue

    return [it["id"] for it in catalogue.demo()]


def precompute(ids: list[str], model: str = config.MODEL, fresh: bool = False, max_cost: float = 5.0,
               log=print) -> dict:
    """Analyse and cache each id. Returns {done, skipped, failed, cost_usd}."""
    stats = {"done": [], "skipped": [], "failed": [], "cost_usd": 0.0}
    for i, pid in enumerate(ids, 1):
        tag = f"[{i}/{len(ids)}] {pid}"
        if not fresh and results.load(pid, model=model):
            stats["skipped"].append(pid)
            log(f"{tag}: schon im Cache")
            continue
        if stats["cost_usd"] >= max_cost:
            stats["failed"].append(pid)
            log(f"{tag}: übersprungen, Kostenlimit ${max_cost:.2f} erreicht")
            continue
        try:
            r = loop.analyze(pid, model=model)
        except (llm.MissingKey, llm.SessionBudgetExceeded) as e:  # every later card would fail too
            stats["failed"].extend(ids[i - 1:])
            log(f"{tag}: Abbruch, {e}")
            break
        except Exception as e:  # noqa: BLE001  one bad card must not stop the others
            stats["failed"].append(pid)
            log(f"{tag}: Fehler {type(e).__name__}: {e}")
            continue
        problems = schemas.errors({k: v for k, v in r.items() if k != "part_results"}, "analysis_result")
        results.save(r)
        cost = r["usage"]["cost_usd"]
        stats["cost_usd"] = round(stats["cost_usd"] + cost, 6)
        stats["done"].append(pid)
        m = r["fields"]["municipality"]
        parts = f", {len(r['composite']['parts'])} Teile" if r.get("composite") else ""
        warn = f", SCHEMA: {problems[0]}" if problems else ""
        log(f"{tag}: {m['value']} ({m['confidence']:.2f}){parts}, ${cost:.3f}{warn}")
    log(f"Fertig: {len(stats['done'])} neu, {len(stats['skipped'])} aus dem Cache, "
        f"{len(stats['failed'])} fehlgeschlagen, ${stats['cost_usd']:.2f}")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m agent.precompute", description=__doc__.split("\n\n")[0])
    ap.add_argument("photo_ids", nargs="*", help="default: the demo cards (GET /demo)")
    ap.add_argument("--model", default=config.MODEL, help=f"default {config.MODEL}")
    ap.add_argument("--fresh", action="store_true", help="re-run cards that are already cached")
    ap.add_argument("--max-cost", type=float, default=5.0, help="stop starting new cards above this (USD)")
    args = ap.parse_args(argv)
    ids = args.photo_ids or demo_ids()
    if not ids:
        print("Keine Demo-Karten gefunden: data_pipeline hat noch keine demo()-Funktion oder es fehlen "
              "die Daten. Ids direkt angeben: python -m agent.precompute <id> ...", file=sys.stderr)
        return 2
    s = precompute(ids, args.model, args.fresh, args.max_cost, log=lambda m: print(m, file=sys.stderr))
    return 0 if not s["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
