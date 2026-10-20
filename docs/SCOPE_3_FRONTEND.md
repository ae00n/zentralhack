# SCOPE 3: Frontend (owner: Timo)

Read `docs/CONTRACTS.md` first. Every interface named here is defined there. Work on branch `timo/frontend`.


## Goal

A German web app the jury remembers. It shows an undated archive card going in, the agent reasoning live, a pin on the map, and the same place across time. Structured metadata comes out with confidence and evidence. It runs fully offline on the M4 Air in demo mode.

## Owned folders

- `frontend/` only. Do not edit `agent/`, `data_pipeline/`, `contracts/` or `docs/CONTRACTS.md`. Propose contract changes in the team chat first.

## Stack

- Next.js (App Router, TypeScript). No Next API routes: all data comes from the FastAPI backend at `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).
- MapLibre GL JS, loaded client-only: `const Map = dynamic(() => import("./MapView"), { ssr: false })`. MapLibre needs `window`.
- Styling: Tailwind. All UI strings in German.

### swisstopo layers (verified live 2026-10-20, HTTP 200, CORS `*`, no key)

| Use | Raster tile URL (EPSG:3857) |
|---|---|
| Time slider backdrop | `https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.zeitreihen/default/{TIME}/3857/{z}/{x}/{y}.png` |
| Today (then vs now) | `https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissimage/default/current/3857/{z}/{x}/{y}.jpeg` |
| Siegfried map (optional) | `https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.hiks-siegfried/default/{YEAR}/3857/{z}/{x}/{y}.png` |

- `{TIME}` must be an exact value like `18641231`. An invalid value returns HTTP 400. Snap the slider year to the nearest value in `map_years` from `GET /timeline`. Valid values run from 1844 to 2021.
- Attribution "© swisstopo" must be visible on every map. Archive images carry their `license.credit` (for example "Staatsarchiv Schwyz, SG.CIV.12.4743").
- In demo mode, tiles come from the backend's `/tiles/{layer}/{time}/{z}/{x}/{y}` route (base from `/health` `tiles_url`), backed by `data/tiles/`. Same template, different base.

## Inputs (from whom)

| Input | From | Contract section |
|---|---|---|
| PhotoRecord lists and details, images | Agent backend (`/photos`, `/images/{id}`) | 2, 5 |
| Live agent trace (SSE) and AnalysisResult | Agent backend (`/analyze`, `/analyze/{job_id}/events`, `/results/{id}`) | 3, 5 |
| Timeline photos and valid map years | Agent backend (`/timeline`), data from Data | 4, 5 |
| Export files | Agent backend (`/export.csv`, `/export.json`) | 6 |
| Eval numbers | Agent backend (`/eval/summary`) | 7 |
| Demo card list in pitch order | Agent backend (`/demo`), data from Data | 1, 5 |

## Outputs (to whom)

- The demo itself, for the pitch and the backup video (whole team).
- Screenshots for the slides (Dijar assembles the deck).
- Bug reports on contract mismatches go to Said (API) or Dijar (data).

## Views (German labels)

1. **Archiv** (`/`): grid of showcase cards (undated ones first). Each card has a title in `text-sm font-medium` and one muted meta line like `SG.CIV.12.4743 · Entstehung: keine Angabe`. There is also an upload button.
2. **Analyse** (`/analyse/[id]`):
   - Left: the photo. Composite cards show the split parts as outlined boxes with "Teil 1 / Teil 2" tabs.
   - Middle: the live agent trace from SSE. Steps fade in; tool calls are shown as compact rows.
   - Right: the result fields (Gemeinde, Ort, Gebäude, Landschaft, Jahrzehnt, Koordinaten). Each field has a confidence bar plus a percentage, and an expandable evidence list (`summary`; supporting vs contradicting via `supports`). "Verworfene Hypothesen" sit in a collapsed section. Fields below 0.5 are marked in amber with "Prüfung nötig".
3. **Karte** (inside Analyse and standalone `/karte`): a pin at `coordinates`, plus a circle with `radius_m` to show uncertainty.
4. **Zeitreise** (`/zeitreise?lat&lon`): a year slider. The historical map backdrop (zeitreihen) changes with the year. Archive photos of this place (`/timeline`) appear on a strip at their year, and the nearest photo to the slider year is shown large. Every year has a map, so no year is empty.
5. **Damals / Heute** (`/vergleich/[id]`): the historical photo beside today's SWISSIMAGE centred on the coordinates. Optionally add a swipe divider between the Zeitreise map at the photo's decade and SWISSIMAGE.
6. **Export**: buttons "CSV herunterladen" and "JSON herunterladen" on the result and on the archive grid (selected or all).
7. **Nachweis** (`/nachweis`): the proof page. Big numbers come from `/eval/summary`: municipality accuracy, decade accuracy, decade within ±1, and n. Add the per-municipality table, a calibration chart (does confidence match accuracy?), the similarity-only baseline next to the agent, and one honest failure case.

## Design rules (owner's, non-negotiable)

- No `rounded-full` bordered pill or chip badges for status, kind or counts. Use the muted meta line: `text-xs text-muted-foreground`, with facts joined by " · ". Colour a word only when it needs attention: amber for review needed, red for error. If a tag is truly needed: `rounded px-1.5 h-5 text-[11px] bg-muted`, no border.
- Motion: simple fades and gentle easing, 300 to 500 ms. No spring, elastic or bounce.
- Calm, archival look: real photos big, chrome small. Laptop projector first, but it must not break on a phone.

## Modes

- `NEXT_PUBLIC_MODE=mock`: no backend at all. Read `contracts/fixtures/*.json` (copied or symlinked into `frontend/public/fixtures/` at build time). The SSE trace is replayed from the fixture's `trace` with timed delays.
- `NEXT_PUBLIC_MODE=live`: real backend, real `/analyze`.
- `NEXT_PUBLIC_MODE=demo`: real backend, but analysis is never triggered. The trace replays from cached `/results/{id}` with timed delays, so it looks live. Use it for the pitch and the video. It works with Wi-Fi off on the M4 Air (backend + cached results + tile cache).

## Starting point and mock strategy

- No frontend code exists yet; you build all of it.
- Fixtures are on `main` in `contracts/fixtures/` (photo_record, analysis_result, timeline, eval_summary, export.csv, sample.jpg). `npm run fixtures` copies them to `frontend/public/fixtures/`; never edit the copies.
- Wrap every fetch in one `lib/api.ts` that switches on `NEXT_PUBLIC_MODE`. Components never call `fetch` directly.
- Use the real swisstopo tiles from the start; they need no backend.
- Switch to `live` as soon as Said's server runs (his fake mode `AGENT_FAKE=1` serves the fixture over real HTTP + SSE first).

## Build order

Each item is done when its check passes.

1. **Scaffold:** Next.js + Tailwind + `lib/api.ts` in mock mode. Check: `npm run dev` shows fixture data.
2. **Archiv grid** (`/`). Check: showcase cards with title + muted meta line, undated first.
3. **Analyse view** (`/analyse/[id]`): fields, confidence, evidence, rejected hypotheses, "Prüfung nötig" in amber. Check: renders the fixture AnalysisResult completely.
4. **Map:** pin + uncertainty circle, "© swisstopo". Check: fixture coordinates show on swisstopo tiles.
5. **Demo mode:** trace replays from `/results/{id}` with timed delays. Check: works with Wi-Fi off against a local backend.
6. **Export buttons** (CSV, JSON). Check: the downloaded CSV opens in Excel.
7. **Nachweis page** (`/nachweis`). Check: shows the numbers from `eval_summary.json`.
8. **Live SSE trace** in live mode. Check: steps fade in as Said's server emits them.
9. **Zeitreise** slider with zeitreihen + `/timeline`. Check: every year from 1864 to today shows a map; snapping never requests an invalid TIME.
10. **Damals / Heute**, then the composite split view, then the calibration chart, then the swipe divider.

## Event days (Fri 23 Oct 19:00 to Sat 24 Oct 17:00)

- Fri 23:00 checkpoint: merge `timo/frontend` into `main`; the UI hits Said's real `/photos` and `/results/{id}`.
- Sat 10:00 checkpoint: end to end on 3 demo cards in live mode; demo mode replay works.
- Sat morning: offline test on the M4 Air (Wi-Fi off); fix contract mismatches.
- Sat 14:00 code freeze: record the backup demo video; bug fixes only after this.
- Sat 17:00: submission and pitch (you drive the live demo).

## Definition of done

- Demo flow works in demo mode with Wi-Fi off: Archiv, then an undated card, then Analyse (trace replays, fields with confidence and evidence), then map pin, then Zeitreise 1864 to today, then Damals/Heute, then CSV export.
- The Nachweis page shows the real eval numbers from `/eval/summary`.
- "© swisstopo" and archive credits are visible wherever tiles or archive images are shown.
- No pill badges, no bouncy motion, all UI text in German.

## Cut first if time runs out

1. Swipe divider (keep plain side by side)
2. Calibration chart (keep the big numbers)
3. Upload of new photos (demo uses pre-picked cards only)
4. Siegfried layer (zeitreihen alone is enough)
5. Live mode polish (demo mode is what the jury sees)
