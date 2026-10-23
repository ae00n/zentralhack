# SCOPE 2: Agent, backend, eval (owner: Said)

> [!IMPORTANT]
> **v3 (Fri 23 Oct evening): the task changed.** The real test set is 603 handed-out 21st-century photos (`challenge:SG.CIV.17.*`, 50 Prio 1), not old postcards, and dating is not asked. Read `docs/CHALLENGE_BRIEF.md` (your to-do list is in its section 5) and the v3 notes in `docs/CONTRACTS.md` before continuing the build order below. Where they disagree, the brief wins.

Read `docs/CONTRACTS.md` first. Every interface named here is defined there. Work on branch `said/agent`.


## Goal

An agent, not a single model call. For each photo it:
1. forms location and date hypotheses from visual cues
2. checks them with tools
3. rejects wrong candidates
4. stops when confident, or flags the photo for human review

The output is an `AnalysisResult` with per-field confidence and evidence, served over HTTP to the frontend. You also produce **the proof slide**: accuracy on labelled archive cards, measured by your eval runner.

## Owned folders (strict)

| You own | You never edit |
|---|---|
| `agent/` (agent loop, tools, FastAPI app, eval runner) | `data_pipeline/`, `frontend/` |
| `data/results/` (cached results, eval summary) | rest of `data/` (Data owns it) |

`contracts/` and `docs/CONTRACTS.md` are shared: change them only after agreeing in the team chat.

## Starting point

- No agent code exists yet; you build all of it.
- `data_pipeline` is real and importable now: from the repo root, `uv venv && uv pip install -e ./data_pipeline` (or `pip install -e ./data_pipeline`). If real data is missing on your machine, set `DATA_PIPELINE_STUB=1` and every function returns fixture data.
- Fixtures and JSON Schemas are on `main` in `contracts/`.
- Real data lives on Dijar's machine (`data/`, not in git). Ask him for a copy or the offline bundle.

## Inputs (what you consume)

| Input | From | Contract |
|---|---|---|
| `data_pipeline` functions (`get_record`, `similar_images`, `archive_lookup`, `split_composite`, `timeline`, `gazetteer`) | Data | CONTRACTS 4 |
| PhotoRecords, images, eval ground truth `data/splits/eval.jsonl` | Data | CONTRACTS 1, 2 |
| swisstopo REST: SearchServer, height, profile | external (api3.geo.admin.ch) | |
| Claude API | external, key in env `ANTHROPIC_API_KEY` | |

## Outputs (what you provide)

| Output | To | Contract |
|---|---|---|
| FastAPI app on `:8000` with all endpoints incl. SSE | Frontend | CONTRACTS 5 |
| `AnalysisResult` JSON, cached in `data/results/<photo_id>.json` | Frontend (demo mode reads cache) | CONTRACTS 3 |
| CSV / JSON export | Frontend export button, jury | CONTRACTS 6 |
| `data/results/eval_summary.json` | Frontend proof view, pitch | CONTRACTS 7 |
| Fixture `contracts/fixtures/analysis_result.json`, `eval_summary.json` kept valid | Frontend | CONTRACTS 8 |

## Interfaces

- **Implements:** CONTRACTS 3, 5, 6, 7.
- **Depends on:** CONTRACTS 1, 2, 4.

## Mock / stub strategy

1. **You depend on Data:** `DATA_PIPELINE_STUB=1` returns fixture data for every section 4 function. Use the real functions whenever `data/` is present.
2. **Frontend depends on you:** build fake mode first. `AGENT_FAKE=1` makes `POST /analyze` return a job whose SSE stream replays the trace from `contracts/fixtures/analysis_result.json` with 300 ms delays, then the fixture result. Timo builds the UI against this. Keep it working to the end: it is also the offline fallback.
3. Never change a response shape silently. Update CONTRACTS.md + fixture in one commit on `main` and tell Timo.

## Handover from Data (2026-10-22, state on `main`)

- `similar_images` default is now **megaloc** (municipality in top 5: 80% vs CLIP 68%, DINOv2 69%, on 8,342 cards). The first call loads it (about 1 GB RAM). `model="fused"` still works.
- Composite postcards are split: 543 composites, 1,851 crops with ids `stasz:N#k` (parent in `parent_id`, `data/records/crops.jsonl`). Crops are in all indexes; `similar_images` counts a card and its crops once (best hit wins). Eval leakage exclusion covers crops.
- `data/splits/demo.json` v2: 3 new cards (357185 four-panel, 357848 undated five-panel, 499742 no printed name, matched via a verified neighbour). All 10 need cached results in `data/results/`.
- Offline map years: `data/tiles/manifest.json`, key `map_years` (16 values, 18791231 to 20211231, one per decade). Serve these in `/health` and `/timeline` when offline.
- `data/` (10 GB) is not in git. **No download needed:** set `DATA_PIPELINE_URL=https://zhdata.vatra.sh` and `DATA_PIPELINE_TOKEN=<from Dijar, private link>` in your `.env`. `data_pipeline` then syncs the small files (about 50 MB, once) into `ZH_DATA_DIR`, fetches images on first use and runs `similar_images`, `date_hints` and `split_composite` on Dijar's server. Same code and data, so every call answers the same as local (16 of 16 calls identical in a parity run). Map tiles are not mirrored. For offline use there is still the bundle `zh-data.tar` (private path only, env vars in its `README.txt`).
- API key: your own key via a private link from Dijar, into the gitignored `.env` as `ANTHROPIC_API_KEY`.
- Open team calls: commit `data_pipeline/uv.lock` or not; demo hosting (Dijar's server vs M4 Air local), decided at the event.

## Build order

Each item is done when its check passes.

1. **FastAPI skeleton + fake mode:** `/health`, `/photos`, `/photos/{id}`, `/images/{id}`, fake `/analyze` + SSE. Check: Timo's frontend in `live` mode gets the fixture result from your server.
2. **Agent loop v1 as a CLI:** `python -m agent.run <photo_id>`; one image in, tool loop, `submit_result`, a valid AnalysisResult out. Check: runs on 3 eval cards and validates against `contracts/schemas/analysis_result.schema.json`.
3. **Real tools:** `similar_images`, `archive_lookup`, `swisstopo_search` with the disk cache. Check: the trace shows tool calls with German summaries; no eval card leaks into its own tool results.
4. **Real `/analyze` + SSE + result cache** (`data/results/<photo_id>.json`, `?fresh=1`). Check: a second request for the same card is instant.
5. **Eval runner + similarity-only baseline:** first a 50-card Haiku pass to debug, then Opus. Check: `eval_summary.json` validates, has the baseline and `metrics` from `data_pipeline.metrics.score`.
6. **Export** (`/export.csv`, `/export.json`), `/timeline`, `/eval/summary`, `/demo`, `/tiles`. Check: the CSV opens in Excel (BOM, `;`).
7. **Composite handling:** run each part from `split_composite` separately; the parent result lists the parts. Check: a known composite yields 2+ part results.
8. **Pre-compute demo results** into the cache. Check: demo mode needs no API.

Wow, after the musts: `terrain_check`, calibration chart data, N=3 sampling with a check call, live upload of a canton photo.

## Event days (Fri 23 Oct 19:00 to Sat 24 Oct 17:00)

- Fri 23:00 checkpoint: merge `said/agent` into `main`; the real agent runs behind `/analyze` in Timo's UI.
- Fri night: the full eval run (350 items, Opus, about $15 to $30 depending on tool calls).
- Sat 10:00 checkpoint: full flow on the laptop; fix failures found in the eval.
- Sat 14:00 code freeze: record the backup demo video.
- Sat 17:00: submission and pitch (you own the proof slide: accuracy, baseline, one honest failure case).

## Agent design (practical guidance)

**Models** (pricing per MTok input/output, verified 2026-10-20; accuracy measured 2026-10-21 on 200 cards, image only):
- Opus 5.5 ($4 / $20): the agent, the eval and the demo. Municipality 92% (76% without a printed place name), the best confidence separation, about $0.01 per card without tools.
- Haiku 5.5 ($0.10 / $0.50): cheap debug runs while you build. 69% municipality, so not for results.
- Sonnet 5.5 (84%, but only 52% without a printed place name) is far behind Opus on the hard cards: not used.
- Opus reads printed text on the card itself, so a separate OCR pre-pass is not needed.

**API traps on the 5.5 models** (from the Claude API docs):
- Forced tool use (`tool_choice` `any` or `tool`) returns HTTP 400 on Opus 5.5. Use `tool_choice: auto` plus a prompt instruction to call `submit_result`, `strict: true` on that tool, or structured outputs (`output_config.format` with a JSON schema).
- Thinking is always on. Control depth with `output_config.effort` (Opus default `medium`); Haiku 5.5 also thinks by default, so give it enough `max_tokens` or the answer gets cut off.
- No assistant prefill.

**Benchmark to beat** (measured by Data on 2026-10-21 on the frozen eval v2, 350 items, Opus 5.5, single calls without a tool loop, scored with `data_pipeline.metrics.score`). Your eval run is the official number; it should beat the "Best so far" column. If it does not, say so in the pitch and use the better pipeline.

| Metric (350 items) | Image only | Best so far |
|---|---|---|
| Municipality, all | 78% | **83%** |
| Place name printed | 94% | 95% |
| No printed place name | 56% | **68%** (86% when a verified neighbour exists) |
| Unposted cards (`card_exact`) | 75% | **87%** |
| Dated photos (`photo_dated`) | 69% | 72% |
| Confidence ≥ 0.8: share answered / correct | 55% / 99.5% | **69% / 97.5%** |
| Confidence ≥ 0.9: share answered / correct | 47% / 100% | 55% / 99.5% |
| Year median error | 4 | **2** |
| Year within ±5 / ±10 | 62% / 84% | **72% / 86%** |
| Year range contains truth / median width | 89% / 24 years | 90% / 22 years |
| Posted cards: guess at or before the postmark | 88% | 86% |

How "Best so far" was produced (facts, not a design you have to copy):
- Items with a printed place name: one call with the image, `date_hints` as text and `rule_checklist()`.
- Items without one: the same plus up to 5 neighbours from `similar_images(model="fused", verify=True)` that are `verified`, sent as images with municipality, year and coordinates, and the line "their years are only loose hints".
- Both: structured output with a JSON schema (municipality from the 30 Gemeinden as an enum, confidence, year, year_low, year_high, evidence, place_name_printed), effort `medium`, the line "black and white is not evidence of age by itself".
- Eval hygiene: `exclude_ids=[photo_id] + eval_exclusions(photo_id)` plus all eval ids for neighbours.
- Cost: $4.40 per 350 items image only, $6.40 with hints, about $0.025 per item with neighbours.

Known limits: some catalogue years are postmarks or acquisition dates, so year scores have a noise floor; each number has about ±4 to 5 points of sampling uncertainty.

**Loop:**
1. Main loop (Opus, tool use): system prompt + image (resized to max 1024 px, image first, then text). Opus reads the printed text itself.
2. Data tools give `date_hints` and `rule_checklist()` without a model call, so they can go straight into the first prompt.
3. Tools (each returns a short German `output_summary` for the trace plus structured data):
   - `similar_images(k, sources)`: the query photo is passed implicitly; always `exclude_ids=[photo_id]`. Return thumbnails of the top 3 as image blocks so the model can actually compare. `model="fused", verify=True` is the strongest setting (about 8 s per query on CPU).
   - `date_hints(photo_id)`: year clues (near-duplicates, publisher card numbers, dated National Library negatives, publisher eras, a CLIP year model), each with a range and a German evidence line.
   - `archive_lookup(place, municipality, year_from, year_to)`: dated reference cards for the same place help dating.
   - `swisstopo_search(text)`: SearchServer `type=locations`, gets coordinates for peaks / places / Flurnamen.
   - `terrain_check(lat, lon, azimuth?)`: height + profile, to sanity-check "Mythen visible from here".
   - `submit_result(...)`: the **final answer tool**. Its JSON schema is the `fields` block of CONTRACTS 3 (value, confidence, evidence[] per field, rejected_hypotheses). Forcing the answer through a tool schema gives structured output without parsing prose.
4. **Stop conditions:**
   - The model calls `submit_result`.
   - `max_steps = 8` tool calls.
   - A per-photo budget guard of $0.40: when hit, send one more turn that asks for `submit_result` now (forced `tool_choice` is a 400 on Opus 5.5).
   - Set `needs_review = true` when municipality or decade confidence is under 0.5.

**Prompting tips:**
- Ask for at least 2 competing hypotheses before calling tools, and to state what evidence would reject each.
- Confidence must be justified by evidence count and agreement. Tell it explicitly that 0.9+ needs at least two independent supporting evidence items.
- Dating cues: printing technique (Lichtdruck, colourised), postmark style, vehicles, clothing, buildings present or absent (check against `archive_lookup` dates and zeitreihen map years). `rule_checklist()` has these as sourced year bounds.
- "Black and white is not evidence of age by itself": vision models over-date grayscale photos (ChronoVision, 2026).
- Evidence summaries in German, one sentence each.

**Caching and limits:**
- swisstopo REST allows 40 req/min: cache every call on disk (`agent/.cache/`, key = URL) and rate-limit to 30/min.
- Use prompt caching on the system prompt + tool definitions.
- Cache every AnalysisResult to `data/results/<photo_id>.json`, and serve from the cache unless `?fresh=1`.

**Cost tracking:**
- Sum `usage` per run into the result.
- A global ledger `data/results/costs.jsonl`.
- A hard stop when the session total passes $80 (the credit is $100).

**Secrets:**
- `ANTHROPIC_API_KEY` from env / `.env` (gitignored) only.
- Set the spend limit in the Anthropic console.
- Never log the key.

## Eval runner

1. Input `data/splits/eval.jsonl`: 350 items in 3 subsets (CONTRACTS 2). For `card_posted` the year is only an upper bound.
2. Run concurrently (4 workers), resumable (skip cards with a cached result for the same model).
3. Pass `exclude_ids=[photo_id] + eval_exclusions(photo_id)` to `similar_images` and `date_hints`. Score with `data_pipeline.metrics.score(predictions)` into `metrics`, plus CONTRACTS 7:
   - `municipality_accuracy`
   - `decade_accuracy`
   - `decade_within_one`
   - a calibration table
   - accuracy per municipality
4. **Baseline:** similarity-only, where municipality = the majority vote of the top-5 `similar_images` labels. The pitch claim is "agent beats plain similarity by X points".
5. Pick **one honest failure case** with a clear explanation (e.g. an identical-looking chapel in two villages) for the pitch.
6. Cost: a single Opus call with neighbours costs about $0.02 to $0.03 per item; a tool loop costs more. Run a 50-card Haiku pass first to debug cheaply.

## Definition of done

1. `POST /analyze` on any demo card returns a valid AnalysisResult (it validates against `contracts/schemas/`) with a live SSE trace.
2. `eval_summary.json` exists for at least 200 eval items on Opus, with the baseline, `metrics` and the failure case.
3. Export CSV opens correctly in Excel (BOM, `;`).
4. All demo cards have cached results, so the demo works with the API unreachable.
5. No key in git; the cost ledger total stays under $80.

## Cut first if time runs out

1. Calibration chart and N=3 sampling.
2. `terrain_check` tool.
3. Live analysis during the demo (use cached results + replayed SSE trace instead).
4. Eval size: drop from 300 to 100 cards (report the n honestly).
