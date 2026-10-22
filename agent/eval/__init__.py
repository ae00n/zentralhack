"""Eval runner, similarity-only baseline and EvalSummary (CONTRACTS section 7).

    python -m agent.eval.runner --limit 50 --model claude-haiku-5-5   # cheap debug pass
    python -m agent.eval.runner                                       # full run with config.MODEL
    python -m agent.eval.runner --baseline-only                       # free, no Claude calls
    python -m agent.eval.runner --summary-only                        # rescore cached results
"""
