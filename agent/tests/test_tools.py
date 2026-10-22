"""Agent tools: leakage guards, swisstopo cache, final-answer schema and normalisation. No network."""

import copy
import json

import httpx
import pytest

from agent import config, llm
from agent.tools import ToolContext, archive, definitions, run_tool, similar, submit, swisstopo
from agent.tools.base import base_id

FIXTURE_ID = "epics:PK_020566"
IMG = str(config.FIXTURES / "sample.jpg")


@pytest.fixture(autouse=True)
def _cache(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")


def _rec(pid: str, muni: str = "Schwyz") -> dict:
    r = copy.deepcopy(similar.dp.get_record(FIXTURE_ID))
    r["id"], r["municipality"] = pid, muni
    return r


# ---------- similar_images ----------

def test_similar_images_never_leaks_the_query_or_its_crops(monkeypatch):
    query = "stasz:514189"
    seen = {}

    def fake_similar(image_path, k=8, model="best", exclude_ids=(), sources=None, verify=False):
        seen.update(k=k, model=model, exclude_ids=list(exclude_ids), verify=verify)
        # a careless index returns the query, its crops, an excluded survey photo and real neighbours
        ids = [query, "stasz:514189#1", "stasz:514189#2", "lubis:7", "stasz:1", "stasz:2#1", "stasz:3"]
        return [{"id": i, "score": 0.9 - n * 0.01, "record": _rec(i), "verified": n < 2, "inliers": 50 - n}
                for n, i in enumerate(ids)]

    monkeypatch.setattr(similar.dp, "similar_images", fake_similar)
    ctx = ToolContext(photo_id=query, image_path=IMG, exclude_ids=[query, "lubis:7"])
    out = similar.run(ctx, k=8, sources=None)
    ids = [h["id"] for h in out.data["hits"]]
    assert ids == ["stasz:1", "stasz:2#1", "stasz:3"]
    assert not {base_id(i) for i in ids} & {base_id(query), "lubis:7"}
    # the real api gets the strongest settings and the exclusions
    assert seen["model"] == "fused" and seen["verify"] is True
    assert query in seen["exclude_ids"] and "lubis:7" in seen["exclude_ids"]
    # top 3 come back as labelled thumbnails, and the content never mentions the query id
    assert [b["type"] for b in out.images] == ["text", "image"] * 3
    blob = json.dumps(out.content("note"))
    assert query not in blob
    assert "Treffer" in out.summary


def test_similar_images_drops_crop_whose_parent_is_the_query(monkeypatch):
    def fake_similar(image_path, k=8, model="best", exclude_ids=(), sources=None, verify=False):
        r = _rec("stasz:999")
        r["parent_id"] = "stasz:514189"
        return [{"id": "stasz:999", "score": 0.9, "record": r}]

    monkeypatch.setattr(similar.dp, "similar_images", fake_similar)
    out = similar.run(ToolContext("stasz:514189#1", IMG, ["stasz:514189#1"]), k=8, sources=None)
    assert out.data["hits"] == []


def test_similar_images_stub_has_no_verify_and_excludes_self():
    # the stub returns only the fixture record, which is the query itself here
    assert not similar._supports_verify()
    out = similar.run(ToolContext(FIXTURE_ID, IMG, [FIXTURE_ID]), k=8, sources=None)
    assert out.data["hits"] == [] and out.summary == "Keine ähnlichen Bilder gefunden"


def test_similar_images_k_is_clamped(monkeypatch):
    got = {}
    monkeypatch.setattr(similar.dp, "similar_images",
                        lambda image_path, k=8, **kw: got.update(k=k) or [])
    similar.run(ToolContext(None, IMG, []), k=500, sources=None)
    assert got["k"] == similar.MAX_K


# ---------- archive_lookup ----------

def test_archive_lookup_excludes_the_query():
    out = archive.run(ToolContext(FIXTURE_ID, IMG, [FIXTURE_ID]), place="Brunnen")
    assert out.data["records"] == []
    out = archive.run(ToolContext("stasz:1", IMG, ["stasz:1"]), place="Brunnen")
    assert [r["id"] for r in out.data["records"]] == [FIXTURE_ID]
    assert out.summary.startswith("1 datierte Archivkarten zu Brunnen")


def test_archive_lookup_needs_a_filter():
    out = archive.run(ToolContext(None, IMG, []))
    assert out.is_error


# ---------- swisstopo_search ----------

SEARCH_BODY = {"results": [{"attrs": {
    "label": "<i>Hauptgipfel</i> <b>Gitschen</b> (UR) - Isenthal", "lat": 46.8771, "lon": 8.5751,
    "objectclass": "TLM_NAME_PKT", "origin": "gazetteer", "x": 1192410.5, "y": 2686631.0}}]}


class _Resp:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_swisstopo_cache_hit_does_not_call_the_network_twice(monkeypatch):
    calls = []
    monkeypatch.setattr(swisstopo.httpx, "get", lambda url, **kw: calls.append(url) or _Resp(SEARCH_BODY))
    ctx = ToolContext(None, IMG, [])
    a = swisstopo.run(ctx, text="Gitschen")
    b = swisstopo.run(ctx, text="Gitschen")
    assert len(calls) == 1 and a.data == b.data
    assert "type=locations" in calls[0] and "searchText=Gitschen" in calls[0]
    hit = a.data["results"][0]
    assert hit["name"] == "Hauptgipfel Gitschen (UR) - Isenthal" and hit["canton"] == "UR"
    assert (hit["E_LV95"], hit["N_LV95"]) == (2686631, 1192410)  # x is northing, y is easting
    assert list((config.CACHE_DIR / "swisstopo").glob("*.json"))
    swisstopo.run(ctx, text="Mythen")
    assert len(calls) == 2


def test_swisstopo_drops_far_fuzzy_matches_and_hints_a_spelling(monkeypatch):
    far = {"results": [{"attrs": {"label": "Ort <b>L'Aurore</b> (VD) - Grandson", "lat": 46.8, "lon": 6.6,
                                  "origin": "gazetteer", "x": 1185037.0, "y": 2539092.0}}]}
    monkeypatch.setattr(swisstopo.httpx, "get", lambda url, **kw: _Resp(far if "Urirotstock" in url else SEARCH_BODY))
    ctx = ToolContext(photo_id="x", image_path="x.jpg", exclude_ids=["x"])
    miss = swisstopo.run(ctx, text="Urirotstock")
    assert miss.data["results"] == [] and miss.data["far_results_dropped"] == 1 and "Uri Rotstock" in miss.data["hint"]
    assert "andere Schreibweise" in miss.summary
    hit = swisstopo.run(ctx, text="Gitschen")
    assert hit.data["results"][0]["km_from_schwyz"] < 60 and "hint" not in hit.data


def test_swisstopo_network_error_is_a_tool_error(monkeypatch):
    def down(url, **kw):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(swisstopo.httpx, "get", down)
    out = swisstopo.run(ToolContext(None, IMG, []), text="Gitschen")
    assert out.is_error and "nicht erreichbar" in out.summary
    assert not list((config.CACHE_DIR / "swisstopo").glob("*.json")) if (config.CACHE_DIR / "swisstopo").exists() else True


def test_swisstopo_rate_limit_waits(monkeypatch):
    slept = []
    monkeypatch.setattr(swisstopo.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(swisstopo, "_calls", swisstopo.deque([swisstopo.time.monotonic()] * swisstopo.RATE_PER_MIN))
    swisstopo._wait_for_slot()
    assert slept and 0 < slept[0] <= 60.1


# ---------- registry ----------

def test_run_tool_survives_errors(monkeypatch):
    out, ms = run_tool("nope", {}, ToolContext(None, IMG, []))
    assert out.is_error
    monkeypatch.setattr(similar.dp, "similar_images", lambda *a, **k: 1 / 0)
    out, ms = run_tool("similar_images", {"k": 3, "sources": None}, ToolContext(None, IMG, []))
    assert out.is_error and "ZeroDivisionError" in out.data["error"]


def _walk(schema):
    if isinstance(schema, dict):
        yield schema
        for v in schema.values():
            yield from _walk(v)
    elif isinstance(schema, list):
        for v in schema:
            yield from _walk(v)


def test_tool_definitions_are_strict_and_stable():
    names = submit.municipalities()
    defs = definitions(names)
    assert json.dumps(defs, sort_keys=False) == json.dumps(definitions(names), sort_keys=False)
    for d in defs:
        assert d["strict"] is (d["name"] != "submit_result")  # submit_result is too large for strict mode
        for node in _walk(d["input_schema"]):
            if node.get("type") == "object" or (isinstance(node.get("type"), list) and "object" in node["type"]):
                assert node.get("additionalProperties") is False, d["name"]
                assert set(node["required"]) == set(node["properties"]), d["name"]
    muni = defs[-1]["input_schema"]["properties"]["municipality"]["properties"]["value"]["anyOf"]
    assert "Ingenbohl" in muni[0]["enum"] and "Küssnacht (SZ)" in muni[0]["enum"] and muni[1] == {"type": "null"}
    assert len(names) == 30


# ---------- submit_result normalisation ----------

def test_normalize_repairs_input():
    names = submit.municipalities()
    body = submit.normalize({
        "municipality": {"value": "küssnacht", "confidence": 1.4,
                         "evidence": [{"kind": "bogus", "summary": "Kirche", "supports": True}, {"summary": ""}]},
        "decade": {"value": 1913, "confidence": -1, "evidence": []},
        "year_range": {"value": {"from": 1920, "to": 1905}, "confidence": 0.5, "evidence": []},
        "buildings": {"value": "Rathaus", "confidence": 0.5, "evidence": []},
    }, names)
    f = body["fields"]
    assert f["municipality"]["value"] == "Küssnacht (SZ)" and f["municipality"]["confidence"] == 1.0
    assert f["municipality"]["evidence"] == [{"kind": "visual_cue", "summary": "Kirche", "supports": True}]
    assert f["decade"] == {"value": 1910, "confidence": 0.0, "evidence": []}
    assert f["year_range"]["value"] == {"from": 1905, "to": 1920}
    assert f["buildings"]["value"] == ["Rathaus"]
    assert f["place"] == {"value": None, "confidence": 0.0, "evidence": []}
    assert body["estimates"]["year"] == 1912


def test_cost_usd():
    usage = {"input_tokens": 1000, "output_tokens": 1000, "cache_read_input_tokens": 10000,
             "cache_creation_input_tokens": 2000}
    expected = (1000 * 4 + 2000 * 4 * 1.25 + 10000 * 4 * 0.1 + 1000 * 20) / 1e6
    assert llm.cost_usd("claude-opus-5-5", usage) == pytest.approx(expected)
    assert llm.price("unknown-model") == max([*config.PRICES.values(), *llm.EXTRA_PRICES.values()])


# ---------- terrain_check ----------

from agent.tools import terrain


def _profile(heights, step=1000.0):
    return [{"dist": i * step, "alts": {"COMB": h}, "easting": 2690000 + i * step, "northing": 1200000}
            for i, h in enumerate(heights)]


def test_line_of_sight_free_and_blocked():
    free = terrain.line_of_sight(_profile([440, 450, 460, 480, 2500]))
    assert free["visible"] is True and "blocked_at" not in free
    blocked = terrain.line_of_sight(_profile([440, 450, 1800, 480, 2500]))
    assert blocked["visible"] is False and blocked["blocked_at"]["height_m"] == 1800
    assert blocked["blocked_at"]["dist_km"] == 2.0


def test_earth_curvature_hides_a_low_far_target():
    # flat lake level, a 20 m target 60 km away sinks below the horizon of a 2 m eye
    pts = _profile([434] * 60 + [454])
    assert terrain.line_of_sight(pts)["visible"] is False


def test_terrain_check_tool_uses_the_cache_and_rejects_bad_distances(monkeypatch):
    calls = []
    body = _profile([440, 450, 460, 2500], step=3000.0)
    monkeypatch.setattr(swisstopo.httpx, "get", lambda url, **kw: calls.append(url) or _Resp(body))
    ctx = ToolContext(photo_id="x", image_path="x.jpg", exclude_ids=["x"])
    args = dict(from_lat=46.995, from_lon=8.605, to_lat=47.0298, to_lon=8.6838)
    a = terrain.run(ctx, **args)
    b = terrain.run(ctx, **args)
    assert not a.is_error and a.data["visible"] is True and a.data["direction"] == "NO"
    assert "Sichtlinie frei" in a.summary and len(calls) == 1 and b.data == a.data
    too_close = terrain.run(ctx, from_lat=47.0, from_lon=8.6, to_lat=47.0, to_lon=8.6)
    assert too_close.is_error and calls == calls[:1]
