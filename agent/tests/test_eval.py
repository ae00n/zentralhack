"""Eval runner, baseline and summary on synthetic eval items with a fake analyze (no Claude, no data)."""

import copy
import json
import threading

import pytest

from agent import config, loop, results, schemas
from agent.config import FIXTURES
from agent.eval import baseline as bl
from agent.eval import items as eval_items
from agent.eval import runner
from agent.eval import summary as sm

FIXTURE = json.loads((FIXTURES / "analysis_result.json").read_text(encoding="utf-8"))
MODEL = "claude-haiku-5-5"

ITEMS = [
    {"id": "stasz:1", "subset": "card_exact", "municipality": "Schwyz", "year_from": 1905, "year_to": 1905,
     "approximate": False, "year_is_upper_bound": False},
    {"id": "stasz:2", "subset": "card_exact", "municipality": "Arth", "year_from": 1931, "year_to": 1931,
     "approximate": False, "year_is_upper_bound": False},
    {"id": "stasz:3", "subset": "card_posted", "municipality": "Ingenbohl", "year_from": 1912, "year_to": 1912,
     "approximate": False, "year_is_upper_bound": True},
    {"id": "lubis:4", "subset": "photo_dated", "municipality": "Einsiedeln", "year_from": 1950, "year_to": 1950,
     "approximate": False, "year_is_upper_bound": False},
    {"id": "nb:5", "subset": "photo_dated", "municipality": "Gersau", "year_from": 1900, "year_to": 1900,
     "approximate": False, "year_is_upper_bound": False},
]
TRUTH = {it["id"]: it for it in ITEMS}
NAMES = {"schwyz": "Schwyz", "arth": "Arth", "ingenbohl": "Ingenbohl", "einsiedeln": "Einsiedeln", "gersau": "Gersau"}


def fake_result(photo_id, model=MODEL, municipality="Schwyz", conf=0.9, year_range=(1900, 1910), decade=1900,
                cost=0.01):
    r = copy.deepcopy(FIXTURE)
    r["photo_id"], r["model"] = photo_id, model
    r["fields"]["municipality"]["value"] = municipality
    r["fields"]["municipality"]["confidence"] = conf
    r["fields"]["year_range"]["value"] = {"from": year_range[0], "to": year_range[1]}
    r["fields"]["decade"]["value"] = decade
    r["usage"]["cost_usd"] = cost
    return r


class Calls(list):
    behaviour: dict


@pytest.fixture
def fake_analyze(monkeypatch):
    """Patches loop.analyze; returns the list of photo ids it was called with."""
    calls, lock = Calls(), threading.Lock()
    behaviour = {"fail": set(), "cost": 0.01}

    def analyze(photo_id=None, image_path=None, *, model=config.MODEL, exclude_ids=(), on_event=None):
        with lock:
            calls.append(photo_id)
        if photo_id in behaviour["fail"]:
            raise RuntimeError("boom")
        return fake_result(photo_id, model, municipality=TRUTH[photo_id]["municipality"], cost=behaviour["cost"])

    monkeypatch.setattr(loop, "analyze", analyze)
    monkeypatch.setattr(runner, "_exclusions", lambda photo_id: [])
    calls.behaviour = behaviour
    return calls


def quiet(_msg):
    pass


# ---------- runner ----------

def test_resumable_second_run_calls_analyze_zero_times(fake_analyze):
    s1 = runner.run_agent(ITEMS, model=MODEL, workers=4, log=quiet)
    assert s1["done"] == len(ITEMS) and sorted(fake_analyze) == sorted(TRUTH)
    assert all(results.load(i, model=MODEL) for i in TRUTH)
    fake_analyze.clear()
    s2 = runner.run_agent(ITEMS, model=MODEL, workers=4, log=quiet)
    assert fake_analyze == [] and s2["done"] == 0
    # a different model is not a cache hit
    runner.run_agent(ITEMS[:1], model="claude-opus-5-5", workers=1, log=quiet)
    assert fake_analyze == ["stasz:1"]


def test_failing_item_does_not_stop_the_run(fake_analyze, tmp_results):
    fake_analyze.behaviour["fail"] = {"stasz:2"}
    s = runner.run_agent(ITEMS, model=MODEL, workers=2, log=quiet)
    assert s["done"] == len(ITEMS) - 1
    assert [e["photo_id"] for e in s["errors"]] == ["stasz:2"]
    assert results.load("stasz:2") is None
    assert "stasz:2" in (tmp_results / "eval_errors.jsonl").read_text(encoding="utf-8")
    # the next run retries only the failed item
    fake_analyze.behaviour["fail"] = set()
    fake_analyze.clear()
    runner.run_agent(ITEMS, model=MODEL, workers=2, log=quiet)
    assert fake_analyze == ["stasz:2"]


def test_cost_cap_stops_scheduling(fake_analyze):
    fake_analyze.behaviour["cost"] = 1.0
    s = runner.run_agent(ITEMS, model="some-model", workers=1, max_cost=3.5, log=quiet)
    assert s["budget_stop"] and s["done"] == 3 and len(fake_analyze) == 3
    assert s["not_scheduled"] == 2 and s["spent"] <= 3.5


def test_items_interleave_and_limit(tmp_path):
    p = tmp_path / "eval.jsonl"
    p.write_text("".join(json.dumps(it) + "\n" for it in ITEMS), encoding="utf-8")
    got = eval_items.load(p, limit=3)
    assert [it["subset"] for it in got] == ["card_exact", "card_posted", "photo_dated"]
    assert {it["id"] for it in eval_items.load(p, subsets=["photo_dated"])} == {"lubis:4", "nb:5"}
    assert eval_items.load(tmp_path / "missing.jsonl") == []


# ---------- baseline ----------

def hit(pid, municipality, year=1910):
    return {"id": pid, "score": 0.9,
            "record": {"id": pid, "municipality": municipality, "date": {"year_from": year, "year_to": year}}}


def test_baseline_majority_vote_ignores_query_and_its_crops():
    hits = [hit("stasz:1", "Arth"), hit("stasz:1#2", "Arth"), hit("stasz:1#1", "Arth"),
            hit("a:1", "Schwyz", 1900), hit("a:2", "Ingenbohl"), hit("a:3", None),
            hit("a:4", "Schwyz", 1920), hit("a:5", "Ingenbohl"), hit("a:6", "Gersau"), hit("a:7", "Arth")]
    p = bl.vote("stasz:1", hits)
    assert p["neighbours"] == ["a:1", "a:2", "a:4", "a:5", "a:6"]
    assert "Arth" not in p["votes"]
    # 2 x Schwyz vs 2 x Ingenbohl: the better ranked one (a:1) wins
    assert p["municipality"] == "Schwyz" and p["municipality_confidence"] == 0.4
    assert p["year_low"] == 1900 and p["year_high"] == 1920
    assert bl.vote("stasz:1", [hit("stasz:1#1", "Arth")])["municipality"] is None


def test_baseline_search_passes_leakage_exclusions_and_caches(monkeypatch, tmp_path):
    import data_pipeline as dp
    import data_pipeline.dating as dating

    img = tmp_path / "x.jpg"
    img.write_bytes(b"x")
    seen = []

    def similar_images(image_path, k=8, model="best", exclude_ids=(), sources=None, **kw):
        seen.append({"exclude_ids": list(exclude_ids), "model": model, **kw})
        return [hit("lubis:4", "Arth"), hit("a:1", "Einsiedeln"), hit("a:2", "Einsiedeln")]

    monkeypatch.setattr(dp, "get_record", lambda pid: {"id": pid, "image": {"path": "x.jpg"}})
    monkeypatch.setattr(dp, "image_file", lambda rec: img)
    monkeypatch.setattr(dp, "similar_images", similar_images)
    monkeypatch.setattr(dating, "eval_exclusions", lambda pid: ["lubis:99"])
    preds = bl.run(ITEMS[3:4], model="fused", log=quiet)
    assert seen[0]["exclude_ids"] == ["lubis:4", "lubis:99"] and seen[0]["model"] == "fused"
    assert "verify" not in seen[0]  # stub mode: stub.similar_images has no verify parameter
    assert preds["lubis:4"]["municipality"] == "Einsiedeln"
    assert bl.accuracy(preds, ITEMS) == (1.0, 1)
    bl.run(ITEMS[3:4], model="fused", log=quiet)
    assert len(seen) == 1  # second run is served from baseline.jsonl
    assert bl.run(ITEMS[3:4], model="megaloc", compute=False, log=quiet) == {}  # other settings, other cache


# ---------- summary ----------

def scenario():
    return {
        "stasz:1": fake_result("stasz:1", municipality="Schwyz", conf=0.95, year_range=(1900, 1910), decade=1900),
        "stasz:2": fake_result("stasz:2", municipality="Küssnacht (SZ)", conf=0.85, year_range=(1910, 1920),
                               decade=1910),
        "stasz:3": fake_result("stasz:3", municipality="ingenbohl", conf=0.5, year_range=(1905, 1915), decade=1900),
        "lubis:4": fake_result("lubis:4", municipality="Einsiedeln", conf=0.1, year_range=(1940, 1950), decade=1940),
        "nb:5": None,  # missing result: not scored
    }


def test_summary_validates_and_counts():
    base = {"stasz:1": {"id": "stasz:1", "municipality": "Schwyz", "municipality_confidence": 0.6, "year": None,
                        "year_low": None, "year_high": None, "settings": {"model": "fused"}},
            "stasz:2": {"id": "stasz:2", "municipality": "Schwyz", "municipality_confidence": 0.6, "year": None,
                        "year_low": None, "year_high": None, "settings": {"model": "fused"}}}
    names = {**NAMES, "küssnacht": "Küssnacht"}
    s = sm.build(ITEMS, scenario(), model=MODEL, baseline_preds=base, record_of=lambda pid: None, names=names)
    assert schemas.errors(s, "eval_summary") == []
    assert s["n"] == 4 and s["n_missing"] == 1
    assert s["municipality_accuracy"] == 0.75  # "ingenbohl" is canonicalised, Küssnacht is wrong
    assert sum(c["n"] for c in s["calibration"]) == s["n"]
    assert [c["bin"] for c in s["calibration"]] == ["0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]
    # decades: stasz:1 1900 vs 1905 ok, stasz:2 1910 vs 1931 two off, lubis:4 1940 vs 1950 one off; posted left out
    assert s["decade_n"] == 3
    assert s["decade_accuracy"] == pytest.approx(0.333)
    assert s["decade_within_one"] == pytest.approx(0.667)
    assert s["decade_posted_at_or_before"] == 1.0
    assert s["failures"] == [{"photo_id": "stasz:2", "expected": "Arth", "got": "Küssnacht",
                              "why": s["failures"][0]["why"], "confidence": 0.85, "subset": "card_exact",
                              "place_name_printed": True}]
    assert s["failures"][0]["why"].startswith("Stärkste Evidenz")
    assert s["baseline"]["similarity_only_municipality_accuracy"] == 0.5 and s["baseline"]["n"] == 2
    assert s["cost_usd"] == pytest.approx(0.04)
    assert s["metrics"]["n_scored"] == 4 and s["metrics"]["all"]["municipality"]["accuracy"] == 0.75
    assert {m["municipality"] for m in s["by_municipality"]} == {"Schwyz", "Arth", "Ingenbohl", "Einsiedeln"}
    path = sm.write(s, [])
    assert path.name == "eval_summary.claude-haiku-5-5.json"
    sm.report(s, log=quiet)


def test_summary_why_mentions_rejected_truth_and_coords():
    r = fake_result("stasz:2", municipality="Schwyz")
    r["rejected_hypotheses"] = [{"field": "municipality", "value": "Arth", "reason": "Kein Seeufer"}]
    s = sm.build(ITEMS[1:2], {"stasz:2": r}, model=config.MODEL, names=NAMES,
                 record_of=lambda pid: {"location": {"lat": 47.0, "lon": 8.6, "precision_m": 50}})
    assert s["failures"][0]["why"].startswith("Richtige Gemeinde Arth verworfen: Kein Seeufer")
    assert s["median_coord_error_km"] is not None and s["coord_n"] == 1
    assert sm.summary_path(config.MODEL).name == "eval_summary.json"
    assert sm.build(ITEMS, {}, model=MODEL, names=NAMES) is None


def test_year_derivation():
    r = fake_result("x", year_range=(1898, 1912), decade=1900)
    assert sm.year_fields(r) == (1905, 1898, 1912, 1900)
    r["fields"]["year_range"]["value"] = None
    assert sm.year_fields(r) == (1905, 1900, 1909, 1900)
    r["fields"]["decade"]["value"] = None
    assert sm.year_fields(r) == (None, None, None, None)
    assert sm.decade_distance(1890, {"year_from": 1905, "year_to": 1921}) == 1
    assert sm.decade_distance(1910, {"year_from": 1905, "year_to": 1921}) == 0
    assert sm.decade_distance(1900, {"year_from": 1905, "year_to": 1905, "year_is_upper_bound": True}) is None


# ---------- CLI ----------

def test_cli_without_eval_items_explains_and_does_not_crash(tmp_path, capsys):
    assert runner.main(["--summary-only", "--eval-file", str(tmp_path / "missing.jsonl")]) == 1
    assert "Keine Eval-Items" in capsys.readouterr().out


def test_cli_full_flow_on_synthetic_items(fake_analyze, tmp_path, tmp_results, capsys):
    p = tmp_path / "eval.jsonl"
    p.write_text("".join(json.dumps(it) + "\n" for it in ITEMS), encoding="utf-8")
    assert runner.main(["--summary-only", "--eval-file", str(p), "--model", MODEL]) == 1  # nothing cached yet
    assert runner.main(["--eval-file", str(p), "--model", MODEL, "--workers", "2"]) == 0
    s = json.loads((tmp_results / f"eval_summary.{MODEL}.json").read_text(encoding="utf-8"))
    assert s["n"] == len(ITEMS) and s["municipality_accuracy"] == 1.0
    assert (tmp_results / f"eval_predictions.{MODEL}.jsonl").exists()
    fake_analyze.clear()
    assert runner.main(["--summary-only", "--eval-file", str(p), "--model", MODEL]) == 0
    assert fake_analyze == []
    assert "Best so far" in capsys.readouterr().out
