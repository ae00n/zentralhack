# SCOPE 2: Agent, backend, eval (owner: Said)

Read `docs/CONTRACTS.md` first. This file is self-contained for the Agent workstream, but every interface named here is defined there.


> [!IMPORTANT]
> Timeline change (2026-10-20): build this scope **now**, before the event. Use the schedule table below as the build order; the clock times no longer apply. Fri 19:00 to Sat 17:00 is for merging, integration, the eval run, the demo video and the pitch. Merge into `main` at least daily.

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

## Already done before Friday

- The contract (CONTRACTS.md) and fixtures exist.
- A manual sanity test: about 10 eval cards pasted into the Claude console by hand to confirm the model can geolocate Schwyz postcards at all. Notes in `docs/RESEARCH.md`. **No agent code exists yet.** You build all of it at the event.

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

## Mock / stub strategy (so all three start at 19:00)

1. **You depend on Data:** run with `DATA_PIPELINE_STUB=1`; every section 4 function returns fixture data. Real data already exists on Friday, so switch off the stub as soon as Dijar confirms each function (target Fri 22:00).
2. **Frontend depends on you:** at Fri 19:30 ship a fake mode first: `AGENT_FAKE=1` makes `POST /analyze` return a job whose SSE stream replays the trace from `contracts/fixtures/analysis_result.json` with 300 ms delays, then the fixture result. Timo builds the whole UI against this. Keep fake mode working until the end (it is also the offline fallback).
3. Never change a response shape silently. Update CONTRACTS.md + fixture in one commit and tell Timo.

## Friday / Saturday schedule

| Time | Task | Done when |
|---|---|---|
| Fri 19:00 to 19:45 | FastAPI skeleton, `/health`, `/photos`, `/images`, fake `/analyze` + SSE | Timo gets fixture results from the real server |
| Fri 19:45 to 22:00 | Agent loop v1: one image in, tool loop, AnalysisResult out (CLI first: `python -m agent.run <photo_id>`) | Runs on 3 eval cards |
| Fri 22:00 to 23:00 | swisstopo tools with cache; real `data_pipeline` | |
| **Fri 23:00** | **Integration checkpoint 1:** real agent behind `/analyze` for 1 card, shown in Timo's UI | |
| Fri 23:00 to Sat 02:00 | Eval runner + similarity-only baseline; first eval on 50 cards with Haiku/Sonnet | First accuracy number exists |
| Sat 02:00 to 07:00 | Sleep in shifts | |
| Sat 07:00 to 10:00 | Prompt / tool fixes from failures; composite handling via `split_composite` | |
| **Sat 10:00** | **Integration checkpoint 2:** full flow on laptop; start full eval (300 cards, Sonnet) | |
| Sat 10:00 to 13:00 | Export endpoints, `/timeline`, `/eval/summary`; pre-compute results for all demo cards (Opus) into cache | Demo mode needs no live API |
| **Sat 14:00** | **Code freeze.** Record backup demo video | |
| Sat 14:00 to 17:00 | Proof slide numbers, honest failure case, rehearsal | Submission at 17:00 |

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

## Priority order

**Must:**
1. Fake mode + SSE for Timo
2. Agent loop with `submit_result`
3. similar_images + swisstopo_search tools
4. Eval runner + baseline
5. Cached demo results
6. Export

**Wow:**
1. terrain_check
2. Composite handling per part
3. Calibration chart
4. Opus vs Sonnet comparison
5. Live upload of a canton photo during the pitch

## Cut first if time runs out

1. Opus comparison and calibration chart.
2. `terrain_check` tool.
3. Live analysis during the demo (use cached results + replayed SSE trace instead).
4. Eval size: drop from 300 to 100 cards (report the n honestly).
