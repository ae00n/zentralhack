"""Paths, env flags and model settings shared by the whole agent package."""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

CONTRACTS = REPO_ROOT / "contracts"
FIXTURES = CONTRACTS / "fixtures"
SCHEMAS = CONTRACTS / "schemas"

DATA_DIR = Path(os.environ.get("ZH_DATA_DIR", REPO_ROOT / "data"))
RESULTS_DIR = Path(os.environ.get("AGENT_RESULTS_DIR", DATA_DIR / "results"))
CACHE_DIR = Path(os.environ.get("AGENT_CACHE_DIR", REPO_ROOT / "agent" / ".cache"))

# AGENT_FAKE=1: /analyze replays contracts/fixtures/analysis_result.json, no Claude calls
FAKE = os.environ.get("AGENT_FAKE") == "1"
# DATA_PIPELINE_STUB=1: data_pipeline answers from contracts/fixtures/ (read by data_pipeline itself)
STUB = os.environ.get("DATA_PIPELINE_STUB") == "1"

MODEL = os.environ.get("AGENT_MODEL", "claude-opus-5-5")
DEBUG_MODEL = "claude-haiku-5-5"

# USD per million tokens (input, output), verified 2026-10-20
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-haiku-5-5": (0.10, 0.50),
}

MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", 8))
PHOTO_BUDGET_USD = float(os.environ.get("AGENT_PHOTO_BUDGET", 0.40))
SESSION_BUDGET_USD = 80.0
NEEDS_REVIEW_BELOW = 0.5
