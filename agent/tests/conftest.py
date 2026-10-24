import os

# Tests never touch real data, the real results cache or the Claude API.
os.environ.setdefault("DATA_PIPELINE_STUB", "1")

import pytest


@pytest.fixture(autouse=True)
def tmp_results(tmp_path, monkeypatch):
    from agent import config, results

    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(results, "RESULTS_DIR", tmp_path / "results")
    return tmp_path / "results"
