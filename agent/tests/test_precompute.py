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
