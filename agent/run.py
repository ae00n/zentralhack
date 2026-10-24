"""CLI: analyse photos with the agent loop.

    python -m agent.run <photo_id> [<photo_id> ...] [--model M] [--eval] [--save] [--quiet]
    python -m agent.run --image path/to/upload.jpg

Prints each AnalysisResult as JSON on stdout (trace lines and the cost line go to stderr), validates it
against contracts/schemas/analysis_result.schema.json, and with --save writes it to the results cache.
Exit code 0 when all results are valid, 1 on an invalid result, 2 on a setup error (e.g. no API key).
"""

import argparse
import json
import sys

from . import config, llm, results, schemas


def _print_event(item: dict) -> None:
    if item["type"] == "tool_call":
        line = f"  [{item['step']}] {item['tool']} {json.dumps(item.get('input') or {}, ensure_ascii=False)}: {item.get('output_summary')} ({item.get('ms')} ms)"
    else:
        text = (item.get("text") or "").replace("\n", " ")
        line = f"  [{item['step']}] {item['type']}: {text[:300]}"
    print(line, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m agent.run", description=__doc__.split("\n\n")[0])
    ap.add_argument("photo_ids", nargs="*", help="archive ids, e.g. stasz:514189")
    ap.add_argument("--image", help="analyse an uploaded image file instead of an archive id")
    ap.add_argument("--model", default=config.MODEL, help=f"default {config.MODEL}")
    ap.add_argument("--eval", action="store_true",
                    help="eval hygiene: also hide eval_exclusions(photo_id) from the tools")
    ap.add_argument("--save", action="store_true", help="write results to the results cache")
    ap.add_argument("--quiet", action="store_true", help="no trace lines on stderr")
    args = ap.parse_args(argv)
    if not args.photo_ids and not args.image:
        ap.error("give at least one photo_id or --image")

    try:
        llm.make_client()  # fail fast, before loading any model or index
        llm.check_session_budget()
    except (llm.MissingKey, llm.SessionBudgetExceeded) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    from .loop import analyze  # imported late so a missing key fails before data_pipeline loads

    jobs = [(pid, None) for pid in args.photo_ids] + ([(None, args.image)] if args.image else [])
    exit_code, total = 0, 0.0
    for pid, img in jobs:
        print(f"== {pid or img} ({args.model})", file=sys.stderr, flush=True)
        exclude = []
        if args.eval and pid:
            from data_pipeline.dating import eval_exclusions

            exclude = eval_exclusions(pid)
        try:
            r = analyze(pid, img, model=args.model, exclude_ids=exclude,
                        on_event=None if args.quiet else _print_event)
        except llm.SessionBudgetExceeded as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        except (ValueError, FileNotFoundError) as e:
            print(f"error: {e}", file=sys.stderr)
            exit_code = 2
            continue
        errs = schemas.errors(r, "analysis_result")
        print(json.dumps(r, ensure_ascii=False, indent=2))
        u = r["usage"]
        total += u["cost_usd"]
        f = r["fields"]
        def show(n):
            v = f[n]["value"]
            v = ", ".join(v) if isinstance(v, list) else v
            return f"{v or 'nicht bestimmbar'} ({f[n]['confidence']:.2f})"
        print("result: " + " | ".join(f"{label} {show(n)}" for n, label in (
            ("locality", "Ortschaft"), ("municipality", "Gemeinde"), ("buildings", "Gebäude"),
            ("landscape_features", "See/Fluss/Berg"), ("street", "Strasse"))), file=sys.stderr)
        print(f"overall: {r['overall_confidence']:.2f}, {'Prüfung nötig' if r['needs_review'] else 'akzeptiert'}: "
              f"{r.get('confidence_explanation')}", file=sys.stderr)
        print(f"cost: ${u['cost_usd']:.4f} (in {u['input_tokens']} tok, cache read {u.get('cache_read_input_tokens', 0)}, "
              f"out {u['output_tokens']} tok, {u.get('api_calls', 0)} calls{', BUDGET HIT' if u.get('budget_hit') else ''}); "
              f"ledger total ${llm.ledger_total():.2f} of ${config.SESSION_BUDGET_USD:.0f}", file=sys.stderr)
        if errs:
            print("INVALID analysis_result: " + "; ".join(errs[:5]), file=sys.stderr)
            exit_code = 1
        elif args.save:
            print(f"saved {results.save(r)}", file=sys.stderr)
    if len(jobs) > 1:
        print(f"total cost this run: ${total:.4f}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
