# SCOPE 2: Agent, backend, eval (owner: Said)

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

## Build order

Each item is done when its check passes.

1. **FastAPI skeleton + fake mode:** `/health`, `/photos`, `/photos/{id}`, `/images/{id}`, fake `/analyze` + SSE. Check: Timo's frontend in `live` mode gets the fixture result from your server.
2. **Agent loop v1 as a CLI:** `python -m agent.run <photo_id>`; one image in, tool loop, `submit_result`, a valid AnalysisResult out. Check: runs on 3 eval cards and validates against `contracts/schemas/analysis_result.schema.json`.
3. **Real tools:** `similar_images`, `archive_lookup`, `swisstopo_search` with the disk cache. Check: the trace shows tool calls with German summaries; no eval card leaks into its own tool results.
4. **Real `/analyze` + SSE + result cache** (`data/results/<photo_id>.json`, `?fresh=1`). Check: a second request for the same card is instant.
5. **Eval runner + similarity-only baseline:** first a 50-card Haiku pass to debug, then Sonnet. Check: `eval_summary.json` validates and has the baseline.
6. **Export** (`/export.csv`, `/export.json`), `/timeline`, `/eval/summary`, `/demo`, `/tiles`. Check: the CSV opens in Excel (BOM, `;`).
7. **Composite handling:** run each part from `split_composite` separately; the parent result lists the parts. Check: a known composite yields 2+ part results.
8. **Pre-compute demo results** with Opus into the cache. Check: demo mode needs no API.

Wow, after the musts: `terrain_check`, calibration chart data, Opus vs Sonnet comparison, live upload of a canton photo.

## Event days (Fri 23 Oct 19:00 to Sat 24 Oct 17:00)

- Fri 23:00 checkpoint: merge `said/agent` into `main`; the real agent runs behind `/analyze` in Timo's UI.
- Fri night: the full eval run (300 cards, Sonnet, about $27).
- Sat 10:00 checkpoint: full flow on the laptop; fix failures found in the eval.
- Sat 14:00 code freeze: record the backup demo video.
- Sat 17:00: submission and pitch (you own the proof slide: accuracy, baseline, one honest failure case).

## Agent design (practical guidance)

**Models** (verified pricing 2026-10-20, per MTok input/output):
- Sonnet 5.5 ($2 / $10): default for the agent and the eval.
- Opus 5.5 ($4 / $20): demo cards only, pre-computed.
- Haiku 5.5 ($0.10 / $0.50): cheap pre-pass that reads printed text on the card ("Gruss aus Einsiedeln") and lists visual cues. Text on the card is often the strongest clue.

**Loop:**
1. Pre-pass (Haiku): OCR text, visible landmarks, photo vs print, colour/tinting, clothing/vehicles hints for dating.
2. Main loop (Sonnet, tool use): system prompt + image (resized to max 1024 px, image first, then text) + pre-pass notes.
3. Tools (each returns a short German `output_summary` for the trace plus structured data):
   - `similar_images(k, sources)`: the query photo is passed implicitly; always `exclude_ids=[photo_id]`. Return thumbnails of the top 3 as image blocks so the model can actually compare.
   - `archive_lookup(place, municipality, year_from, year_to)`: dated reference cards for the same place help dating.
   - `swisstopo_search(text)`: SearchServer `type=locations`, gets coordinates for peaks / places / Flurnamen.
   - `terrain_check(lat, lon, azimuth?)`: height + profile, to sanity-check "Mythen visible from here".
   - `submit_result(...)`: the **final answer tool**. Its JSON schema is the `fields` block of CONTRACTS 3 (value, confidence, evidence[] per field, rejected_hypotheses). Forcing the answer through a tool schema gives structured output without parsing prose.
4. **Stop conditions:**
   - The model calls `submit_result`.
   - `max_steps = 8` tool calls.
   - A per-photo budget guard of $0.40: when hit, force `submit_result` with `tool_choice`.
   - Set `needs_review = true` when municipality or decade confidence is under 0.5.

**Prompting tips:**
- Ask for at least 2 competing hypotheses before calling tools, and to state what evidence would reject each.
- Confidence must be justified by evidence count and agreement. Tell it explicitly that 0.9+ needs at least two independent supporting evidence items.
- Dating cues: printing technique (Lichtdruck, colourised), postmark style, vehicles, clothing, buildings present or absent (check against `archive_lookup` dates and zeitreihen map years).
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

1. Input `data/splits/eval.jsonl`, about 300 labelled cards.
2. Run concurrently (4 workers), resumable (skip cards with a cached result for the same model).
3. Metrics per CONTRACTS 7:
   - `municipality_accuracy`
   - `decade_accuracy`
   - `decade_within_one`
   - a calibration table
   - accuracy per municipality
4. **Baseline:** similarity-only, where municipality = the majority vote of the top-5 `similar_images` labels. The pitch claim is "agent beats plain similarity by X points".
5. Pick **one honest failure case** with a clear explanation (e.g. an identical-looking chapel in two villages) for the pitch.
6. Cost estimate: about $0.09 per card on Sonnet, so 300 cards is about $27. Run a 50-card Haiku pass first to debug cheaply.

## Definition of done

1. `POST /analyze` on any demo card returns a valid AnalysisResult (it validates against `contracts/schemas/`) with a live SSE trace.
2. `eval_summary.json` exists for at least 200 cards on Sonnet, with the baseline and the failure case.
3. Export CSV opens correctly in Excel (BOM, `;`).
4. All demo cards have cached results, so the demo works with the API unreachable.
5. No key in git; the cost ledger total stays under $80.

## Cut first if time runs out

1. Opus comparison and calibration chart.
2. `terrain_check` tool.
3. Live analysis during the demo (use cached results + replayed SSE trace instead).
4. Eval size: drop from 300 to 100 cards (report the n honestly).
