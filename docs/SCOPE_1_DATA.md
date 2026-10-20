# SCOPE 1: Data (owner: Dijar)

Read `docs/CONTRACTS.md` first. Every interface named here is defined there. Work on branch `dijar/data`.

## Goal

Give the agent and the frontend clean, fast, honest data:
- every photo as a `PhotoRecord`
- a similarity index the agent can query
- a leak-free labelled eval set
- composite postcards split into single photos
- a bundle so the demo runs offline on the M4 Air

## Owned folders

| You own | You never edit |
|---|---|
| `data_pipeline/` (code) | `agent/`, `frontend/` |
| `data/` except `data/results/` (gitignored) | `data/results/` (Agent writes it) |

`contracts/` and `docs/CONTRACTS.md` are shared: change them only after the team agrees, on `main`.

> Staatsarchiv images have no open licence. They never go into git, a public URL or the submission upload.

## Current state (built, on `dijar/data`)

| Piece | File | State |
|---|---|---|
| Polite HTTP client (throttle, retry, disk cache) | `http.py` | done |
| Schwyz gazetteer: 30 municipalities, Thema tag to municipality via swisstopo SearchServer | `gazetteer.py`, `geo.py` | done |
| Staatsarchiv scraper (SG.CIV.12, 6,417 cards; SG.CIV.04) | `scrapers/staatsarchiv.py` | full run in progress |
| E-Pics collector (geotagged pre-1970 + postcards, CC BY-SA / PDM only) | `scrapers/epics.py` | full run in progress |
| Smapshot collector (camera poses, pre-1970) | `scrapers/smapshot.py` | queued after E-Pics |
| Resumable runner | `run_scrapes.sh refs|archive` | done |
| Merge to `data/records/all.jsonl` (E-Pics and Smapshot joined on file name) | `merge.py` | done, rerun after scrape |
| Eval / showcase / timeline / demo splits + stats | `splits.py` | done, rerun and freeze after scrape |
| CONTRACTS section 4 functions + `DATA_PIPELINE_STUB=1` stub | `api.py`, `stub.py`, `__init__.py` | done, 16 tests pass |
| Embeddings: DINOv2-small + CLIP ViT-B/32, FAISS, `data/index/best.json` | `embed.py` | done on partial data |
| Composite splitter | `split.py` | classical CV failed (recall 0 on 10 labelled composites); default is Claude Haiku boxes, untested until `ANTHROPIC_API_KEY` is set |

## Inputs

| Input | From |
|---|---|
| Archive catalog, E-Pics API, Smapshot API | external (scrapers) |
| swisstopo WMTS tiles for the offline cache | external (geo.admin.ch) |
| Canton photos at the challenge pitch, if any | event; ingest as `source: "upload"` |
| Eval results, to debug failures | Agent (`data/results/eval_summary.json`) |

## Outputs

| Output | To | Contract |
|---|---|---|
| `data/` layout, PhotoRecords, images | Agent, Frontend | 1, 2 |
| `import data_pipeline` (all section 4 functions) | Agent | 4 |
| `data/splits/eval.jsonl` ground truth | Agent eval runner | 1, 7 |
| `demo.json`, `timeline_sets.json` | Agent `/demo`, `/timeline`; Frontend | 1, 5 |
| Offline bundle (data subset + `data/tiles/`) | demo laptop | 1, 5 |
| Fixtures `photo_record.json`, `timeline.json` (already on `main`) | Agent, Frontend | 8 |

## Stub strategy

- `DATA_PIPELINE_STUB=1` makes every section 4 function return `contracts/fixtures/` data. It is Said's fallback if real data is missing on his machine; keep it working until the code freeze.
- Never change a signature silently: update CONTRACTS.md, stub and fixture in one commit on `main` and tell Said.

## Build order

Each item is done when its check passes.

1. **Finish the scrapes.** Check: `wc -l data/records/*.jsonl` matches the logs; a rerun of `run_scrapes.sh` fetches 0 new records.
2. **Merge + splits.** `python -m data_pipeline.merge`, then `python -m data_pipeline.splits`. Freeze `eval.jsonl` (about 300 cards, stratified by municipality, fixed seed) and tell Said. Check: `stats.json` shows records per source, dated vs undated, eval size per municipality.
3. **Embeddings on the full set.** `python -m data_pipeline.embed build`, then `embed check`. Check: `best.json` names the model, and its top-5 municipality agreement beats the "always Schwyz" baseline.
4. **Splitter.** Set `ANTHROPIC_API_KEY`, then `python -m data_pipeline.split eval --method vlm` against `tests/split_labels.json` (76 hand labels, 10 composites), then `split batch`. Check: recall at least 0.8 on the labelled composites; cost under $1.
5. **Timeline sets.** Places with 4 or more dated cards. Check: `timeline()` for Hauptplatz Schwyz returns cards sorted by year.
6. **Demo shortlist.** About 10 cards in `demo.json`, each with a `why`: undated ones, composites, Hauptplatz Schwyz, Brunnen, Kloster Einsiedeln. Check: every card has an image and, after Said's run, a cached result.
7. **Offline bundle.** Data subset for the demo cards and their references, plus a tile cache: about 5 km around each demo location, zoom 12 to 17, only the zeitreihen years in the demo timeline sets plus `swissimage` current, at most 5 tiles/s, stored as `data/tiles/<layer>/<time>/<z>/<x>/<y>.<ext>`. Check: the full demo runs on the M4 Air with Wi-Fi off.
8. **Help Said with the eval.** Look into failures, fix data causes (wrong municipality mapping, bad crops).

Wow, after the musts:
- LUBIS terrestrial photos (`ch.swisstopo.lubis-terrestrische_aufnahmen`) as extra dated references.
- DINOv2 vs CLIP retrieval chart for the pitch.

## Rules that must hold

- **Leakage:** `similar_images(exclude_ids=[...])` also excludes crops (`id#n`) and the parent; `archive_lookup` never returns an eval id. Tests cover this.
- **Attribution:** every record keeps `license.credit` ("Staatsarchiv Schwyz, <Signatur>", "ETH-Bibliothek Zürich, Bildarchiv / ...", "© swisstopo").
- **Paths:** image paths are relative to `data/`; `ZH_DATA_DIR` overrides the location.

## Event days (Fri 23 Oct 19:00 to Sat 24 Oct 17:00)

- Fri 23:00 checkpoint: merge `dijar/data` into `main`; agent runs end to end on real data.
- Sat 10:00 checkpoint: full flow on the laptop; Said's eval run started.
- Ingest canton photos if they hand any out.
- Sat 14:00 code freeze: record the backup demo video.
- Sat 17:00: submission and pitch (you own the data numbers and the architecture slide).

## Definition of done

1. All section 4 functions real, tested (leakage, timeline sort, splitter on known composites).
2. `stats.json` gives the pitch numbers.
3. The offline bundle runs the demo with Wi-Fi off.
4. `git ls-files data | wc -l` is 0; no key in git.

## Cut first if time runs out

1. LUBIS extras and the retrieval chart.
2. Generic splitting: hand-annotate boxes for the ~10 demo composites in `demo.json` instead.
3. Tile cache beyond the two main demo locations.
