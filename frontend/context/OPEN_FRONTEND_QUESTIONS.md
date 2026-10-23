# Open frontend questions

State: Thu 22.10.2026, `main` at `5dc54ae` (contracts v2, data build order done). `agent/` and `frontend/` do not exist yet; `said/agent` and `timo/frontend` are identical to `main`.

Every question has a **default**: what the frontend builds until someone answers. So nothing here stops work today; an answer only changes a detail later. **Blocks** says which build-order step (SCOPE_3) needs the real answer.

Per AGENTS.md: the frontend never does Agent or Data work. Questions for Said and Dijar go through Timo; contract changes need the whole team and land in `contracts/` + `docs/CONTRACTS.md` in one commit on `main`.

---

## 1. Unblocked now vs blocked

### Can start now (mock mode, no backend, no `data/`)

| # | Work | Needs |
|---|---|---|
| 1 | Scaffold: Next.js App Router, TS, Tailwind, fonts, tokens, `.env.example`, `npm run fixtures` | nothing |
| 2 | Types for PhotoRecord, AnalysisResult, Evidence, TraceItem, Timeline, EvalSummary, Health, Demo | `contracts/schemas/` + CONTRACTS.md |
| 3 | `lib/api.ts` with the mock adapter (fixtures, trace replay with delays) | fixtures |
| 4 | Archiv grid | local mock list (see 4.1) |
| 5 | Analyse / "Ort & Zeit" screen: fields, confidence, evidence, rejected hypotheses, "Prüfung nötig" | `analysis_result.json` + a local low-confidence variant |
| 6 | Trace replay component (same component serves mock and demo mode) | `trace` in the fixture |
| 7 | Map: pin, uncertainty circle, "© swisstopo", online swisstopo tiles | nothing (WMTS is open, CORS `*`) |
| 8 | Zeitreise slider with snapping to `map_years`, online zeitreihen | `timeline.json` |
| 9 | Damals / Heute side by side with SWISSIMAGE | nothing |
| 10 | Nachweis page from `eval_summary.json`, clearly marked as sample data | fixture |
| 11 | Export buttons (mock: serve `export.csv` fixture) | fixture |

### Blocked or only partly doable

| Work | Waits for | Question |
|---|---|---|
| Live SSE trace (step 8) | Said: `AGENT_FAKE=1` server on :8000 + SSE format | 3.1, 3.12 |
| Demo mode against a real backend (step 5) | Said: `/results/{id}`, `/health`; Dijar: bundle on the M4 Air | 3.4, 2.9 |
| Offline map tiles | Said: `/tiles` route shape; offline `map_years` | 3.3, 3.4 |
| Composite split view | shape of parent result + `crop_bbox` | 3.6 |
| Real archive look (titles, meta lines) | Said: `/photos` with real records | 3.10 |
| Real Nachweis numbers | Said: eval run (Fri night) + `metrics` shape | 3.9 |
| Upload | team decision + Said upload flow | 2.6, 3.11 |

---

## 2. Team (all three)

**2.1 Is "Ort & Zeit" the same screen as `/analyse/[id]`?**
SCOPE_3 lists Analyse as three columns (photo, trace, result) and separately `/karte`, `/zeitreise`, `/vergleich/[id]`. The later "Ort & Zeit" layout puts map + Zeitreise + photo + result + trace on one screen.
Default: `/analyse/[id]` is the "Ort & Zeit" screen. Zeitreise and "Dann und heute" are panels / toggles inside it. `/zeitreise` and `/vergleich/[id]` only as standalone routes if time is left; `/karte` dropped.
Blocks: step 3 layout (decide before Fri 19:00).

**2.2 Confidence display: percent or `0.86`?**
Views list says "bar plus a percentage", the main-screen spec says mono number `0.86` + 2px bar.
Default: mono `0.86` + 60px bar (the newer spec).

**2.3 Where does `overall_confidence` go?**
It is delivered, but "never one global confidence bar on its own".
Default: a muted meta line above the fields ("Gesamt 0.76"), no bar.

**2.4 Show `year_range`?**
It is a result field and an export column, but not in the field list of the views.
Default: inside the Jahrzehnt row: `1900er · 1898 bis 1907`.

**2.5 What does the Archiv grid show?**
Showcase cards are undated by definition, so "undated first" only matters if dated cards are in the grid too.
Default: `/demo` cards first (pitch order), then showcase. No dated cards.

**2.6 Upload: does the canton bring photos on Friday?**
Upload is on the cut list. If the canton brings photos at the 18:30 pitch, it becomes the most convincing demo moment.
Default: no upload until someone hears yes on Friday. Ask the canton at the challenge pitch.

**2.7 Archivist review action ("Übernehmen / Korrigieren")?**
No role or review flow exists. "Prüfung nötig" is only a marker. A minimal accept/correct per field would help "Problemlösung & Relevanz" and "Business-Potenzial" (35 of 100 points), but needs a write endpoint from Said.
Default: not built. Marker only. Mention it as next step in the pitch.

**2.8 Staatsarchiv images in screenshots, slides and the backup video?**
Rule: stasz images never public and never in the submission upload. The backup video and slide screenshots will contain them.
Default: video and screenshots stay local / are only shown in the room; any uploaded material uses only E-Pics, NB, LUBIS (open) images. Need a team yes.

**2.9 The M4 Air: whose, and when can I test the frontend on it?**
Frontend is developed on Windows. The demo runs on macOS with the 10.6 GB bundle. `next/font/google` needs internet at build time; after that the build is offline-safe.
Default: production build (`npm run build && npm start`) on the Air Sat morning, built while online. Need a slot before then (ideally Fri evening).

**2.10 Team mock: layout yes, styling no?** (answered in part, 22.10.)
Timo shared the mock (screenshot, not in the repo): map + time strip left, timeline gallery + metadata right, one screen. That supports the default in 2.1. SCOPE_3 keeps the layout but rejects its styling (blue, pill chips, avatar, "My Archive" / "Contribute" tabs, AI photos, one confidence bar, Edit / "Generate Archive Entry" buttons).
Default: mock layout, archive-look styling as in SCOPE_3. Confirm the team still wants the archive look over the mock's look.

---

## 3. Said (backend, `agent/`)

**3.1 SSE format.** Not specified beyond "one trace item per event, final event result".
- Event names? Default: `event: trace` (data = one TraceItem JSON), `event: result` (data = full AnalysisResult), `event: error` (data = `{message}`).
- Cache hit: does the stream send all trace items then `result` immediately? Default: yes, and the frontend replays them with delays itself.
- Heartbeats / reconnect? Default: no reconnect; on error fall back to polling `GET /analyze/{job_id}` every 1 s.
Blocks: step 8.
Answered (23.10., Said's code on `said/agent` 4fbd332): `event: trace` and `event: result` as in the default, `: ping` every 15 s, no `event: error` (a failed job sends `result` with `status: "error"` and a German `error`). Cache hit sends all trace items, then `result`. Built in step 8, with the polling fallback.

**3.2 IDs in URL paths.** IDs contain `:` and crops contain `#` (`stasz:514200#1`). An unencoded `#` is cut off as a fragment.
Default: frontend sends `encodeURIComponent(id)` in every path (`stasz%3A514200%231`). Backend must decode. Please confirm with a crop id.

**3.3 Tile URL shape (online vs offline).** SCOPE_3 says "same template, different base". It is not:
- online: `https://wmts.geo.admin.ch/1.0.0/{layer}/default/{time}/3857/{z}/{x}/{y}.png|.jpeg`
- offline: `/tiles/{layer}/{time}/{z}/{x}/{y}` (no extension), while Dijar stores `data/tiles/<layer>/<time>/<z>/<x>/<y>.<ext>`
- `tiles_url` is relative (`/tiles`) offline.
Proposal: `/health` returns full templates, e.g. `{tiles: {zeitreihen: "<base>/.../{time}/{z}/{x}/{y}.png", swissimage: "..."}}`, absolute URLs. Default until then: two URL builders in the frontend, relative URLs prefixed with `NEXT_PUBLIC_API_URL`.
Blocks: offline demo.

**3.4 Which `map_years` does `/timeline` return offline?**
Online the contract says GetCapabilities values (many years). The offline cache has only 16 TIMEs, one per decade, 1870s to 2020s (`data/tiles/manifest.json`). If `/timeline` returns the online list while offline, the slider asks for tiles that are not cached and the map goes blank.
Ask: when `offline: true`, return the manifest years. Default: frontend snaps to whatever `map_years` it gets; in demo mode the slider moves in decade steps.
Answered (23.10., Said's code on `said/agent` 4fbd332): `/timeline` always returns the manifest years when `data/tiles/manifest.json` exists, else a fixed list of 12 (1864 to 2021), online too. Offline is safe. Online the slider only uses those 12 sheets although swisstopo has all 178 years 1844 to 2021 (checked in GetCapabilities on 23.10.); returning the full list online would be Said's change, the frontend needs none.

**3.5 `status: "needs_review"` vs `needs_review: true`.** Which does a finished result have?
Default: frontend treats either as "Prüfung nötig".

**3.6 Composite cards.**
- What is in the parent result's `fields`: best part, merged, or empty?
- Crop boxes: from `GET /photos/{part_id}` `crop_bbox`? In pixels of which image (stored max-1024 px JPEG or original)? Format `[x, y, w, h]` or `[x1, y1, x2, y2]`?
Default: parent shows the photo with boxes, the result panel shows the selected part's own `/results/{part_id}`. Boxes assumed `[x, y, w, h]` in stored-image pixels, scaled by `image.width`.
Blocks: composite view (after step 10).

**3.7 Evidence kinds for date hints.** `date_hints` produces `card_number`, `nb_negative`, `publisher_rule`, `year_probe`, `near_duplicate`, but `Evidence.kind` only allows `visual_cue | text_on_card | similar_image | archive_record | swisstopo_place | terrain | map_layer`. Which kind do dating hints get, or is the enum extended (contract change)?
Default: unknown kinds render as a plain row with `summary`; known kinds get a German label.

**3.8 Trace items.** Tool names to expect (`similar_images`, `date_hints`, `archive_lookup`, `swisstopo_search`, `swisstopo_height` / `swisstopo_profile` or `terrain_check`?). Is `output_summary` always present and German? Is `text` of `thought` steps German? Any trace `type` besides `thought`, `tool_call`, `final`?
Default: German labels for known tools, raw name otherwise; show `output_summary` if present.

**3.9 `/eval/summary` before the eval exists, and the `metrics` block.**
- 404 or empty before the Fri night run? Default: Nachweis shows "Noch keine Auswertung"; fixture numbers are invented and never shown outside mock mode.
- `metrics` shape is `{}` in the contract. Per-subset numbers (`card_exact`, `card_posted`, `photo_dated`) and "with vs without printed place name" are the strongest pitch numbers. Please fix the shape (or send one real example) before Sat 10:00.
Answered (23.10., Said's code on `said/agent` 4fbd332): `metrics` is `data_pipeline.metrics.score()` output, built that way in step 7. Before the first eval run `/eval/summary` serves the fixture (not 404); the frontend detects it by `_fixture_note` and shows "Noch keine Auswertung" outside mock mode. Still open: a real summary to check against.

**3.10 `/photos` details.** What does `q` search (title, signature, Thema)? Default sort? Does `split=showcase` return the demo cards too?
Default: no search box at first; frontend sorts nothing itself.

**3.11 Upload flow (only if 2.6 is yes).** `photo_id` of an upload (`upload:<sha1>`?), are `/photos/{id}` and `/images/{id}` available for it afterwards, max size, formats.

**3.12 When is `AGENT_FAKE=1` running on :8000?** It is the first thing that lets the frontend leave mock mode. Needed before the Fri 23:00 checkpoint at the latest.
Answered (23.10.): runs from `said/agent` with `AGENT_FAKE=1 DATA_PIPELINE_STUB=1 uvicorn agent.server.app:app --port 8000`; step 8 was tested against it.

**3.13 `/export.json` row shape.** No fixture. Default: same keys as the CSV header.
Answered (23.10., Said's code on `said/agent` 4fbd332): same keys as the CSV header. Built that way in step 6.

**3.14 `/demo` `why`.** German and meant for the screen, or only for the presenter?
Default: not shown to the jury; a presenter hint only.

**3.15 Absolute or relative URLs** for `image_url` (timeline) and `tiles_url`? Default: relative, prefixed with the API base.

---

## 4. Dijar (data, `data_pipeline/`)

**4.1 More fixtures (contract change, needs team ok).** Mock mode has one record (dated, `split: "reference"`), one result, no composite, no demo list, no health, and timeline entries pointing at stasz images that do not exist. Useful, public-domain images only:
- 5 to 10 showcase-like records (E-Pics / NB / LUBIS images)
- `demo.json` example (`[{id, why, record}]`)
- one composite with its crop records and `crop_bbox`
- one result with fields below 0.5 and `needs_review: true`
Default: the frontend keeps its own mock data in `frontend/mocks/` (derived from the schemas, reusing `sample.jpg`), never in `contracts/`.

**4.2 Tile cache coverage.** Cache covers about 5 km around 15 demo areas, zoom 12 to 17. Outside that (or zoomed out) the offline map is blank.
- Is the area list (`manifest.json` `areas`) reachable for the frontend (via Said) so the map can clamp to it?
Default: in demo mode, `minZoom: 12`, `maxZoom: 17`, map centred on the result coordinates, no free panning far away.

**4.3 Zeitreise span.** zeitreihen ends at 2021, the cache has 2020s. "Heute" = swissimage `current`.
Default: slider runs over `map_years`, last stop "Heute" switches to swissimage.

**4.4 Credits for the new sources.** Is `license.credit` filled for every `lubis` and `nb` record (swisstopo LUBIS, Nationalbibliothek)?
Default: show `license.credit`, fall back to the source name.

**4.5 Demo cards.** 10 cards incl. 2 composites and 1 without printed place name. Which ones does the pitch actually use (the 3 for Sat 10:00), and does each have a timeline set near it so Zeitreise is not empty?

---

## 5. Frontend decisions I make myself (FYI, no answer needed)

- Tailwind v3 with `tailwind.config` as SCOPE_3 says (v4 configures in CSS); tokens as CSS variables in `app/globals.css`.
- Mock data: `npm run fixtures` copies (not symlinks; Windows), plus `frontend/mocks/` for my own extra cases.
- Types written by hand from the schemas; unknown keys ignored.
- Every fetch only in `lib/api.ts`; mock adapter replays traces with the same component as demo mode.
- Map layers are raster only, no vector style, so no glyph fonts needed offline.
- In mock mode every eval number carries a visible "Beispieldaten" marker so a fixture number never reaches a screenshot.

---

## 5. v3 asks to pass on (FRONTPAGE_PLAN section 9), state 23.10. evening

Checked against `origin/said/agent` at `cac8434` (23.10. 20:44). The frontend builds none of these; it uses the fallback.

| To | Ask | State | Frontend fallback until then |
|---|---|---|---|
| Said | `priority` filter on `/photos` | **done** (`4ef9913`), sorted by signature | (client-side `raw.priority` filter stays as a safety net) |
| Said | `/export.xlsx` (Metadaten + Methode) | **done** (`4ef9913`), also `?split=challenge&priority=1` | |
| Said | `POST /review/{id}` | **done** (`4ef9913`). Accepts `bestaetigt`, `korrigiert` and `offen`; a second POST **overwrites** (answers the plan's question). `korrigiert` needs at least one field. | |
| Said | Bulk results for the desk: `GET /results?ids=a,b,c` (or `?split=challenge&priority=1`), returning `[AnalysisResult]` or `{items: [...]}`, slim is fine (fields values + confidences, coordinates, overall, needs_review, review) | **missing**: `GET /results` without an id is 404 today | fan-out over `/results/{id}`, 6 parallel, cached in memory (`listResults`) |
| Said | `verified: true` and `inliers: n` on `similar_image` evidence (LightGlue) | **missing** | "Das Archiv kennt diesen Ort" takes the highest-score similar image and does not say "verifiziert" |
| Dijar | Offline `ch.swisstopo.pixelkarte-grau` z8 to z12 over the canton bbox, plus z13 to z16 around the demo photos, in `data/tiles/` + manifest | open | desk map blank offline, list still works |
| Dijar | QC numbers per confidence bin (`challenge_qc.jsonl` hand check) by Sat 12:00, shape agreed Sat morning | open | Nachweis shows the postcard eval only |
| Said + Dijar | Shape for the QC numbers. Frontend proposal (built, item 9): `GET /qc/summary` → `{n, municipality_correct, bins: [{bin: "<0.5" | "0.5-0.9" | ">=0.9", n, correct}], cost_usd_per_photo, created_at}`; a static JSON with the same keys works too | open | QC block hidden, postcard eval only |
| Said | Reset of reviews for demo re-runs: `/review` writes into the cached results, so the demo changes `data/results/` | open | re-copy `data/results/` before each run |
