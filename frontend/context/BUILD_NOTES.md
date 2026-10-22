# Build notes

One section per build step (`docs/SCOPE_3_FRONTEND.md`, Build order). Each step lists what is special about it (decisions, deviations, workarounds) and what of **that step's own scope** was left out, with the reason. Work that belongs to a later step is not listed. Open team questions live in `OPEN_FRONTEND_QUESTIONS.md`; this file links to them by number.

Keep appending: a new section per step, and update an older section when something from it gets built later (mark it "done in step N").

---

## Step 1: Scaffold (22.10.)

**Check:** `npm run build` and `npm run typecheck` pass; page, fixtures and `sample.jpg` are served. Done.

**Special**
- Versions: Next.js 16, React 19, Tailwind 3.4 (SCOPE_3 asks for `tailwind.config`; v4 configures in CSS), TypeScript 5 (not 7.0, the new native compiler, Next support unproven).
- `tailwind.config.ts` replaces (not extends) colours, radius, shadows and font weights: there is no `rounded-full`, no shadow and no weight above 600, so the archive-look rules are enforced by the theme. If a circle is ever needed (slider thumb), use custom CSS.
- Custom type sizes: `text-page` 28, `text-section` 18, `text-body` 14, `text-meta` 12. Tailwind's default sizes (`text-sm` etc.) still exist.
- Fonts via `next/font/google`: downloaded at build time and self-hosted. Build once with internet, then it runs offline.
- `next.config.ts`: `images.unoptimized`; images are plain `<img>` from the backend (or fixtures), no next/image pipeline.
- `npm run fixtures` copies (not symlinks, Windows) `contracts/fixtures/` to `public/fixtures/`; runs automatically before `dev` and `build`; output gitignored.
- `lib/api.ts`: every endpoint of CONTRACTS section 5 except `/analyze` (+ SSE) and `/tiles`. IDs go through `encodeURIComponent` (crop ids contain `#`, question 3.2). Relative backend URLs are prefixed with `NEXT_PUBLIC_API_URL` via `absolute()` (question 3.15). `getResult` and `getEvalSummary` return `null` on 404.
- `replayTrace()` in `lib/api.ts` is shared by mock and demo mode: one step per recorded `ms`, clamped to 600 to 1500 ms.
- `lib/types.ts` written by hand from the schemas. `Evidence.kind` and `TraceItem.type` also accept any string (question 3.7). `needsReview()` treats both `status: "needs_review"` and `needs_review: true` as "Prüfung nötig" (question 3.5).
- Mock mode: `getHealth` returns the swisstopo WMTS base and `offline: false`; `imageUrl` returns `sample.jpg` for every id; `exportUrl` returns the CSV fixture for both formats (no JSON fixture, question 3.13).

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
- Replay: in mock and demo mode the trace replays step by step and nothing of the result (fields and map coordinates) shows until it ends, so the demo never spoils itself. "Überspringen" cancels the replay and shows everything. Live mode shows the full trace at once until step 8.
- Trace log is a `<details>` open by default ("Analyse läuft" while replaying, then "Analyseschritte (n)"), so it never jumps or remounts when the replay ends.
- IDs from the URL are decoded with `decodeURIComponent`; a crop-style id (`%231`) round-trips correctly. Unknown id: "Dieses Foto gibt es nicht."
- `mocks/results.ts`: `stasz:mock-02` gets a low-confidence variant (Gemeinde 0.44, Ort unknown 0.20, Jahrzehnt 0.32, `needs_review: true`, one "dagegen" evidence, matching final trace line). Mock `getResult` also sets `photo_id` to the requested id.
- No result yet (`/results` 404): "Für dieses Foto liegt noch keine Analyse vor."
- Fixed after Timo's report: in `npm run dev`, StrictMode runs effects twice and both responses started a replay, so every trace step appeared twice ("same key" warnings). The effect now marks its run stale in the cleanup and ignores late responses. Lesson: check new views against the dev server too, not only the production build (Next 16 allows one dev server per folder, so use the one already running on :3000).

**Not built**
- Evidence `ref_id` (the referenced similar image / archive record) is not shown as a thumbnail or link; only summary, kind, score and `url`. Worth adding once real results show how often `ref_id` is set.
- Expanded evidence rows were not checked in a screenshot (needs a click); only typecheck and the collapsed state are verified.
