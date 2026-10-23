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


def test_archive_lookup_open_ended_date(tiny_data):
    from data_pipeline import api
    r = dict(api.get_record("stasz:2"), id="stasz:5", date={"raw": "nach 1910", "year_from": 1910, "year_to": None})
    api._records()["stasz:5"] = r
    assert [x["id"] for x in tiny_data.archive_lookup(year_from=1950)] == ["stasz:5"]


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
    # without an exclusion, a card and its crop count once: the better-scored crop stays
    out = tiny_data.similar_images("q.jpg", k=5)
    assert [o["id"] for o in out] == ["stasz:2#1", "epics:4", "stasz:1"]


def test_eval_ids(tiny_data):
    assert tiny_data.eval_ids() == {"stasz:1"}


def test_similar_images_verify_reranks(tiny_data, monkeypatch):
    fake = types.ModuleType("data_pipeline.embed")
    fake.search = lambda path, k, model: [("stasz:2", 0.95), ("epics:4", 0.9), ("stasz:3", 0.8)]
    geo = types.ModuleType("data_pipeline.verify")
    inl = {"2.jpg": 5, "4.jpg": 80, "3.jpg": 40}
    geo.verify = lambda q, paths: [{"path": str(p), "matches": 99, "inliers": inl[p.name],
                                    "verified": inl[p.name] >= 30} for p in paths]
    import data_pipeline
    for name, mod in (("embed", fake), ("verify", geo)):
        monkeypatch.setitem(sys.modules, f"data_pipeline.{name}", mod)
        monkeypatch.setattr(data_pipeline, name, mod, raising=False)
    plain = tiny_data.similar_images("q.jpg", k=3)
    assert [o["id"] for o in plain] == ["stasz:2", "epics:4", "stasz:3"]
    assert set(plain[0]) == {"id", "score", "record"}  # default shape unchanged
    out = tiny_data.similar_images("q.jpg", k=2, verify=True)
    assert [(o["id"], o["inliers"], o["verified"]) for o in out] == [("epics:4", 80, True), ("stasz:3", 40, True)]


def test_archive_lookup_word_order_and_spelling(tiny_data):
    assert [r["id"] for r in tiny_data.archive_lookup(place="Schwyz Hauptplatz")] == ["stasz:2"]
    assert [r["id"] for r in tiny_data.archive_lookup(place="Hauptplaz")] == ["stasz:2"]  # typo: fuzzy fallback
    assert tiny_data.archive_lookup(place="Einsiedeln") == []
