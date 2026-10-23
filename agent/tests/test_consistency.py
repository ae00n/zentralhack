import itertools
import json
import threading
import time

from agent import config, consistency, loop, precompute, results
from agent.server import catalogue, export

_seq = itertools.count()


def run(pid="challenge:1", locality="Seewen", municipality="Schwyz", overall=0.95, cost=0.1):
    """A fake AnalysisResult with its own run_id and a later created_at for every call."""
    r = json.loads((config.FIXTURES / "analysis_result.json").read_text(encoding="utf-8"))
    i = next(_seq)
    r.update(photo_id=pid, run_id=f"run-{i:04d}", created_at=f"2026-10-23T00:{i // 60 % 60:02d}:{i % 60:02d}Z",
             overall_confidence=overall, needs_review=overall < 0.9, status="done" if overall >= 0.9 else
             "needs_review", confidence_explanation="Gemeinde durch 3 unabhängige Quellen gestützt.",
             usage={**r["usage"], "cost_usd": cost})
    r["fields"]["locality"]["value"] = locality
    r["fields"]["municipality"]["value"] = municipality
    return r


def test_agreement_keeps_the_most_confident_run():
    a, b = run(overall=0.85), run(locality="seewen", municipality="SCHWYZ", overall=0.95)
    kept = consistency.combine([a, b])
    assert kept["run_id"] == b["run_id"] and kept["overall_confidence"] == 0.95 and not kept["needs_review"]
    c = kept["consistency"]
    assert c["runs"] == 2 and c["agree"] is True and [v["overall"] for v in c["values"]] == [0.85, 0.95]
    assert kept["confidence_explanation"].endswith(" In 2 unabhängigen Analysen übereinstimmend.")
    assert "consistency" not in b  # the input runs stay untouched


def test_disagreement_caps_and_needs_review():
    a, b = run(locality=None, municipality="Schwyz", overall=0.95), run(locality=None, municipality="Steinen",
                                                                        overall=0.7)
    kept = consistency.combine([a, b])
    assert kept["run_id"] == a["run_id"]
    assert kept["overall_confidence"] == 0.6 and kept["needs_review"] is True and kept["status"] == "needs_review"
    assert kept["consistency"]["agree"] is False
    assert kept["confidence_explanation"].endswith(
        " Zwei unabhängige Analysen nennen verschiedene Orte (Schwyz / Steinen); Prüfung nötig.")


def test_none_counts_as_a_value():
    assert consistency.check([run(locality=None), run(locality=None)])["agree"] is True
    assert consistency.check([run(locality=None), run(locality="Seewen")])["agree"] is False
    single = run()
    assert consistency.combine([single]) is single


def test_from_history_uses_cached_runs_only():
    pid = "challenge:h"
    assert consistency.from_history(pid) is None
    results.save(run(pid, municipality="Schwyz"))
    assert consistency.from_history(pid) is None  # one run only
    results.save(run(pid, municipality="Steinen"))
    c = consistency.from_history(pid)
    assert c["runs"] == 2 and c["agree"] is False
    assert [v["municipality"] for v in c["values"]] == ["Schwyz", "Steinen"]
    results.save(run(pid, municipality="steinen"))
    assert consistency.from_history(pid)["agree"] is True
    assert consistency.from_history(pid, last=3)["agree"] is False


def test_precompute_runs_2_counts_cost_and_keeps_all_runs_in_history(monkeypatch):
    overalls = iter([0.7, 0.95, 0.95, 0.8])
    places = iter(["Schwyz", "Schwyz", "Schwyz", "Steinen"])
    calls = []

    def analyze(pid, model=config.MODEL, **kw):
        calls.append(pid)
        return run(pid, municipality=next(places), overall=next(overalls), cost=0.1)

    monkeypatch.setattr(loop, "analyze", analyze)
    lines = []
    s = precompute.precompute(["p:1", "p:2"], runs=2, log=lines.append)
    assert calls == ["p:1", "p:1", "p:2", "p:2"]
    assert s["done"] == ["p:1", "p:2"] and abs(s["cost_usd"] - 0.4) < 1e-9
    one, two = results.load("p:1"), results.load("p:2")
    assert one["overall_confidence"] == 0.95 and one["consistency"]["agree"] is True and not one["needs_review"]
    assert two["overall_confidence"] == 0.6 and two["needs_review"] and two["consistency"]["agree"] is False
    for pid, kept in (("p:1", one), ("p:2", two)):
        hist = results.history(pid)
        assert len(hist) == 2 and hist[-1]["run_id"] == kept["run_id"] and "consistency" in hist[-1]
    assert any("INSTABIL" in l for l in lines)
    # export: Pruefung_noetig is ja on disagreement
    assert export.row(two, None)["Pruefung_noetig"] == "ja"
    # resumable: both are cached now
    calls.clear()
    assert precompute.precompute(["p:1", "p:2"], runs=2, log=lines.append)["skipped"] == ["p:1", "p:2"]
    assert calls == []


def test_cost_cap_counts_every_run(monkeypatch):
    monkeypatch.setattr(loop, "analyze", lambda pid, model=config.MODEL, **kw: run(pid, cost=0.1))
    # $0.20 per photo with 2 runs: a $0.45 cap allows 2 photos, a third would pass the cap
    s = precompute.precompute([f"x:{i}" for i in range(6)], runs=2, max_cost=0.45, log=lambda m: None)
    assert s["done"] == ["x:0", "x:1"] and abs(s["cost_usd"] - 0.4) < 1e-9 and len(s["failed"]) == 4


def test_export_needs_review_on_disagreement_only():
    r = run(overall=0.95)
    assert export.row(r, None)["Pruefung_noetig"] == "nein"
    r["consistency"] = {"runs": 2, "agree": True, "values": []}
    assert export.row(r, None)["Pruefung_noetig"] == "nein"
    r["consistency"]["agree"] = False
    assert export.row(r, None)["Pruefung_noetig"] == "ja"


SESSIONS = {"s:1": ["s:3"], "s:3": ["s:1", "s:5"], "s:5": ["s:3"], "s:2": [], "s:4": ["s:6", "other:9"],
            "s:6": ["s:4"]}


def _records(monkeypatch):
    monkeypatch.setattr(catalogue, "get_record",
                        lambda pid: {"id": pid, "raw": {"session": SESSIONS.get(pid, [])}} if pid in SESSIONS
                        else None)


def test_sessions_group_in_order_of_first_appearance(monkeypatch):
    _records(monkeypatch)
    ids = ["s:1", "s:2", "s:3", "s:4", "s:5", "s:6", "s:7"]
    assert precompute.sessions(ids) == [["s:1", "s:3", "s:5"], ["s:2"], ["s:4", "s:6"], ["s:7"]]
    # restricted to the ids being run: without s:3, s:1 and s:5 are not connected
    assert precompute.sessions(["s:5", "s:1"]) == [["s:5"], ["s:1"]]


def test_session_siblings_run_one_after_another_in_one_worker(monkeypatch):
    _records(monkeypatch)
    events, lock = [], threading.Lock()

    def analyze(pid, model=config.MODEL, **kw):
        with lock:
            events.append(("start", pid, threading.get_ident()))
        time.sleep(0.02)
        # a later sibling must see the earlier sibling's result already cached
        seen = [sid for sid in SESSIONS.get(pid, []) if results.load(sid)]
        with lock:
            events.append(("end", pid, threading.get_ident(), tuple(seen)))
        return run(pid)

    monkeypatch.setattr(loop, "analyze", analyze)
    s = precompute.precompute(["s:1", "s:2", "s:3", "s:4", "s:5", "s:6"], workers=4, runs=2, max_cost=100,
                              log=lambda m: None)
    assert sorted(s["done"]) == ["s:1", "s:2", "s:3", "s:4", "s:5", "s:6"]
    starts = [e for e in events if e[0] == "start"]
    session = [e for e in starts if e[1] in ("s:1", "s:3", "s:5")]
    assert [e[1] for e in session] == ["s:1", "s:1", "s:3", "s:3", "s:5", "s:5"]  # both runs before the sibling
    assert len({e[2] for e in session}) == 1  # one worker
    ends = {e[1]: e[3] for e in events if e[0] == "end"}
    assert "s:1" in ends["s:3"] and "s:3" in ends["s:5"]
    # the sessions ran in parallel: more than one worker thread was used
    assert len({e[2] for e in starts}) > 1


def test_report_shows_stable_and_unstable_chips():
    from agent import report

    results.save(consistency.combine([run("r:1"), run("r:1")]))
    results.save(consistency.combine([run("r:2", municipality="Schwyz"), run("r:2", municipality="Steinen")]))
    page = report.build(["r:1", "r:2"], "Test")
    assert page.count('class="chip stab"') == 1 and page.count('class="chip unstable"') == 1
    assert 'data-f="unstable">Instabil</button>' in page
