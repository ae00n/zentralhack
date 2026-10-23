import json

from agent import config, llm, loop, precompute, results


def _fixture(pid, model):
    r = json.loads((config.FIXTURES / "analysis_result.json").read_text(encoding="utf-8"))
    return {**r, "photo_id": pid, "model": model}


def test_precompute_caches_skips_and_stops_on_missing_key(monkeypatch):
    calls = []

    def analyze(pid, model=config.MODEL, **kw):
        calls.append(pid)
        if pid == "c":
            raise llm.MissingKey("no key")
        if pid == "b":
            raise RuntimeError("boom")
        return _fixture(pid, model)

    monkeypatch.setattr(loop, "analyze", analyze)
    s = precompute.precompute(["a", "b", "c", "d"], log=lambda m: None)
    assert s["done"] == ["a"] and s["failed"] == ["b", "c", "d"] and calls == ["a", "b", "c"]
    assert results.load("a")["photo_id"] == "a"
    # second run: "a" comes from the cache, no new call
    calls.clear()
    s = precompute.precompute(["a"], log=lambda m: None)
    assert s["skipped"] == ["a"] and calls == []


def test_demo_ids_in_stub_mode():
    assert precompute.demo_ids() == ["epics:PK_020566"]


def test_parallel_batch_reports_cost_after_10_and_respects_the_cap(monkeypatch):
    monkeypatch.setattr(loop, "analyze", lambda pid, model=config.MODEL, **kw: _fixture(pid, model))
    lines = []
    ids = [f"challenge:SG.CIV.17.{i}" for i in range(1, 15)]
    s = precompute.precompute(ids, workers=4, max_cost=100, log=lines.append)
    assert len(s["done"]) == 14 and not s["failed"]
    report = [l for l in lines if l.startswith("== Kosten nach 10 Fotos")]
    assert len(report) == 1 and "hochgerechnet auf alle 14" in report[0]
    # the fixture costs $0.085 per photo: a $0.30 cap stops after a few, the rest is reported as not started
    s = precompute.precompute([f"x:{i}" for i in range(10)], workers=2, max_cost=0.3, log=lines.append)
    assert 0 < len(s["done"]) < 10 and len(s["done"]) + len(s["failed"]) == 10
