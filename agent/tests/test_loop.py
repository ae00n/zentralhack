"""Agent loop with a scripted fake client (stub data_pipeline, no network, no key, no cost)."""

import json
from types import SimpleNamespace

import pytest

from agent import config, llm, loop, prompts, schemas
from agent.tools import submit

SUBMIT = submit.NAME

# ---------- a scripted stand-in for anthropic.Anthropic ----------


FIXTURE_ID = "epics:PK_020566"  # the stub record (contracts/fixtures/photo_record.json)


def text(t: str):
    return SimpleNamespace(type="text", text=t)


def thinking(t: str):
    return SimpleNamespace(type="thinking", thinking=t, signature="sig")


def tool_use(name: str, inp: dict, id: str):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=id)


def response(*content, stop="tool_use", input_tokens=2000, output_tokens=300, cache_read=0, cache_write=0,
             model="claude-opus-5-5"):
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                            cache_read_input_tokens=cache_read, cache_creation_input_tokens=cache_write)
    return SimpleNamespace(content=list(content), stop_reason=stop, usage=usage, model=model)


def ev(kind="visual_cue", summary="Kirchturm mit Spitzhelm sichtbar", supports=True):
    return {"kind": kind, "summary": summary, "ref_id": None, "score": None, "supports": supports}


def submit_input(muni="Ingenbohl", muni_conf=0.82, decade=1900, decade_conf=0.7):
    return {
        "municipality": {"value": muni, "confidence": muni_conf, "evidence": [ev("text_on_card", "Aufdruck nennt Urirotstock")]},
        "place": {"value": "Seeufer bei Brunnen", "confidence": 0.6, "evidence": [ev()]},
        "buildings": {"value": [], "confidence": 0.9, "evidence": []},
        "landscape_features": {"value": ["Urirotstock", "Gitschen"], "confidence": 0.9, "evidence": [ev()]},
        "decade": {"value": decade, "confidence": decade_conf, "evidence": [ev()]},
        "year_range": {"value": {"from": 1898, "to": 1907}, "confidence": 0.7, "evidence": [ev()]},
        "coordinates": {"value": {"lat": 46.98, "lon": 8.61, "radius_m": 800}, "confidence": 0.6, "evidence": []},
        "year_best": 1903,
        "place_name_printed": True,
        "overall_confidence": 0.76,
        "rejected_hypotheses": [{"field": "municipality", "value": "Sisikon", "reason": "Gitschen wäre näher."}],
    }


class FakeClient:
    """Pops one scripted response per create() call and records every request."""

    def __init__(self, responses, errors=()):
        self.responses = list(responses)
        self.errors = list(errors)  # exceptions raised by the first calls, before any response
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create_plain)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create_beta))

    def _record(self, kind, kw):
        self.calls.append({"kind": kind, **kw, "messages": list(kw["messages"])})
        if self.errors:
            raise self.errors.pop(0)
        if not self.responses:
            raise AssertionError("FakeClient ran out of scripted responses")
        return self.responses.pop(0)

    def _create_plain(self, **kw):
        return self._record("plain", kw)

    def _create_beta(self, **kw):
        return self._record("beta", kw)


# ---------- tests ----------


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_degraded", False)
    monkeypatch.setattr(config, "FAKE", False)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")


def _run(monkeypatch, responses, errors=(), **kw):
    fake = FakeClient(responses, errors)
    monkeypatch.setattr(llm, "make_client", lambda: fake)
    events = []
    r = loop.analyze(kw.pop("photo_id", FIXTURE_ID), on_event=events.append, **kw)
    return r, fake, events


def _ledger_lines():
    p = llm.ledger_path()
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_scripted_run_is_valid(monkeypatch):
    r, fake, events = _run(monkeypatch, [
        response(text("Zwei Hypothesen: Brunnen oder Sisikon."), tool_use("similar_images", {"k": 8, "sources": None}, "t1")),
        response(thinking("Vergleiche Treffer."), tool_use(SUBMIT, submit_input(), "t2"), stop="tool_use"),
    ])
    schemas.validate(r, "analysis_result")
    assert r["photo_id"] == FIXTURE_ID and r["model"] == config.MODEL and r["composite"] is None
    assert r["status"] == "done" and r["needs_review"] is False
    assert r["fields"]["municipality"]["value"] == "Ingenbohl"
    assert r["fields"]["decade"]["value"] == 1900
    assert r["estimates"] == {"year": 1903, "place_name_printed": True}
    assert r["rejected_hypotheses"][0]["value"] == "Sisikon"

    # trace: date_hints step, thought, similar_images call, final; all emitted live. Thinking notes are
    # left out (the API writes them in English).
    types = [(t["type"], t.get("tool")) for t in r["trace"]]
    assert types == [("tool_call", "date_hints"), ("thought", None), ("tool_call", "similar_images"),
                     ("final", None)]
    assert events == r["trace"]
    assert [t["step"] for t in r["trace"]] == [1, 2, 3, 4]
    sim = r["trace"][2]
    assert sim["input"] == {"k": 8, "sources": None} and isinstance(sim["output_summary"], str)

    # cost: 2 calls x (2000 in, 300 out) at Opus prices
    expected = 2 * (2000 * 4.0 + 300 * 20.0) / 1e6
    assert r["usage"]["cost_usd"] == pytest.approx(expected)
    assert r["usage"]["input_tokens"] == 4000 and r["usage"]["output_tokens"] == 600
    assert r["usage"]["budget_hit"] is False
    assert len(_ledger_lines()) == 2 and sum(l["cost_usd"] for l in _ledger_lines()) == pytest.approx(expected)


def test_request_shape(monkeypatch):
    _, fake, _ = _run(monkeypatch, [response(tool_use(SUBMIT, submit_input(), "t1"))])
    call = fake.calls[0]
    assert call["kind"] == "beta" and call["fallbacks"] == "default"
    assert llm.FALLBACK_BETA in call["betas"]
    assert call["tool_choice"] == {"type": "auto"}
    assert call["thinking"]["type"] == "adaptive"
    assert "budget_tokens" not in call["thinking"]
    assert call["output_config"] == {"effort": loop.EFFORT}
    assert call["system"][-1]["cache_control"] == {"type": "ephemeral"}
    names = [t["name"] for t in call["tools"]]
    assert names == ["similar_images", "archive_lookup", "swisstopo_search", SUBMIT]
    first = call["messages"][0]["content"]
    assert first[0]["type"] == "image" and first[1]["type"] == "text"  # image first, then text
    assert "Date hints" in first[1]["text"] and "Verlag wehrli" in first[1]["text"]
    assert "Black and white is not evidence of age" in call["system"][0]["text"]
    # no catalogue metadata of the query (title, places, municipality) in the prompt
    assert "Vierwaldstättersee mit Urirotstock" not in first[1]["text"]


def test_haiku_goes_plain_without_fallbacks(monkeypatch):
    r, fake, _ = _run(monkeypatch, [response(tool_use(SUBMIT, submit_input(), "t1"), model="claude-haiku-5-5")],
                      model="claude-haiku-5-5")
    assert fake.calls[0]["kind"] == "plain" and "fallbacks" not in fake.calls[0]
    assert r["usage"]["cost_usd"] == pytest.approx((2000 * 0.10 + 300 * 0.50) / 1e6)


def test_low_confidence_needs_review(monkeypatch):
    r, _, _ = _run(monkeypatch, [response(tool_use(SUBMIT, submit_input(muni_conf=0.3), "t1"))])
    schemas.validate(r, "analysis_result")
    assert r["needs_review"] is True and r["status"] == "needs_review"
    r, _, _ = _run(monkeypatch, [response(tool_use(SUBMIT, submit_input(decade_conf=0.49), "t1"))])
    assert r["needs_review"] is True


def test_budget_guard(monkeypatch):
    monkeypatch.setattr(loop, "PHOTO_BUDGET_USD", 0.001)
    r, fake, _ = _run(monkeypatch, [
        response(tool_use("similar_images", {"k": 8, "sources": None}, "t1")),
        response(tool_use(SUBMIT, submit_input(), "t2")),
    ])
    schemas.validate(r, "analysis_result")
    assert r["usage"]["budget_hit"] is True
    assert r["fields"]["municipality"]["value"] == "Ingenbohl"
    # the tool was not run; the model got a skipped tool_result plus the stop instruction
    assert not [t for t in r["trace"] if t.get("tool") == "similar_images"]
    last_user = fake.calls[1]["messages"][-1]["content"]
    assert last_user[0]["type"] == "tool_result" and last_user[0]["is_error"] is True
    assert last_user[-1] == {"type": "text", "text": prompts.STOP_NOW_BUDGET}


def test_max_steps_then_no_submit(monkeypatch):
    monkeypatch.setattr(loop, "MAX_STEPS", 2)
    r, fake, _ = _run(monkeypatch, [
        response(tool_use("similar_images", {"k": 4, "sources": None}, "t1")),
        response(tool_use("archive_lookup", {"place": "Brunnen", "municipality": None, "year_from": None, "year_to": None}, "t2"),
                 tool_use("similar_images", {"k": 8, "sources": None}, "t3")),
        response(tool_use("similar_images", {"k": 12, "sources": None}, "t4")),  # ignores the stop
    ])
    schemas.validate(r, "analysis_result")
    calls = [t for t in r["trace"] if t["type"] == "tool_call" and t["tool"] != "date_hints"]
    assert len(calls) == 2  # third tool in turn 2 skipped, turn 3 never executed
    assert fake.calls[2]["messages"][-1]["content"][-1]["text"] == prompts.STOP_NOW_STEPS
    assert r["needs_review"] is True and r["status"] == "needs_review"
    assert r["fields"]["municipality"]["confidence"] == 0.0
    assert r["trace"][-1]["type"] == "final"
    assert len(fake.calls) == 3


def test_end_turn_gets_one_nudge(monkeypatch):
    r, fake, _ = _run(monkeypatch, [
        response(text("Ich denke Schwyz."), stop="end_turn"),
        response(tool_use(SUBMIT, submit_input(), "t1")),
    ])
    assert fake.calls[1]["messages"][-1]["content"] == [{"type": "text", "text": prompts.NUDGE_SUBMIT}]
    assert r["status"] == "done"

    r, fake, _ = _run(monkeypatch, [response(text("a"), stop="end_turn"), response(text("b"), stop="end_turn")])
    schemas.validate(r, "analysis_result")
    assert r["needs_review"] is True and len(fake.calls) == 2


def test_refusal_returns_review_result(monkeypatch):
    r, _, _ = _run(monkeypatch, [response(stop="refusal")])
    schemas.validate(r, "analysis_result")
    assert r["needs_review"] is True


def test_session_budget_hard_stop(monkeypatch):
    llm.record({"cost_usd": config.SESSION_BUDGET_USD + 0.01})
    fake = FakeClient([response(tool_use(SUBMIT, submit_input(), "t1"))])
    monkeypatch.setattr(llm, "make_client", lambda: fake)
    with pytest.raises(llm.SessionBudgetExceeded):
        loop.analyze(FIXTURE_ID)
    assert fake.calls == []


def test_missing_key_fails_before_any_call(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(llm.MissingKey):
        loop.analyze(FIXTURE_ID)


def test_strict_schema_rejection_retries_plain(monkeypatch):
    err = type("BadRequest", (Exception,), {"status_code": 400})("tools.3.input_schema: strict mode schema too complex")
    r, fake, _ = _run(monkeypatch, [response(tool_use(SUBMIT, submit_input(), "t1"))], errors=[err])
    assert [c["kind"] for c in fake.calls] == ["beta", "plain"]
    assert all("strict" not in t for t in fake.calls[1]["tools"])
    assert r["status"] == "done"


def test_upload_image(monkeypatch):
    img = str(config.FIXTURES / "sample.jpg")
    r, fake, _ = _run(monkeypatch, [
        response(tool_use("similar_images", {"k": 8, "sources": None}, "t1")),
        response(tool_use(SUBMIT, submit_input(), "t2")),
    ], photo_id=None, image_path=img)
    schemas.validate(r, "analysis_result")
    assert r["photo_id"].startswith("upload:")
    # an upload is not an archive card, so the stub's fixture record may come back as a neighbour
    tool_result = fake.calls[1]["messages"][-1]["content"][0]
    assert FIXTURE_ID in tool_result["content"][0]["text"]


def test_on_event_errors_do_not_stop_the_run(monkeypatch):
    fake = FakeClient([response(tool_use(SUBMIT, submit_input(), "t1"))])
    monkeypatch.setattr(llm, "make_client", lambda: fake)

    def boom(item):
        raise RuntimeError("client went away")

    r = loop.analyze(FIXTURE_ID, on_event=boom)
    assert r["status"] == "done"


def test_unknown_photo_id(monkeypatch):
    monkeypatch.setattr(llm, "make_client", lambda: FakeClient([]))
    with pytest.raises(ValueError):
        loop.analyze("stasz:does-not-exist")


def test_fake_mode_replays_fixture_without_a_client(monkeypatch):
    monkeypatch.setattr(config, "FAKE", True)
    monkeypatch.setattr(llm, "make_client", lambda: pytest.fail("no client in fake mode"))
    events = []
    r = loop.analyze("stasz:1", on_event=events.append)
    assert r["photo_id"] == "stasz:1" and events
    schemas.validate(r, "analysis_result")


# ---------- composite cards ----------


def _with_crops(monkeypatch, n=2):
    base = loop.dp.get_record(FIXTURE_ID)
    crops = {f"{FIXTURE_ID}#{i}": {**base, "id": f"{FIXTURE_ID}#{i}", "parent_id": FIXTURE_ID,
                                   "crop_bbox": [0, 0, 10, 10]} for i in range(1, n + 1)}
    monkeypatch.setattr(loop.dp, "get_record", lambda pid: crops.get(pid) or (base if pid == FIXTURE_ID else None))


def test_composite_card_runs_each_part_and_parent_takes_the_most_confident(monkeypatch):
    from agent import results

    _with_crops(monkeypatch)
    weak = {**submit_input(muni="Schwyz", muni_conf=0.4), "overall_confidence": 0.4}
    r, fake, events = _run(monkeypatch, [
        response(tool_use(SUBMIT, weak, "a1")),
        response(tool_use(SUBMIT, submit_input(), "b1")),
    ])
    assert len(fake.calls) == 2
    assert r["composite"] == {"is_composite": True, "parts": [f"{FIXTURE_ID}#1", f"{FIXTURE_ID}#2"]}
    assert r["photo_id"] == FIXTURE_ID and r["fields"]["municipality"]["value"] == "Ingenbohl"
    assert [p["fields"]["municipality"]["value"] for p in r["part_results"]] == ["Schwyz", "Ingenbohl"]
    assert r["usage"]["cost_usd"] == round(sum(p["usage"]["cost_usd"] for p in r["part_results"]), 6)
    # one live trace across both parts, numbered through, every part step tagged
    assert [t["step"] for t in r["trace"]] == list(range(1, len(r["trace"]) + 1)) and events == r["trace"]
    assert {t.get("part") for t in r["trace"][:-1]} == {f"{FIXTURE_ID}#1", f"{FIXTURE_ID}#2"}
    assert r["trace"][-1]["type"] == "final" and "Teil 2" in r["trace"][-1]["text"]
    # parts are saved on their own; the parent file lists them but does not embed them
    results.save(r)
    parent = results.load(FIXTURE_ID)
    assert "part_results" not in parent and parent["composite"]["parts"] == r["composite"]["parts"]
    schemas.validate(parent, "analysis_result")
    assert results.load(f"{FIXTURE_ID}#1")["fields"]["municipality"]["value"] == "Schwyz"


def test_a_crop_is_never_split_again(monkeypatch):
    _with_crops(monkeypatch)
    r, fake, _ = _run(monkeypatch, [response(tool_use(SUBMIT, submit_input(), "c1"))], photo_id=f"{FIXTURE_ID}#1")
    assert r["composite"] is None and len(fake.calls) == 1


def test_single_card_without_crops_is_not_composite(monkeypatch):
    r, fake, _ = _run(monkeypatch, [response(tool_use(SUBMIT, submit_input(), "d1"))])
    assert r["composite"] is None and "part_results" not in r
