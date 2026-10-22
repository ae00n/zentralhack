import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "contracts" / "fixtures"
SCHEMAS = ROOT / "contracts" / "schemas"


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setenv("DATA_PIPELINE_STUB", "1")
    for m in [m for m in sys.modules if m.startswith("data_pipeline")]:
        del sys.modules[m]
    import data_pipeline
    yield data_pipeline
    for m in [m for m in sys.modules if m.startswith("data_pipeline")]:
        del sys.modules[m]


def test_stub_mode_answers_from_fixtures(stub):
    rec = json.loads((FIX / "photo_record.json").read_text())
    assert stub.get_record(rec["id"])["id"] == rec["id"]
    assert stub.similar_images("x.jpg", exclude_ids=[rec["id"]]) == []
    assert stub.similar_images("x.jpg")[0]["id"] == rec["id"]
    assert stub.image_file(rec).exists()
    assert len(stub.gazetteer()) == 30
    assert stub.split_composite(str(stub.image_file(rec)))[0]["bbox"][:2] == [0, 0]
    assert stub.timeline(47.0, 8.6)[0]["id"] == rec["id"]


@pytest.mark.parametrize("fixture,schema", [
    ("photo_record.json", "photo_record.schema.json"),
    ("analysis_result.json", "analysis_result.schema.json"),
    ("eval_summary.json", "eval_summary.schema.json"),
])
def test_fixtures_match_schemas(fixture, schema):
    jsonschema.validate(json.loads((FIX / fixture).read_text()), json.loads((SCHEMAS / schema).read_text()))


@pytest.mark.parametrize("raw,expected", [
    ("1914", (1914, 1914, False)),
    ("keine Angabe", (None, None, False)),
    ("ca. 1915", (1915, 1915, True)),
    ("05.07.1947 - 05.07.1947", (1947, 1947, False)),
    ("1899-1904", (1899, 1904, False)),
    ("", (None, None, False)),
])
def test_staatsarchiv_date_parsing(raw, expected):
    from data_pipeline.scrapers.staatsarchiv import parse_date
    d = parse_date(raw)
    assert (d["year_from"], d["year_to"], d["approximate"]) == expected
