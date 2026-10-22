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
