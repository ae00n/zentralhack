import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tiny_data(tmp_path, monkeypatch):
    """A throwaway data/ dir with 3 Staatsarchiv cards (one in eval) and one reference."""
    def rec(i, source="staatsarchiv", year=1910, muni="Schwyz", lat=47.02, lon=8.65):
        return {"id": f"{'stasz' if source == 'staatsarchiv' else source}:{i}", "source": source, "source_id": str(i),
                "date": {"raw": str(year) if year else "keine Angabe", "year_from": year, "year_to": year,
                         "approximate": False},
                "places": ["Hauptplatz", muni], "municipality": muni, "title": f"Karte {i}",
                "location": {"lat": lat, "lon": lon, "method": "thema_gazetteer", "precision_m": 1000},
                "image": {"path": f"images/x/{i}.jpg", "width": 10, "height": 10}, "license": {"code": "x", "credit": "x"}}
    rows = [rec(1, year=1904), rec(2, year=1920), rec(3, year=None), rec(4, source="epics", year=1930)]
    (tmp_path / "records").mkdir()
    (tmp_path / "splits").mkdir()
    (tmp_path / "records" / "all.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows) + '{"truncated')
    (tmp_path / "splits" / "eval.jsonl").write_text(json.dumps({"id": "stasz:1"}) + "\n")
    monkeypatch.setenv("ZH_DATA_DIR", str(tmp_path))
    for m in [m for m in sys.modules if m.startswith("data_pipeline")]:
        del sys.modules[m]
    import data_pipeline
    yield data_pipeline
    for m in [m for m in sys.modules if m.startswith("data_pipeline")]:
        del sys.modules[m]
