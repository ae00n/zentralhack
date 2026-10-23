import json

from agent import results, schemas
from agent.config import FIXTURES
from agent.loop import analyze


def test_fixture_is_valid():
    fixture = json.loads((FIXTURES / "analysis_result.json").read_text(encoding="utf-8"))
    assert schemas.errors(fixture, "analysis_result") == []


def test_analyze_signature_and_cache_roundtrip(monkeypatch):
    from agent import config

    monkeypatch.setattr(config, "FAKE", True)
    events = []
    r = analyze("stasz:1", on_event=events.append)
    assert r["photo_id"] == "stasz:1" and events
    schemas.validate(r, "analysis_result")
    results.save(r)
    assert results.load("stasz:1")["photo_id"] == "stasz:1"
    assert results.load("stasz:1", model="other-model") is None


def test_a_new_run_keeps_the_previous_result_in_the_history():
    fixture = json.loads((FIXTURES / "analysis_result.json").read_text(encoding="utf-8"))
    first = {**fixture, "photo_id": "stasz:7", "run_id": "r1", "created_at": "2026-10-23T10:00:00Z"}
    results.save(first)
    results.save({**first, "review": {"status": "bestaetigt"}})  # same run: no history entry
    assert [r["run_id"] for r in results.history("stasz:7")] == ["r1"]
    results.save({**first, "run_id": "r2", "created_at": "2026-10-23T11:00:00Z"})
    assert [r["run_id"] for r in results.history("stasz:7")] == ["r1", "r2"]
    assert results.load("stasz:7")["run_id"] == "r2"
    assert len(results.all_results()) == 1  # history files are not results
