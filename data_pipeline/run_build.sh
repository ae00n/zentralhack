#!/usr/bin/env bash
# The one data build for the agent (v6). Resumable: every step skips work already done.
#   nohup ./run_build.sh > ../data/logs/build.log 2>&1 &
# 1. registers (GWR addresses, swissNAMES3D landmarks)  2. Mapillary, least covered Gemeinden first
# 3. merge  4. MegaLoc index (Commons + Mapillary only)  5. coverage  6. matches for the challenge photos
# Run nothing else CPU-heavy meanwhile: embedding is 5.7 img/s with the CPU free, 0.7 when shared.
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
export EMBED_THREADS="${EMBED_THREADS:-24}" INDEX_SOURCES=commons,mapillary
step() { echo "=== $(date -u +%FT%TZ) $*"; }

step "1 registers";  $PY -m data_pipeline.registers build
step "2 mapillary";  $PY -m data_pipeline.scrapers.mapillary fetch --balanced
step "3 merge";      $PY -m data_pipeline.merge
step "4 index";      nice -n 5 $PY -m data_pipeline.embed build --model megaloc
step "5 coverage";   $PY -m data_pipeline.embed coverage
step "6 matches";    $PY -m data_pipeline.matches build --priority 1
step "6b matches";   $PY -m data_pipeline.matches build
step "done"
