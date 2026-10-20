# SCOPE 1: Data (owner: Dijar)

Read `docs/CONTRACTS.md` first. This file is self-contained for the Data workstream, but every interface named here is defined there.

## Goal

Give the agent and the frontend clean, fast, honest data:
- every photo as a `PhotoRecord`
- a similarity index the agent can query
- a leak-free labelled eval set
- composite postcards split into single photos
- everything packaged so the demo runs offline on the M4 Air

## Owned folders (strict)

| You own | You never edit |
|---|---|
| `data_pipeline/` (code) | `agent/`, `frontend/` |
| `data/` except `data/results/` (data, gitignored) | `data/results/` (Agent writes it) |

`contracts/` and `docs/CONTRACTS.md` are shared: change them only after agreeing in the team chat.

## Already done before Friday (pre-event, data only)

| Item | Where |
|---|---|
| Staatsarchiv scraper + raw data (SG.CIV.12 Ansichtskarten, SG.CIV.04 Flugaufnahmen), watermark strip cropped | `data/records/staatsarchiv.jsonl`, `data/images/staatsarchiv/` |
| Smapshot collector (Schwyz, pre-1970, with camera pose) | `data/records/smapshot.jsonl`, `data/images/smapshot/` |
| E-Pics collector (Schwyz bbox, pre-1970, CC BY-SA / PDM only) | `data/records/epics.jsonl`, `data/images/epics/` |
| Merged + deduplicated records | `data/records/all.jsonl` |
| Embeddings (DINOv2-small and CLIP ViT-B/32) + FAISS index | `data/index/` |
| Eval / showcase / timeline / demo splits + stats | `data/splits/` |
| Gazetteer of Schwyz municipalities | `data/gazetteer/gemeinden.json` |

> [!IMPORTANT]
> Staatsarchiv images have no open licence. They never go into git, never into a public URL, never into the submission upload. Only the private repo's `.gitignore`d `data/` holds them.

## Inputs (what you consume)

| Input | From |
|---|---|
| Archive catalog, Smapshot API, E-Pics API (already scraped) | external, pre-event |
| swisstopo WMTS tiles for the offline cache | external (geo.admin.ch) |
| Canton photos handed out at the 18:30 pitch, if any | event; ingest as `source: "upload"` records |
| Eval results, to help debug failures | Agent (`data/results/eval_summary.json`) |

## Outputs (what you provide)

| Output | To | Contract |
|---|---|---|
| `data/` layout, PhotoRecords | Agent, Frontend | CONTRACTS 1, 2 |
| Python module `data_pipeline` with `get_record`, `similar_images`, `archive_lookup`, `split_composite`, `timeline`, `gazetteer` | Agent (Agent serves them over HTTP to Frontend) | CONTRACTS 4 |
| Eval ground truth `data/splits/eval.jsonl` | Agent eval runner | CONTRACTS 1, 7 |
| Demo shortlist `data/splits/demo.json`, timeline sets | Frontend demo mode, pitch | CONTRACTS 1 |
| Offline bundle (data subset + `data/tiles/`) | Laptop demo | CONTRACTS 1 |

## Interfaces

- **Implements:** CONTRACTS section 1 (disk layout), 2 (PhotoRecord), 4 (Python interfaces), 8 (fixtures: you own `photo_record.json` and `timeline.json`).
- **Depends on:** nothing at runtime. Section 5 `GET /timeline` and `GET /images` are served by Agent but read your functions.

## Mock / stub strategy (so all three start at 19:00)

1. At 19:00 the repo already has `data_pipeline/stub.py`: every section 4 function returns data from `contracts/fixtures/`. `DATA_PIPELINE_STUB=1` makes `import data_pipeline` use it. Agent develops against the stub; you swap in real code function by function behind the same signatures.
2. Real data already exists on Friday, so the stub is only a safety net. Keep it working until Sat 10:00.
3. Never change a function signature silently. If you must, update CONTRACTS.md, the stub and the fixture in one commit and tell Said.

## Friday / Saturday schedule

| Time | Task | Done when |
|---|---|---|
| Fri 19:00 to 20:00 | Install shared venv, check `data/` on the laptop, `get_record` + `gazetteer` real | Said can `import data_pipeline` with real records |
| Fri 20:00 to 22:00 | `similar_images` (FAISS, best model from the pre-event retrieval check, `exclude_ids`, `sources` filter) + `archive_lookup` (eval ids excluded) | Top-8 query under 200 ms on the laptop |
| Fri 22:00 to 23:00 | `timeline(lat, lon, radius_m)` | Hauptplatz Schwyz returns cards 1899 to 1972 sorted by year |
| **Fri 23:00** | **Integration checkpoint 1:** agent runs end to end on real data for 1 card | |
| Fri 23:00 to Sat 03:00 | `split_composite` (see notes) + test on the demo shortlist | All demo composites split correctly |
| Sat 03:00 to 08:00 | Sleep in shifts (agree with team) | |
| Sat 08:00 to 10:00 | Offline bundle: subset + tile cache + `README` "run on laptop" | App runs with Wi-Fi off |
| **Sat 10:00** | **Integration checkpoint 2:** full flow on laptop, eval run started | |
| Sat 10:00 to 14:00 | Help Said with eval failures; ingest canton photos if given; polish demo picks | |
| **Sat 14:00** | **Code freeze.** Record backup demo video | |
| Sat 14:00 to 17:00 | Pitch slides (data numbers, architecture), rehearsal | Submission at 17:00 |

## Implementation notes

- **Composite splitter:** start classical (OpenCV): grayscale, threshold the light card background and decorative borders, find large rectangular contours (area over 15% of the card, aspect 0.5 to 2.5), drop nested boxes. Fall back to "one part = full image". Wow option if time: ask Claude Haiku 5.5 for bounding boxes, but only through Agent's client (Agent owns model calls) or with a clearly separate, budget-guarded helper you agree on with Said.
- **Leakage:** `similar_images(exclude_ids=[...])` must also exclude crops (`id#n`) and the parent. `archive_lookup` never returns any eval id. Test this with a unit test: query each of 20 eval cards, assert their ids never appear.
- **Image paths** in records are relative to `data/`. Expose `DATA_DIR` env (default `./data`).
- **Tile cache:** only the demo area (about 5 km around each demo location), zoom 12 to 17, only the zeitreihen years used by the demo timeline sets plus `swissimage` current. Throttle to at most 5 tiles/second (WMTS limit is 1,200/min; we stay far below). Store as `data/tiles/<layer>/<time>/<z>/<x>/<y>.<ext>`; Frontend switches tile URL to the backend's static route in offline mode.
- **Attribution** must survive: `license.credit` for every record ("ETH-Bibliothek Zürich, Bildarchiv", "Staatsarchiv Schwyz, <Signatur>", "© swisstopo").

## Definition of done

1. All section 4 functions real, typed, with docstrings, and a `tests/` file covering leakage, timeline sort, splitter on 5 known composites.
2. `data/splits/stats.json` gives numbers for the pitch: records per source, labelled vs undated, eval size per municipality.
3. Offline bundle runs the full demo on the M4 Air with Wi-Fi off.
4. No Staatsarchiv image or API key in git (`git ls-files data | wc -l` is 0).

## Priority order

**Must (Fri):**
1. `get_record`, `gazetteer`, `similar_images`, `archive_lookup` real
2. Leakage-safe eval set handed to Said
3. `timeline`

**Must (Sat morning):**
1. `split_composite` for the demo cards
2. Offline bundle

**Wow:**
1. Canton photos ingested live
2. LUBIS terrestrial photos as extra dated references
3. Haiku-assisted splitting
4. Retrieval comparison chart (DINOv2 vs CLIP) for the pitch

## Cut first if time runs out

1. Haiku-assisted splitting (keep OpenCV only).
2. Generic splitter: hand-annotate bounding boxes for the ~10 demo composites in `data/splits/demo.json` instead.
3. Tile cache beyond the 2 main demo locations.
4. LUBIS extras.
