"""Locations of everything under data/ (see docs/CONTRACTS.md section 1)."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("ZH_DATA_DIR", REPO_ROOT / "data"))

RECORDS = DATA_DIR / "records"
IMAGES = DATA_DIR / "images"
RAW = DATA_DIR / "raw"
GAZETTEER = DATA_DIR / "gazetteer"
SPLITS = DATA_DIR / "splits"
INDEX = DATA_DIR / "index"


def ensure(*dirs: Path) -> None:
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
