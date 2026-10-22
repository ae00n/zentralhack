#!/usr/bin/env bash
# Full scrape chain, resumable: re-running skips everything already in data/records.
# Usage: ./run_scrapes.sh refs     (E-Pics, E-Pics postcards, then Smapshot)
#        ./run_scrapes.sh archive  (Staatsarchiv SG.CIV.12, then SG.CIV.04)
set -u
cd "$(dirname "$0")"
LOGS=../data/logs
mkdir -p "$LOGS"
PY=.venv/bin/python
case "${1:-}" in
  refs)
    $PY -m data_pipeline.scrapers.epics fetch >> "$LOGS/epics_full.log" 2>&1
    $PY -m data_pipeline.scrapers.epics fetch --postcards >> "$LOGS/epics_pk.log" 2>&1
    $PY -m data_pipeline.scrapers.smapshot fetch >> "$LOGS/smapshot_full.log" 2>&1
    ;;
  archive)
    $PY -m data_pipeline.scrapers.staatsarchiv fetch --collection SG.CIV.12 >> "$LOGS/stasz_full.log" 2>&1
    $PY -m data_pipeline.scrapers.staatsarchiv fetch --collection SG.CIV.04 >> "$LOGS/stasz_04.log" 2>&1
    ;;
  *) echo "usage: $0 refs|archive" >&2; exit 2 ;;
esac
