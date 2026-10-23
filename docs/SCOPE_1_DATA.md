# SCOPE 1: Data (owner: Dijar)

> [!IMPORTANT]
> **v3 (Fri 23 Oct evening): the task changed.** The real test set is 603 handed-out 21st-century photos (`challenge:SG.CIV.17.*`, 50 Prio 1), not old postcards, and dating is not asked. Read `docs/CHALLENGE_BRIEF.md` (your to-do list is in its section 5) and the v3 notes in `docs/CONTRACTS.md` before continuing the build order below. Where they disagree, the brief wins.

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
| Staatsarchiv: SG.CIV.12 (6,417 postcards), SG.CIV.04 (153 aerials), photographer series SG.CIV.21 to .31 (2,837) | `scrapers/staatsarchiv.py` | done |
| E-Pics (4,466, CC BY-SA / PDM) and Smapshot (camera poses) | `scrapers/epics.py`, `scrapers/smapshot.py` | done |
| swisstopo LUBIS ground photos (2,716, exact capture day, camera station) | `scrapers/lubis.py` | done |
| Swiss National Library Wehrli + Zinggeler photos from Commons (2,884, public domain) | `scrapers/nb_commons.py` | done |
| Wehrli negative number to date table (22,615 negatives) | `scrapers/helveticarchives.py` | done |
| Merge (19,988 records) | `merge.py` | done |
| Eval v2 (350 items in 3 subsets, frozen), showcase, timeline sets, demo shortlist | `splits.py` | done; `splits refresh` rewrites timelines + stats without touching eval. 64 timeline sets labelled by the geocoded place tag; 10 demo cards (incl. 2 split composites, 1 card with no printed place name) |
| Shared scoring for every eval run | `metrics.py` | done |
| Embeddings: CLIP, DINOv2, MegaLoc; rank fusion; LightGlue verification | `embed.py`, `verify.py` | done; `best` = megaloc (LOO over 8,342 cards, top-5 vote: MegaLoc 80%, CLIP 68%, DINOv2 69%). Crops are indexed too |
| Date hints: near-duplicates, card-number series, NB negatives, publisher eras, CLIP year probe; 55 sourced dating rules | `dating.py`, `dating_rules.json` | done; card number median error 1 year, year probe 4 |
| CONTRACTS section 4 functions + `DATA_PIPELINE_STUB=1` stub | `api.py`, `stub.py`, `__init__.py` | done, 24 tests pass |
| Composite splitter (Claude Haiku boxes) | `split.py` | done: recall 0.90, precision 0.90 on 76 labelled cards; all 6,017 SG.CIV.12 cards split ($0.82): 543 composites, 1,851 crops in `records/crops.jsonl` |
| Offline tile cache + laptop bundle | `tiles.py`, `bundle.py` | done: 27,178 tiles (3.9 GB): zeitreihen, one TIME per decade 1870s to 2020s (16 `map_years` in `data/tiles/manifest.json`), + swissimage, around 15 demo areas. `bundle` writes `~/zh-bundle/zh-data.tar` (10.6 GB: data without raw + model weights); unpacked, every section 4 call works with no network |
| Challenge photos (v3) | `scrapers/challenge.py` | done: 603 records in `records/challenge.jsonl` (50 Prio 1), EXIF date on 601, real GPS on 1, `raw.session` groups (267 photos), images in `images/challenge/`. Not indexed |
| Ortschaft / Gemeinde / Strasse / named buildings (v3) | `places.py` | done: `address_lookup` (swisstopo Ortschaftenverzeichnis, swissBOUNDARIES3D, Gebäudeadressverzeichnis, disk-cached) and `named_buildings` (OSM via Overpass, `python -m data_pipeline.places build`, offline after) |
| Remote data mode (no local `data/`) | `serve.py`, `remote.py` | done: `https://zhdata.vatra.sh` (Dijar's server, bearer token, temporary until 24 Oct). Client env `DATA_PIPELINE_URL` + `DATA_PIPELINE_TOKEN`: small files mirrored into `ZH_DATA_DIR`, images fetched on first use, `similar_images` / `date_hints` / `split_composite` run on the server. Parity run: 16 of 16 calls identical to local. The server needs `ANTHROPIC_API_KEY` or the splitter falls back to OpenCV |

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

Three modes, same functions: local `data/` (default), `DATA_PIPELINE_STUB=1` (fixtures), `DATA_PIPELINE_URL` (data server, see the state table).

- `DATA_PIPELINE_STUB=1` makes every section 4 function return `contracts/fixtures/` data. It is Said's fallback if real data is missing on his machine; keep it working until the code freeze.
- Never change a signature silently: update CONTRACTS.md, stub and fixture in one commit on `main` and tell Said.

## Build order

Each item is done when its check passes. Items 1 to 4 of the earlier order (scrapes, merge + splits, embeddings, splitter eval) are done. Items 1 to 5 below are done on our side (22 Oct); item 5's last check (full demo with Wi-Fi off on the M4 Air) needs the backend and frontend, Sat 10:00.

1. **Split all composites.** `python -m data_pipeline.split batch`. Check: crops in `data/records/crops.jsonl`, cost under $2.
2. **Point "best" at the strongest index.** `embed check`, then make sure `best.json` names `megaloc` (Said can also ask for `model="fused"`). Check: `similar_images` default beats CLIP on the LOO check.
3. **Timeline sets.** Places with 4 or more dated cards (62 today). Check: `timeline()` for Hauptplatz Schwyz returns cards sorted by year.
4. **Demo shortlist.** About 10 cards in `demo.json`, each with a `why`: undated ones, composites, Hauptplatz Schwyz, Brunnen, Kloster Einsiedeln. Check: every card has an image and, after Said's run, a cached result.
5. **Offline bundle.** Data subset for the demo cards and their references, plus a tile cache: about 5 km around each demo location, zoom 12 to 17, only the zeitreihen years in the demo timeline sets plus `swissimage` current, at most 5 tiles/s, stored as `data/tiles/<layer>/<time>/<z>/<x>/<y>.<ext>`. Check: the full demo runs on the M4 Air with Wi-Fi off.
6. **Data causes of eval failures.** When Said shares failures, fix only the data side (wrong municipality mapping, bad crops, wrong dates). Prompts and agent runs stay his.

Wow, after the musts: a retrieval chart for the pitch (CLIP vs MegaLoc vs fused + verify).

## Rules that must hold

- **Leakage:** `similar_images(exclude_ids=[...])` also excludes crops (`id#n`) and the parent; `archive_lookup` never returns an eval id. Tests cover this.
- **Attribution:** every record keeps `license.credit` ("Staatsarchiv Schwyz, <Signatur>", "ETH-Bibliothek Zürich, Bildarchiv / ...", "© swisstopo").
- **Paths:** image paths are relative to `data/`; `ZH_DATA_DIR` overrides the location.

## v3 build order (Fri 23 Oct onward)

1. Challenge records. Done.
2. `address_lookup`, `named_buildings`. Done (buildings.json needs the Overpass download once).
3. Saturday morning: `splits/challenge_qc.jsonl` from the team's hand check of about 20 Prio-1 results.
4. Data fixes for agent failures on challenge photos (wrong building names, missing OSM names).

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

1. The retrieval chart.
2. Generic splitting: hand-annotate boxes for the ~10 demo composites in `demo.json` instead.
3. Tile cache beyond the two main demo locations.
