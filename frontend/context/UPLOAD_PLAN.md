# Upload plan: Hochladen, Analyse, Prüfen, Export

The desk shows SG.CIV.17 after the agent processed it. The product the archive needs is the step before it:
"I drop my folder or ZIP, check the uncertain photos, and get the Excel." This plan adds that flow without
throwing the desk away: the desk becomes the overview of **one batch** (Stapel), and SG.CIV.17 is one batch
among others.

```
 1 Hochladen  ->  2 Analyse  ->  3 Prüfen  ->  4 Export
```

Each step below has a scope, a check, and two lists we fill in while building: **Special** (decisions,
deviations, workarounds) and **Not built** (only items from that step's own scope, with the reason).

---

## Shell principle

The backend for batches is not there yet. Every step is built so it works now and switches over without a
UI change when the backend lands:

- **Mock mode** (`NEXT_PUBLIC_MODE=mock`): the whole flow runs in the browser. Uploaded images show as
  object URLs, results are the three mock challenge results in turn (sure + confirmed, Prüfung nötig,
  nicht bestimmbar), so every state of the overview is visible.
- **Live mode, today's backend**: the "client runner". The browser unpacks the ZIP, sends each image to
  `POST /analyze` (multipart `file`), at most 3 at a time, and follows the job over SSE / polling. The batch is
  remembered in `localStorage`.
- **Live mode, with `/batches`**: the "server runner". Probed once with `GET /batches`; a 404 / 405 means
  "not there yet" and the client runner takes over (same pattern as the bulk `GET /results?ids=` fallback in
  `lib/api.ts`). Nothing to switch by hand.

All backend calls stay in `lib/api.ts`; the batch logic in `lib/batches.ts`; file collection in
`lib/collect.ts`.

## Numbers (measured 24.10. on the 258 results in `agent/reports/results.zip`)

- Cost per photo: median 0.19 USD, p90 0.33 USD (budget cap 0.40, session cap 150 USD).
- Time per photo: median 54 s, p90 95 s (sum of trace `ms`).
- With 3 at a time: 50 photos take about 15 min and cost about 10 USD; 600 photos about 3 h and 115 USD.

---

## Asks for the backend (Dijar), to pass on

Proposed, not in `contracts/` yet. The frontend shell is written against exactly this.

**Fixes the client runner needs as well (most important first)**
1. **Excel `Dateiname` for uploads = the original file name** (the path inside the ZIP, as sent in the
   multipart `filename`), not `<sha1>.jpg` (`agent/server/export.py` `_file_name`). The original name is
   already in `uploads/<key>.json`. Without it the brief's "eindeutige Zuordnung zur Bilddatei" fails.
2. **Concurrency limit for jobs** (e.g. a semaphore of 3 in `agent/server/jobs.py`): 50 uploads would otherwise
   start 50 Claude calls at once and run into rate limits.
3. **Keep uploads at full resolution** (or at least 2048 px). `catalogue.save_upload` shrinks to 1024 px,
   while v6 works on full-resolution originals with crops.
4. **Known challenge photos keep their id**: when an uploaded file name (or sha1) matches a challenge
   record's `raw.file_name`, return `challenge:<signature>` instead of `upload:<sha1>`, so signature,
   priority and the cached result are kept.

**New endpoints (server runner)**

```
POST /batches                      JSON {name, skipped: [{file_name, reason}]}   -> Batch (no items yet)
POST /batches/{id}/files           multipart, field "files" repeated, filename = path in the ZIP
                                   (the frontend sends chunks of 8)               -> Batch
GET  /batches                      -> Batch[]
GET  /batches/{id}                 -> Batch
POST /batches/{id}/retry           JSON {file_names?: string[]} (none = all with status error) -> Batch
GET  /export.xlsx?batch={id}       same sheets as today, rows in batch order, Dateiname = file_name
GET  /export.zip?batch={id}        images unchanged under their file_name + metadaten.xlsx
                                   (optional later: XMP sidecars with GPS / place; never modify originals)
```

```ts
type BatchItemStatus = "queued" | "uploading" | "running" | "done" | "error" | "skipped";
interface BatchItem {
  file_name: string;          // path inside the ZIP or folder, the Excel key
  size: number;               // bytes
  photo_id: string | null;    // upload:<sha1> or challenge:<sig>, once stored
  job_id: string | null;
  status: BatchItemStatus;
  error: string | null;       // German, for error / skipped
}
interface Batch {
  id: string;
  name: string;
  created_at: string;         // ISO
  runner: "server" | "client";
  items: BatchItem[];         // upload order
  cost_usd?: number | null;
}
```

The server keeps the queue (survives a closed tab), applies the concurrency limit, and stops the batch when
the session budget is hit (remaining items: status `error`, error "Kostenlimit erreicht ...").

---

## Step 1: Data layer (api, batch store, file collection)

**Scope:** types `Batch` / `BatchItem`; `lib/collect.ts` (ZIP unpacking in the browser with `fflate`, folder
drop, filter of non-images); `lib/api.ts` additions (`uploadPhoto`, mock uploads, `/batches` endpoints with
404 fallback); `lib/batches.ts` (store with `useBatches()`, client runner with 3 parallel jobs, server runner
polling, `localStorage`, estimate). No UI.

**Check:** `npm run typecheck` and `npm run build` pass; `collectImages` on a test ZIP returns the images
with their paths and lists the rest as skipped. Done (24.10.): typecheck and build pass. Node smoke tests
(scratchpad, not committed): two ZIPs with a folder entry, `__MACOSX`, `.DS_Store`, HEIC, a nested ZIP, a TIFF
and a duplicate path, plus a loose PNG, a PDF, a broken ZIP and `Thumbs.db` give 5 images in natural order
(`IMG_2` before `IMG_10`) and 6 skipped with reasons, junk dropped silently. Client runner in mock mode: 8
images + 1 skipped, never more than 3 in flight, the 7th fails, "Erneut versuchen" brings it to 8 done.

**Special**
- `fflate` 0.8.2 for the ZIP (small, async unzip). A ZIP is read into memory whole, so above 1.5 GB it is
  skipped with "bitte aufteilen oder den Ordner ziehen"; a dropped folder has no limit.
- `PickedFile` carries `file_name` next to the Blob instead of relying on `File.name`, which may not keep
  "/" in every browser. A dropped folder gets the same path shape as `webkitdirectory` (`filesFromDrop`).
- Accepted: jpg, jpeg, png, tif, tiff, webp (what PIL reads in the backend). HEIC is skipped with the hint
  to export as JPEG. Junk (`__MACOSX`, `._*`, `.DS_Store`, `Thumbs.db`) is dropped silently; everything else
  shows as skipped with a German reason. The same path twice: the first wins, the second is skipped.
- No env flag for the runner: `serverBatches()` probes `GET /batches` once; 404 / 405 = client runner. A
  backend that is down is probed again next time.
- Client runner: 3 in flight over all batches, oldest batch first. Files live in memory only; after a reload
  queued / uploading items turn into "Upload unterbrochen", running jobs are followed again, and a job the
  backend forgot (restart) still counts as done when `GET /results/{id}` has a result.
- "Kostenlimit" and "API-Schlüssel" errors stop the rest of the batch at once (they hit every photo).
- `followAnalysis` now writes a finished result into the result cache: lists that asked before the job
  ended had cached `null` and would never show the photo. Mock mode got its own job branch there.
- Batch cost is the sum of `usage.cost_usd`. A cache hit (same image uploaded again) counts the cost of
  the original run again, so the number can be too high.
- Mock mode: uploads stay in memory with object URLs (the mock desk shows the real image), results are the
  three mock challenge results in turn, every 7th mock job fails once. Mock batches are not kept over a
  reload.
- Server runner (shell for the proposed `/batches`): chunks of 8, our placeholders are merged with each
  answer, polling every 2 s while something runs, skipped files are sent along at creation. Retry sends
  files that never arrived again and asks the server to requeue the rest.
- `exportXlsxUrl` takes `batch`, and `exportZipUrl(batch)` exists, ready for step 5.

**Not built**
- Server runner is typechecked only: there is no `/batches` yet to test against.
- Client runner not run against the live backend (real Claude calls cost money); first live test in step 3
  with 2 to 3 photos.
- No automatic retry on "Zu viele Anfragen": the item fails and "Erneut versuchen" is manual.

---

## Step 2: Start page `/`: Hochladen + Stapel

**Scope:** drop zone (ZIP, several images, a whole folder) plus file picker; preview before the start
("48 Bilder · 2 übersprungen · ca. 15 Min. · ca. 9 USD") with the skipped files listed; name field; button
"Analyse starten". Under it the batch cards, SG.CIV.17 Prio 1 as the first one ("Beispiel: bereits
verarbeitet"). The current desk moves to `/stapel/[id]`. Header: the step strip instead of the search
field (the search moves into the desk panel).

**Check:** in mock mode a ZIP with 5 images plus a .txt shows "5 Bilder · 1 übersprungen", starts, and opens
`/stapel/<id>`; `/stapel/challenge` shows today's desk unchanged. Done (24.10.), headless Chrome over CDP
against the mock dev server: a ZIP "Brunnen Schwyz.zip" (5 JPEGs in a folder, `notizen.txt`, `__MACOSX`) shows
"5 Bilder · 1 übersprungen", the name "Brunnen Schwyz", `notizen.txt` with its reason; "Analyse starten" opens
`/stapel/local-...`, the strip shows "2 Analyse" while it runs and "3 Prüfen" when 5 of 5 are done; the start
page then lists the batch card next to SG.CIV.17. `/stapel/challenge` shows the desk with the search in the
panel, no footer. Phone 390 px: no horizontal scroll, strip as "1/4 · Hochladen". No console errors.
`npm run typecheck` and `npm run build` pass.

**Special**
- The desk moved unchanged from `app/page.tsx` to `components/desk/Arbeitsplatz.tsx`; `app/stapel/[id]`
  renders it for the id `challenge` and `BatchView` for every other id. All links to `/` and `/?foto=` (desk
  reset link, analyse back button and breadcrumb) go through `deskHref()` in `lib/format.ts`
  (`CHALLENGE_DESK = "/stapel/challenge"`).
- Header: the step strip "1 Hochladen > 2 Analyse > 3 Prüfen > 4 Export" replaces the search field. The step
  comes from the route: `/` = 1, an upload batch = 2 while it runs and 3 after, the desk and the photo view
  = 3, Nachweis = none. Hochladen links to `/`, Analyse / Prüfen to the current batch, Export downloads that
  batch's Excel until the dialog of step 5 exists. The red underline marks the current step (no number
  circles: the theme has no pill radius). Phone: "2/4 · Analyse" as text, menu with "Hochladen und Stapel".
- The header Excel button is contextual: none on `/`, the batch Excel on an upload batch (once something
  is done), the SG.CIV.17 Prio-1 Excel as before on the desk, photo view and Nachweis.
- The search moved into the desk panel (`DeskSearch.tsx`, full width above Prio 1 | Alle), same `?q=` and
  ⌘K behaviour.
- Footer hidden on `/stapel/challenge` (the desk fits one viewport), shown on the start page and batches.
- Upload preview: up to 12 thumbnails (object URLs, freed on change), count, skipped files in a
  `<details>`, estimate (mock: "Beispieldaten: keine echte Analyse, keine Kosten"; live also says that cache
  hits cost nothing), name proposal from the ZIP or folder name (kept once edited), "Weitere Dateien" adds to
  the selection (everything is read again, so a ZIP is unpacked twice). The "Fenster offen lassen" note shows
  only for the client runner.
- The SG.CIV.17 card reads only the records (`listChallenge`), not the 50 results, to keep the start page
  light: "N Fotos · 50 Prio 1 · Beispiel: bereits verarbeitet".
- Batch card "×" asks with `window.confirm` and only forgets the batch in this browser.
- `useBatches()` now returns `{ batches, ready }`, so a batch page shows "Lade Stapel ..." instead of
  flashing "nicht gefunden" before localStorage and the server answered.
- `BatchView` is the first version of step 3: progress line, bar, list with status, error, Öffnen and
  Erneut versuchen, Excel button. Cost is hidden in mock mode (mock results carry made-up costs).

**Not built**
- Drag and drop of a folder is only covered by the code path (`filesFromDrop`); the headless test used the
  file input. Needs one manual drop test in Chrome and Edge.

---

## Step 3: `/stapel/[id]` while the analysis runs

**Scope:** progress line ("23 von 48 · noch ca. 6 Min. · 4.20 USD"), a grid of thumbnails that colour in
(wartet / läuft / sicher / Prüfung nötig / nicht bestimmbar / Fehler), "Erneut versuchen" for errors, a
note when the tab must stay open (client runner). Done photos can be opened and reviewed while the rest
still runs.

**Check:** mock batch of 10: the grid fills in, an error item can be retried, a reload during the run keeps
the done items (live) and marks interrupted uploads.

**Special**
-

**Not built**
-

---

## Step 4: Auswertung: the desk for one batch

**Scope:** the desk (`app/page.tsx` today) takes its records from the batch instead of `listChallenge()`:
`Prio 1 | Alle` only for the challenge batch, counters, sort "unsicher zuerst" and map stay. Main button
"12 unsichere prüfen": opens `/analyse/[id]?stapel=<id>` and the review queue walks only the photos of that
batch that need review; at the end back to the overview with the export at hand. Toggle **Karte | Tabelle**
(table = the Excel columns, per-field confidence, Prüfung nötig).

**Check:** a mock batch of 6: the counters match, "unsichere prüfen" walks exactly the uncertain ones,
Bestätigen / Korrigieren update the counters at once.

**Special**
-

**Not built**
-

---

## Step 5: Export dialog

**Scope:** the export button shows the state ("Excel herunterladen · 41/48 geprüft"); dialog with Excel
(sheets Metadaten + Methode), CSV, "ZIP: Originalbilder + Excel" (server runner only, greyed out with a
reason otherwise), option "nur geprüfte" or "alle, mit Prüfstatus". Client runner: `export.xlsx?ids=...`;
server runner: `?batch=`.

**Check:** mock: the CSV fixture downloads; live: the Excel of a 3-photo upload has the original file names.

**Special**
-

**Not built**
-

---

## Step 6 (optional): table view polish and pitch path

**Scope:** sortable table columns, inline correction in the table, a prepared demo ZIP (run once before the
pitch, so the live upload hits the sha1 cache and is done at once).

**Check:** demo ZIP upload on the pitch machine finishes in under 10 s.

**Special**
-

**Not built**
-
