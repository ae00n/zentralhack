import sys
import types


def test_truncated_line_is_skipped(tiny_data):
    assert tiny_data.get_record("stasz:2")["title"] == "Karte 2"


def test_archive_lookup_never_returns_eval_cards(tiny_data):
    ids = [r["id"] for r in tiny_data.archive_lookup(municipality="Schwyz")]
    assert "stasz:1" not in ids
    assert ids == ["stasz:2"]  # undated stasz:3 and the epics record are excluded too


def test_archive_lookup_year_overlap(tiny_data):
    assert tiny_data.archive_lookup(year_from=1921) == []
    assert [r["id"] for r in tiny_data.archive_lookup(place="hauptplatz", year_to=1925)] == ["stasz:2"]


def test_timeline_sorted_and_leak_free(tiny_data):
    t = tiny_data.timeline(47.02, 8.65, 500)
    assert [x["id"] for x in t] == ["stasz:2"]


def test_similar_images_excludes_query_and_its_crops(tiny_data, monkeypatch):
    fake = types.ModuleType("data_pipeline.embed")
    fake.search = lambda path, k, model: [("stasz:2#1", 0.99), ("stasz:2", 0.95), ("epics:4", 0.9), ("stasz:1", 0.8)]
    monkeypatch.setitem(sys.modules, "data_pipeline.embed", fake)
    import data_pipeline
    monkeypatch.setattr(data_pipeline, "embed", fake, raising=False)
    out = tiny_data.similar_images("q.jpg", k=5, exclude_ids=["stasz:2"])
    assert [o["id"] for o in out] == ["epics:4", "stasz:1"]
    out = tiny_data.similar_images("q.jpg", k=5, exclude_ids=["stasz:2"], sources=["epics"])
    assert [o["id"] for o in out] == ["epics:4"]


def test_eval_ids(tiny_data):
    assert tiny_data.eval_ids() == {"stasz:1"}
