# Build notes

One section per build step (`docs/SCOPE_3_FRONTEND.md`, Build order). Each step lists what is special about it (decisions, deviations, workarounds) and what of **that step's own scope** was left out, with the reason. Work that belongs to a later step is not listed. Open team questions live in `OPEN_FRONTEND_QUESTIONS.md`; this file links to them by number.

Keep appending: a new section per step, and update an older section when something from it gets built later (mark it "done in step N").

---

## Step 1: Scaffold (22.10.)

**Check:** `npm run build` and `npm run typecheck` pass; page, fixtures and `sample.jpg` are served. Done.

**Special**
- Versions: Next.js 16, React 19, Tailwind 3.4 (SCOPE_3 asks for `tailwind.config`; v4 configures in CSS), TypeScript 5 (not 7.0, the new native compiler, Next support unproven).
- `tailwind.config.ts` replaces (not extends) colours, radius, shadows and font weights: there is no full-radius class, no shadow and no weight above 600, so the archive-look rules are enforced by the theme. If a circle is ever needed (slider thumb), use custom CSS.
- Custom type sizes: `text-page` 28, `text-section` 18, `text-body` 14, `text-meta` 12. Tailwind's default sizes (`text-sm` etc.) still exist.
- Fonts via `next/font/google`: downloaded at build time and self-hosted. Build once with internet, then it runs offline.
- `next.config.ts`: `images.unoptimized`; images are plain `<img>` from the backend (or fixtures), no next/image pipeline.
- `npm run fixtures` copies (not symlinks, Windows) `contracts/fixtures/` to `public/fixtures/`; runs automatically before `dev` and `build`; output gitignored.
- `lib/api.ts`: every endpoint of CONTRACTS section 5 except `/analyze` (+ SSE) and `/tiles`. IDs go through `encodeURIComponent` (crop ids contain `#`, question 3.2). Relative backend URLs are prefixed with `NEXT_PUBLIC_API_URL` via `absolute()` (question 3.15). `getResult` and `getEvalSummary` return `null` on 404.
- `replayTrace()` in `lib/api.ts` is shared by mock and demo mode: one step per recorded `ms`, clamped to 600 to 1500 ms.
- `lib/types.ts` written by hand from the schemas. `Evidence.kind` and `TraceItem.type` also accept any string (question 3.7). `needsReview()` treats both `status: "needs_review"` and `needs_review: true` as "Prüfung nötig" (question 3.5).
- Mock mode: `getHealth` returns the swisstopo WMTS base and `offline: false`; `imageUrl` returns `sample.jpg` for every id; `exportUrl` returns the CSV fixture for both formats (no JSON fixture, question 3.13). Replaced by `downloadExport()` in step 6.

**Not built**
- Nothing from the step's scope.

---

## Step 2: Archiv grid (22.10.)

**Check:** cards with title + muted meta line, undated first. Done (headless screenshots at 1440 and 390 px).

**Special**
- Order: `/demo` cards first in pitch order, then `/photos?split=showcase`, undated before dated (stable sort keeps the backend order inside each group). Default from question 2.5.
- `mocks/photos.ts`: 10 invented records (`stasz:mock-01` .. `-10`, signatures `SG.CIV.12.M001` etc.), all with the fixture image, 3 of them dated. Mock-only, never in `contracts/`. Mock demo list = 3 of them. The contract fixture record (`split: "reference"`) is reachable by id but not in the grid.
- Mock `listPhotos` filters `split`, `municipality` and `q` (title + signature, my guess for question 3.10) and pages with `limit` / `offset`.
- Paging: 48 per page, "Weitere Karten laden" button when `total` is larger. The count line uses `total` from `/photos`.
- If `/demo` fails, the grid still loads from `/photos` alone.
- Card image: `object-contain` on a `paper-2` mat with a 3:2 box, so postcards of any ratio are not cropped. Hover darkens the mat and colours the title `--accent`, no shadow.
- Site header (`components/SiteHeader.tsx`, in the layout): "Zeitreise Schwyz", "Archiv", and a "Beispieldaten" marker in mock mode only.

**Not built**
- Upload button (named in the Archiv view spec): on the SCOPE_3 cut list, waits for question 2.6.

---

## Step 3: Analyse view (22.10.)

**Check:** renders the fixture AnalysisResult completely. Done (headless screenshots: normal result, low-confidence variant, replay running, unknown id).

**Special**
- `/analyse/[id]` is the "Ort & Zeit" screen in the team mock's layout (default of questions 2.1 / 2.10): left column for map and Zeitreise, right column photo, result, trace. On narrow screens the right column comes first. Until step 4 the left column is a `paper-2` panel with the coordinates in mono.
- Confidence is the mono number (`0.82`) plus the 60px 2px bar, not a percentage (question 2.2). Below 0.5: bar, number and an inline "Prüfung nötig" turn `--warn`.
- Header line "Gesamt 0.76" (question 2.3), plus "· Prüfung nötig" when `needsReview()` and "· Budget erreicht" when `usage.budget_hit`.
- Jahrzehnt row shows `year_range` too: "1900er · 1898 bis 1907" (question 2.4). Rejected hypotheses on `year_range` are filed under that row.
- Each row expands (chevron, `aria-expanded`) to its evidence: "dafür" / "dagegen" (dagegen in `--warn`), summary, German kind label, score in mono, "Quelle" link when `url` is set. Rejected values show as a muted "Verworfen: Flüelen, Sisikon" line under the row and with their reasons when expanded. All rejected hypotheses are also in a collapsed "Verworfene Hypothesen (n)" section (view 2 spec).
- German labels for fields, evidence kinds (incl. the date_hints kinds, question 3.7) and tool names in `lib/labels.ts`; unknown keys show raw.
- Replay: in mock and demo mode the trace replays step by step and nothing of the result (fields and map coordinates) shows until it ends, so the demo never spoils itself. "Überspringen" cancels the replay and shows everything. Live mode shows a cached result and its full trace at once (no replay); a new analysis streams (done in step 8).
- Trace log is a `<details>` open by default ("Analyse läuft" while replaying, then "Analyseschritte (n)"), so it never jumps or remounts when the replay ends.
- IDs from the URL are decoded with `decodeURIComponent`; a crop-style id (`%231`) round-trips correctly. Unknown id: "Dieses Foto gibt es nicht."
- `mocks/results.ts`: `stasz:mock-02` gets a low-confidence variant (Gemeinde 0.44, Ort unknown 0.20, Jahrzehnt 0.32, `needs_review: true`, one "dagegen" evidence, matching final trace line). Mock `getResult` also sets `photo_id` to the requested id.
- No result yet (`/results` 404): "Für dieses Foto liegt noch keine Analyse vor."
- Fixed after Timo's report: in `npm run dev`, StrictMode runs effects twice and both responses started a replay, so every trace step appeared twice ("same key" warnings). The effect now marks its run stale in the cleanup and ignores late responses. Lesson: check new views against the dev server too, not only the production build (Next 16 allows one dev server per folder, so use the one already running on :3000).

**Not built**
- Evidence `ref_id` (the referenced similar image / archive record) is not shown as a thumbnail or link; only summary, kind, score and `url`. Worth adding once real results show how often `ref_id` is set.
- Expanded evidence rows were not checked in a screenshot (needs a click); only typecheck and the collapsed state are verified.

---

## Step 4: Map (23.10.)

**Check:** fixture coordinates show on swisstopo tiles, with pin, uncertainty circle and "© swisstopo". Done (headless screenshots: result at 1440 px, replay still running).

**Special**
- MapLibre GL **5.24** (not 6.x): v6 is ESM-only and loads its worker as a separate file via `import.meta.url` at runtime, which is unproven with Turbopack and offline. v5 inlines the worker.
- `components/map/MapView.tsx` is generic (one raster layer + pin + circle), loaded with `next/dynamic`, `ssr: false`, from `components/analyse/MapPanel.tsx`. Step 9 reuses it with the zeitreihen layer; changing the `tiles` prop swaps the source via `setTiles`, a new `center` re-fits with a 400 ms ease.
- Layer in step 4: SWISSIMAGE `current` (cached offline at z12 to 17). The zeitreihen layer needs `map_years` and comes with the slider in step 9.
- Tile URLs: `getTilesUrl()` + `tileTemplate()` in `lib/api.ts`. Online WMTS shape `.../{layer}/default/{time}/3857/{z}/{x}/{y}.{ext}`, offline the backend shape `/tiles/{layer}/{time}/{z}/{x}/{y}.{ext}` (question 3.3; Said's route accepts the extension). If `/health` fails, the map falls back to swisstopo directly. Mock `tiles_url` is now `https://wmts.geo.admin.ch/1.0.0`, the same value Said's `/health` returns online.
- Offline (`/health` `offline: true`): `minZoom` 12, `maxZoom` 17, the cached range (question 4.2). Online 7 to 19. No `maxBounds` yet.
- Pin = 14 px `--accent` dot with a paper ring (custom CSS `.map-pin`, the theme has no full-radius class). Circle = `radius_m` polygon, accent line 1.5 px + 12 % fill. MapLibre paint reads the colours from the CSS variables.
- Own "© swisstopo · SWISSIMAGE" line in the bottom-right corner instead of MapLibre's attribution control (which has its own look). Zoom buttons restyled to paper + rule, no shadow. No rotation, no pitch.
- The map stays hidden until the replay ends (same rule as the result fields); the panel says "Ort wird bestimmt ...", "Keine Koordinaten" or "Keine Analyse".
- Gotcha: `maplibre-gl.css` sets `.maplibregl-map { position: relative }`, which beats Tailwind's `absolute inset-0` and gave the map height 0. The map container is sized with `h-full w-full` inside a positioned parent.

**Not built**
- Standalone `/karte`: dropped by the default of question 2.1.
- `maxBounds` around the cached areas offline: needs the area list (question 4.2). Panning far away offline shows blank tiles.
- Phone width not verified in a screenshot: headless Chrome lays out at least about 490 px wide, so the 390 px shot does not show the real phone layout.

---

## Step 5: Demo mode (23.10.)

**Check:** works with Wi-Fi off against a local backend. Partly done: checked against Said's server from `said/agent` (4fbd332) with `AGENT_FAKE=1 DATA_PIPELINE_STUB=1 AGENT_OFFLINE=1`, frontend built with `NEXT_PUBLIC_MODE=demo` (`next start`). Archiv from `/demo` + `/photos`, image from `/images`, result from `/results` replayed, map tiles requested from `/tiles/...` in the right shape, "Erneut abspielen" restarts. The real offline run on the M4 Air with Dijar's `data/` (cached results + tiles) is still open; there is no `data/` on Timo's laptop, so tiles were 404 here.

**Special**
- Replay pacing: each step's recorded ms clamped to 600 to 1500 ms as before, then scaled down so the whole replay takes at most 15 s (each step at least 250 ms). Real traces can have 20+ steps.
- Presenter links on the Analyse screen, top right: "Analyse erneut abspielen" (mock and demo mode, after the replay) and "Nächste Karte →" (next card of `/demo` in pitch order, only on demo cards).
- Backend down: `fetch` network errors become `ApiError` status 0, and `errorText()` shows "Backend nicht erreichbar (http://localhost:8000)" on Archiv and Analyse instead of "Failed to fetch".
- `NEXT_PUBLIC_MODE` and `NEXT_PUBLIC_API_URL` are inlined at build time: the demo build needs them set for `npm run build` (README).
- No header marker in demo mode (mock shows "Beispieldaten"), so the pitch looks live.
- Testing tip: headless Chrome's `--virtual-time-budget` screenshots catch MapLibre before its worker has drawn the GeoJSON (circle missing, wrong zoom). Use puppeteer-core with real waits.

**Not built**
- Nothing from the step's scope. For Said (not frontend): results are stored as `data/results/<photo_id>.json`, and ids contain `:`, which is not a valid filename character on Windows. Fine on the M4 Air, but the cache cannot be written or copied on a Windows laptop.

---

## Step 6: Export buttons (23.10.)

**Check:** the downloaded CSV opens in Excel. Done in mock mode: headless Chrome clicked every button (Archiv all, Archiv selection of 2, Analyse CSV + JSON), 5 files saved, CSVs start with the UTF-8 BOM. Excel (COM, on Timo's laptop) opens `zeitreise-schwyz_alle.csv` as 23 columns, umlauts and the `;`-joined lists inside quotes intact. Checked in step 8 against Said's real `/export.csv` (fake mode): BOM, `;`, header + one row.

**Special**
- "CSV herunterladen" / "JSON herunterladen" in one component (`components/ExportButtons.tsx`), used under the result (that photo only) and in the Archiv header.
- Archiv: a checkbox in the top-left corner of each card selects it for the export. It sits beside the card link, not inside it, so ticking never opens the card. With a selection: "Export: 3 ausgewählt · Auswahl aufheben" and only those ids are exported; without: "Export: alle analysierten Karten" (no `ids`, the backend default). The selection is only kept while the page is open.
- Download through `downloadExport()` in `lib/api.ts`: `fetch` + blob + object URL instead of a plain link. Reasons: `/export.json` would open in a browser tab instead of saving, and a cross-origin `<a download>` ignores the file name. The blob keeps the bytes as sent, so the BOM survives (`res.text()` would drop it and Excel would garble umlauts).
- File names: `zeitreise-schwyz_<photo id>.csv` (`:` and `#` replaced by `-`), `zeitreise-schwyz_auswahl-3.json`, `zeitreise-schwyz_alle.csv`.
- Empty export (none of the ids has a result, or no results yet): no file is saved, a muted line says "Für die Auswahl liegt keine Analyse vor." / "Noch keine Analysen vorhanden." The row count comes from the downloaded file itself.
- Question 3.13 answered by Said's code (`said/agent` 4fbd332): `/export.json` rows use the CSV column names as keys. Mock JSON is built from the CSV fixture the same way (all values are strings there; the real backend sends numbers).
- Mock mode always exports the single fixture row, whatever is selected.
- For Said (not frontend): his `Pruefung_noetig` only looks at `needs_review`, not at `status: "needs_review"` (question 3.5). If the agent ever sets only the status, the export says "nein" while the UI says "Prüfung nötig".

**Not built**
- The empty-export message is not seen in a test: in mock mode every id has a result.
- No production build run for this step (`npm run dev` was running in the same folder); typecheck passes.
- Excel was only tried with the laptop's own regional settings. With a decimal comma locale (de-DE) Excel may read `0.82` as text; Swiss settings (de-CH) use a point. Not a frontend fix, the file comes from the backend.

---

## Step 7: Nachweis page (23.10.)

**Check:** shows the numbers from `eval_summary.json`. Done in mock mode (headless screenshots at 1440 and 800 px, no console errors besides the missing favicon). Not checked against a real eval: Said's run is planned for Friday night.

**Special**
- `/nachweis`, linked in the site header next to "Archiv".
- Order on the page: meta line (n, model, date, cost), four big numbers (Gemeinde richtig, Jahrzehnt richtig, Jahrzehnt ±1, Fotos ausgewertet), then "Agent gegen reine Bildähnlichkeit", "Wann die Gemeinde stimmt", "Konfidenz", "Nach Gemeinde", and one "Ehrlicher Fehlerfall" at the end.
- Shares are shown as percentages ("71 %", narrow no-break space), not as `0.71` like confidences: these are measured hit rates, and the jury reads percent faster. Bars are the same 2 px ink bars as the confidence, 120 px, never amber.
- Said's eval code (`said/agent` 4fbd332, `agent/eval/summary.py`) writes more than CONTRACTS section 7: `decade_n`, `decade_posted_at_or_before`, `coord_n`, `n_eval`, `n_missing`, `mean_confidence` per calibration bin, `confidence` / `subset` per failure, and `metrics` = `data_pipeline.metrics.score()` (`all` + one entry per subset). `lib/types.ts` follows his code; all extra keys are optional, so the page also works with the plain contract shape.
- **Fixture guard:** Said's `/eval/summary` serves the made-up fixture when no eval has run yet. In live and demo mode `getEvalSummary()` treats a summary with `_fixture_note` as "no eval" and the page says "Noch keine Auswertung", so invented numbers can never reach the pitch (question 3.9). Only mock mode shows them, with an amber "Beispieldaten" line.
- "Wann die Gemeinde stimmt": printed vs not printed place name and the three subsets from `metrics` (German labels in `lib/labels.ts`: "Ansichtskarten, nicht gelaufen", "Ansichtskarten, gelaufen", "Fotos mit Aufnahmedatum"). Hidden when `metrics` is missing.
- "Konfidenz": one sentence per level from `metrics` ("Ab 0.8: 40 % der Fotos, davon 90 % richtig"), then the calibration bins as a table. The chart is step 10.
- Fehlerfall: the first entry of `failures`. Said sorts them by confidence, highest first, so it is the most confident mistake. Thumbnail, expected vs got, confidence, his German `why`, link to the Analyse screen, count of the other mistakes.
- `mocks/eval.ts` adds Said's extra keys and an invented `metrics` block to the fixture in mock mode, so every section can be built and seen.
- The baseline sentence says "x Prozentpunkte besser"; if the agent is ever worse, the number is negative (honest, but reword it then).

**Not built**
- The "Noch keine Auswertung" state and the fixture guard are not seen in a test (backend not running).
- The Fehlerfall link goes to `/analyse/<id>`; whether that page has a cached result for eval photos depends on the backend. In mock mode the fixture id `stasz:361043` does not exist, so the link shows "Dieses Foto gibt es nicht."
- Year metrics from `metrics` (median year error, range coverage, "≤ Poststempel") and `decade_posted_at_or_before` are not shown. The big decade numbers cover the year side for the jury; add them if the team wants them.

---

## Step 8: Live SSE trace (23.10.)

**Check:** steps fade in as Said's server emits them. Done against Said's server (`said/agent` 4fbd332, `AGENT_FAKE=1 DATA_PIPELINE_STUB=1`) with the frontend in live mode: headless Chrome counted one more trace line about every 300 ms (his fake delay), the result appeared only with the `result` event. Screenshots: no analysis yet, running, done.

**Special**
- **No auto-start in live mode.** Opening a photo never starts an analysis (each real run costs money and time). Cached result (`/results/{id}`): shown at once with its full trace, plus "Neu analysieren" top right (`POST /analyze?fresh=1`). No result: "Für dieses Foto liegt noch keine Analyse vor." with an "Analyse starten" button. For the pitch this extra click is also the moment the presenter starts the agent.
- Said's SSE format (`agent/server/app.py`): `event: trace` with one TraceItem, then `event: result` with the full AnalysisResult, `: ping` comments every 15 s. There is no `event: error`: a failed job ends with a `result` whose `status` is `"error"` and whose `error` is a German message (`jobs.py`, e.g. "Kein API-Schlüssel gesetzt", "Kostenlimit erreicht"). The page shows that message in `--bad` with "Erneut versuchen". Question 3.1 answered.
- `startAnalysis()` + `followAnalysis()` in `lib/api.ts`. `followAnalysis` uses `EventSource` and closes it on `result`; otherwise EventSource would reconnect after the server ends the stream and replay the job from step 1. On a stream error before the result it switches to polling `GET /analyze/{job_id}` every second (question 3.1 default). Trace items are de-duplicated by `step`, and steps from the final result that the stream missed are added.
- While the stream runs, the result and the map stay hidden ("Ort und Zeitraum werden bestimmt ...", map "Ort wird bestimmt ..."), the same rule as the replay. No "Überspringen" in live mode (nothing to skip to).
- Leaving the page or switching photos closes the stream only; the job keeps running on the server, and Said's backend shares a running job when the same photo is started again.
- Starting fails (backend down, 404, 400): "Analyse konnte nicht starten: ..." with "Erneut versuchen". Stream and polling both fail: "Verbindung zur Analyse verloren: Backend nicht erreichbar (...)"; the steps received so far stay visible. Tested by killing the backend mid-stream (fake delay raised to 1.5 s in a scratch copy of Said's code, not in the repo).
- `AnalysisResult` type gained `error` / `error_detail` (Said's `jobs.py`, not in the contract).
- Test setup: Next 16 allows one dev server per folder, and Turbopack does not follow a junctioned `node_modules`. The live test ran from a full copy of `frontend/` with its own `npm ci` on port 3001.

**Not built**
- Polling that recovers (stream breaks, backend still up) is not seen in a test; only the case where both fail.
- A real (non-fake) run with Claude is not tested: no API key and no `data/` on this laptop. Real traces are longer and slower; the log simply grows.
- Upload (`POST /analyze` with a file): on the SCOPE_3 cut list (question 2.6).

---

## Step 9: Zeitreise (23.10.)

**Check:** every year from 1864 to today shows a map; snapping never requests an invalid TIME. Done in mock mode (online swisstopo): headless Chrome set the slider to every year from 1864 to 2026 and logged every tile response. 168 tile responses, 0 errors, every requested zeitreihen TIME was in `map_years`, the "© swisstopo · ..." line was there for all 163 years. Screenshots at the start year, 1864, 1900, 1950, 2021, 2026.

**Special**
- Lives in the Analyse screen under the map (default of question 2.1), not as `/zeitreise`. The base layer of the existing map follows the slider; pin and circle stay.
- Slider runs from 1864 to the current year, step 1. Snapping (`lib/timeline.ts`, `snapToMap`): the nearest value in `map_years` (a tie goes to the earlier sheet); years after the last sheet (2021) show "Heute" = SWISSIMAGE. Only values from `map_years` are ever requested; without `map_years` (timeline failed) the map stays on SWISSIMAGE. Verified live on 23.10.: an invalid TIME (`19050101`) gets HTTP 400 from swisstopo.
- **Start year = the analysis' own estimate** (middle of `year_range`, else decade + 5), so the map first shows the time of the photo (fixture: 1903, sheet 1904). No estimate: today.
- Header line: the slider year big in mono `--accent`, then "Karte von 1904" or "Heute, Luftbild SWISSIMAGE". The map's own line says "© swisstopo · Zeitreise 1904" or "· SWISSIMAGE".
- Axis under the slider: a thin tick per map sheet, a small dot per archive photo (the nearest one in `--accent`), mono labels every 20 years. No chips.
- Archive photos of this place from `/timeline` (default radius 1000 m): the nearest to the slider year shown large (title, "1904 · signature · 420 m entfernt", archive credit, "Dieses Foto ansehen →" unless it is the photo under analysis), and below a horizontal strip of all dated ones, captioned "1904 · SG.CIV.12.xxx"; clicking one moves the slider to its year. Photo year = exact year or middle of the range; undated photos are left out (they have no place on the axis). At most 40 photos.
- Titles, signatures and credits come from `/photos/{id}` per strip photo (`TimelinePhoto` only has id, years, distance). The strip shows ids until the records arrive; missing records stay as ids (mock mode: the fixture timeline points at stasz ids that do not exist in mock).
- Images use `imageUrl(id)` instead of the timeline's `image_url`: same backend route, and mock mode gets the sample image.
- `MapView` got `tilesMaxZoom`: zeitreihen is capped at z16 (tiles past z16 are tiny / blank on swisstopo, probed on 23.10.), MapLibre scales z16 up. A source's maxzoom is fixed, so switching between SWISSIMAGE (19) and zeitreihen (16) removes and re-adds the source under the circle; between two zeitreihen years only `setTiles` runs. `raster-fade-duration` 300 ms softens the switch.
- The map follows the slider 150 ms late, so dragging across many sheets does not request every one on the way.
- Slider look: custom CSS in `globals.css` (`.zeitreise-slider`): 2 px rule track, round accent thumb like the map pin (the theme has no full-radius class).
- Online the backend only returns 12 `map_years` (its fallback list) although swisstopo has every year 1844 to 2021; offline it returns the cached ones. See question 3.4.

**Not built**
- While `/timeline` loads, the map briefly shows SWISSIMAGE before it switches to the start year's sheet (no `map_years` yet). Short, and reads as "from today back in time", so left as is.
- Not tested against Said's `/timeline` (backend not running for this step) or offline tiles (no `data/` on this laptop).
- Old sheets (1864) look very coarse at the default zoom: the original Dufour map is 1:100 000. No zoom change per sheet.
- Phone width not checked in a screenshot (same headless limit as step 4).

---

# FRONTPAGE_PLAN v3 (from 23.10. evening)

`docs/FRONTPAGE_PLAN.md` replaces the Views, Look and Build order of SCOPE_3. Sections below follow its section 10 (Build order), one per item. Steps 1 to 9 above stay as the history of the code that is kept.

## v3 item 1: Re-skin (23.10.)

**Check:** `/` and `/analyse/x` render the white/red sz.ch look; no shield anywhere; `grep -r "rounded-full"` empty. Done: headless Chrome at 1440 and 390 px on both pages: white page, red band `rgb(226, 0, 26)`, body font Barlow, browser title "Erschliessung SG.CIV.17 · Staatsarchiv Schwyz (Prototyp)", "Prototyp" tag + footer sentence present, no image named wappen/logo/shield, no horizontal scroll at 390 px, no console errors. `grep -rn "rounded-full"` over `frontend/` (without node_modules / .next) is empty.

**Special**
- Token names kept (`paper`, `ink`, `accent`, ...), values swapped to plan 2.1; new tokens `ink-strong`, `accent-hover/-dark/-light`, `cert-*`, `focus-ring`. `tailwind.config.ts` is the plan's block verbatim (still replaces Tailwind's defaults); `maxWidth.wrapper` and `transitionDuration.fade` sit in `extend` so Tailwind's other max widths keep working.
- Fonts: Barlow 300/400/500/700 (`--font-barlow`) and IBM Plex Mono 400/500 (`--font-plex-mono`) via `next/font`; Source Serif 4 and IBM Plex Sans dropped. Body 16/24.
- Class sweep for the dropped theme keys: `font-serif text-page` → `text-page` (Light 300), `font-serif text-section` → `text-h3` (Bold 700), the Zeitreise year `font-mono text-section` → `font-mono text-h3 font-normal`, Nachweis big numbers `font-serif` → `font-light`, card title `text-sm font-medium` → `text-body font-bold`. Muted links hover to black (`hover:text-ink-strong`, sz.ch) instead of red.
- `.wrapper` utility in `globals.css` (92 % wide, max 1520 px) for header, band, footer and all pages; Nachweis keeps its 1100 px reading width inside it.
- `.link` utility for red underlined body links (black on hover, 400 ms); not used yet, item 3 uses it for source links.
- Focus: global `:focus-visible` = 1 px black outline + the sz.ch blue 4 px ring (`--focus-ring`). Outlines are never removed; on the red band the outline and underline turn white.
- Header (`SiteHeader.tsx`): "Staatsarchiv Schwyz" + " · Erschliessungs-Assistent" (Light, muted; second line on phone), right "Nachweis", "Methode" (→ `/nachweis#methode`, the anchor comes with item 9) and the `Prototyp` tag (`rounded px-1.5 h-5 text-[11px]` on `paper-2`). Mock mode adds a second tag "Beispieldaten" in warn.
- Red band (`SearchBand.tsx`): white search icon (lucide, stroke 1.5), Light input with `accent-light` underline, placeholder "Signatur, Ort oder Gebäude suchen". Submitting goes to `/?q=...`; the desk list reads it in item 4.
- Footer (`SiteFooter.tsx`): `paper-2`, 2 px rule top border, 14 px, the three plan sentences joined by " · ".
- Comments that named the forbidden class were reworded so the grep check is literally empty.

**Not built**
- Pages inside keep their old structure (Archiv grid, Ergebnis panel); the plan rebuilds them in items 3 and 4. The detail map pin and uncertainty circle are now bright brand red because they use `--accent`; plan 2 says brand red never encodes data, so item 3 should recolour them.
- Header on phone is the plain wrapped version (no "[=]" menu); the phone pass is item 10.
