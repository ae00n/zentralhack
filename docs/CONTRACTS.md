# CONTRACTS: single source of truth

Every scope builds against this file. Change it only when all three agree (say it in the team chat first), then update the JSON Schemas in `contracts/schemas/` and the fixtures in `contracts/fixtures/` in the same commit.

Owners: Data = Dijar (`data_pipeline/`), Agent = Said (`agent/`), Frontend = Timo (`frontend/`).

> [!IMPORTANT]
> **v3 (Fri 23 Oct, after the detailed brief).** The task is the ~600 handed-out 21st-century photos (`SG.CIV.17.*`, 50 of them "Prio 1"), not old postcards. Required per photo: one Excel row keyed by file name with Ortschaft, Gemeinde, Gebaeude, See/Fluss/Berg, Strasse (in that priority), a confidence per row with an explained method, and unknowns left open. Dating is not asked (EXIF has the capture date). Read `docs/CHALLENGE_BRIEF.md` first. v3 adds: source/split `challenge`, fields `locality` + `street`, `confidence_explanation`, `review`, functions `address_lookup` + `named_buildings`, `.xlsx` export, `POST /review`.

Conventions:
- IDs are strings `"<source>:<source_id>"`, e.g. `stasz:514200`, `smapshot:2772`, `epics:LBS_MH01-001467`, `lubis:368701`, `nb:EAD-WEHR-20678-B`, `challenge:SG.CIV.17.3`, `upload:7f3c...`. Crops of a composite card get `stasz:514200#1`, `#2`.
- Coordinates: WGS84 `lat`/`lon` everywhere in JSON. The export adds Swiss LV95 (`E`, `N`) because the archive and swisstopo use it.
- Confidence is a float `0.0` to `1.0`.
- Years are integers. A decade is the first year of the decade (`1910` = 1910s).
- User-facing strings produced by the agent (evidence summaries, reasons) are **German**. Field names and code are English.
- Every JSON object may carry extra keys; consumers must ignore unknown keys.

## 1. Data on disk (`data/`, gitignored, produced by Data)

```
data/
  records/staatsarchiv.jsonl   one PhotoRecord per line
  records/smapshot.jsonl
  records/epics.jsonl
  records/lubis.jsonl          swisstopo LUBIS ground photos (exact capture day, camera station)
  records/nb.jsonl             Swiss National Library Photoglob-Wehrli + Zinggeler photos (Commons, public domain)
  records/challenge.jsonl      the 603 handed-out challenge photos (50 Prio 1 + 553), NOT in all.jsonl, NOT in any index
  records/all.jsonl            merged, deduplicated (Smapshot + E-Pics joined on E-Pics file name; LUBIS beats its Smapshot copy)
  images/<source>/<source_id>.jpg   max 1024 px long edge, watermark strip cropped (stasz); challenge: images/challenge/SG.CIV.17.3.jpg, EXIF rotation applied
  challenge/                   the unpacked SharePoint zip as handed out (full resolution originals, brief .docx, slides)
  index/<model>.faiss          FAISS IndexFlatIP over L2-normalised embeddings
  index/<model>.ids.json       row -> PhotoRecord id
  index/<model>.meta.json      {model, dim, n, created_at}   models: clip, dinov2, megaloc
  index/year_probe.pkl         CLIP year probe used by date_hints (eval cards left out of training)
  splits/eval.jsonl            {id, subset, municipality, year_from, year_to, approximate, year_is_upper_bound}  (ground truth, frozen)
  splits/showcase.jsonl        {id}  undated / unlocated cards for the demo
  splits/timeline_sets.json    [{place, lat, lon, ids:[...sorted by year]}]
  splits/demo.json             [{id, why}]  pre-picked, pre-tested demo cards
  splits/stats.json            counts per municipality / decade / source
  gazetteer/gemeinden.json     [{name, bfs_nr, lat, lon, aliases:[...]}]  Kanton Schwyz municipalities
  gazetteer/buildings.json     named OSM places in Kanton Schwyz (named_buildings reads it)
  results/<photo_id>.json      cached AnalysisResult (written by Agent; frontend demo mode reads these)
  tiles/                       offline swisstopo tile cache for the demo area (Friday)
```

## 2. PhotoRecord

```jsonc
{
  "id": "stasz:514200",
  "source": "staatsarchiv",            // staatsarchiv | smapshot | epics | lubis | nb | challenge | upload
  "source_id": "514200",
  "source_url": "https://query.staatsarchiv.sz.ch/detail.aspx?ID=514200",
  "signature": "SG.CIV.12.4743",       // Signatur, null if none
  "collection": "SG.CIV.12",           // subcollection or E-Pics/Smapshot collection name
  "kind": "postcard",                  // postcard | aerial | ground | unknown
  "title": "Oberarth mit Gasthaus Engel",
  "date": {
    "raw": "1914",                     // verbatim: "1914" | "keine Angabe" | "ca. 1915" | "05.07.1947 - 05.07.1947"
    "year_from": 1914,                 // null if unknown
    "year_to": 1914,
    "approximate": false
  },
  "places": ["Oberarth", "Arth"],      // Thema tags verbatim, split on ";"
  "municipality": "Arth",              // canonical Gemeinde from gazetteer, null if not resolvable
  "location": {                        // null if unknown
    "lat": 47.06, "lon": 8.53,
    "method": "thema_gazetteer",       // smapshot_pose | epics_geo | thema_gazetteer | lubis_station | exif_gps
    "precision_m": 2000
  },
  "camera": null,                      // Smapshot and LUBIS: {lat, lon, altitude_m, azimuth, tilt, roll, focal}
  "photographer": null,
  "license": {
    "code": "stasz-private",           // stasz-private | CC-BY-SA-4.0 | PDM | ...
    "credit": "Staatsarchiv Schwyz, SG.CIV.12.4743",
    "url": null
  },
  "image": { "path": "images/staatsarchiv/514200.jpg", "width": 767, "height": 476, "sha1": "..." },
  "parent_id": null,                   // set on crops of a composite card
  "crop_bbox": null,                   // [x, y, w, h] in parent pixels
  "split": "eval",                     // eval | showcase | reference | challenge | none
  "raw": { }                           // all source fields verbatim (e.g. Staatsarchiv labels)
}
```

Ground truth for evaluation = `municipality` (from Thema) and `date.year_from/year_to`.

### Challenge photos (`records/challenge.jsonl`, v3)

```jsonc
{
  "id": "challenge:SG.CIV.17.3", "source": "challenge", "source_id": "SG.CIV.17.3", "signature": "SG.CIV.17.3",
  "collection": "SG.CIV.17", "kind": "ground", "title": null, "places": [], "municipality": null,   // unknown: that is the task
  "date": { "raw": "24.02.2005", "year_from": 2005, "year_to": 2005, "approximate": false },        // EXIF DateTimeOriginal
  "location": null,                    // only 1 of 603 has real EXIF GPS (method exif_gps)
  "split": "challenge",
  "raw": {
    "file_name": "SG.CIV.17.3.jpg",    // the Excel key (Dateiname)
    "priority": 1,                     // 1 = Prio-1 set of 50, 2 = "Nice to have"
    "exif": { "datetime": "2005:02:24 10:39:27", "make": "NIKON CORPORATION", "model": "NIKON D1X", "focal_mm": 17.0, "focal_35mm": 25, "lat": null, "lon": null },
    "session": ["challenge:SG.CIV.17.408"],   // same camera, under 30 min apart: usually the same place
    "original_size": [3008, 1960]
  }
}
```

Never part of the reference index, so `similar_images` never returns a challenge photo. There is no ground truth for them; QC is a hand-checked sample (`splits/challenge_qc.jsonl`, see CHALLENGE_BRIEF).

### Eval set (`splits/eval.jsonl`, frozen, 350 items)

| subset | items | year truth |
|---|---|---|
| `card_exact` | 150 unposted SG.CIV.12 cards with an exact year | exact year |
| `card_posted` | 100 posted cards | `year_is_upper_bound: true`: the catalogue year is often the postmark, so the photo is from that year or earlier |
| `photo_dated` | 100 LUBIS + NB Wehrli photos with a capture date | exact year |

Every eval run is scored with `data_pipeline.metrics.score(predictions)` so all numbers are comparable.

## 3. AnalysisResult (produced by Agent)

```jsonc
{
  "photo_id": "stasz:514189",
  "run_id": "2026-10-23T21:14:02Z-ab12",
  "status": "done",                    // queued | running | done | needs_review | error
  "model": "claude-opus-5-5",
  "composite": {                       // null if single photo
    "is_composite": true,
    "parts": ["stasz:514189#1", "stasz:514189#2"]   // each part has its own AnalysisResult
  },
  "fields": {                           // v3 order = the archive's priority: locality, municipality, buildings, landscape_features, street
    "locality":           { "value": "Schwyz",               "confidence": 0.86, "evidence": [] },   // Ortschaft (official PLZ locality, e.g. Brunnen in Ingenbohl)
    "municipality":       { "value": "Schwyz",               "confidence": 0.86, "evidence": [ /* Evidence */ ] },
    "place":              { "value": "Hauptplatz",            "confidence": 0.71, "evidence": [] },
    "buildings":          { "value": ["Pfarrkirche St. Martin", "Rathaus"], "confidence": 0.80, "evidence": [] },
    "landscape_features": { "value": ["Grosser Mythen", "Kleiner Mythen"],  "confidence": 0.90, "evidence": [] },
    "decade":             { "value": 1900,                    "confidence": 0.55, "evidence": [] },
    "year_range":         { "value": { "from": 1898, "to": 1912 }, "confidence": 0.55, "evidence": [] },
    "coordinates":        { "value": { "lat": 47.0207, "lon": 8.6541, "radius_m": 300 }, "confidence": 0.70, "evidence": [] },
    "street":             { "value": "Grundstrasse 32",       "confidence": 0.60, "evidence": [] }    // v3: street + number when known, else street only, else null
  },
  // v3: a field that cannot be determined has value null (or []) and confidence 0. Never guess a name.
  // decade / year_range are optional in v3 (challenge photos carry the EXIF date in the record).
  "overall_confidence": 0.74,
  "confidence_explanation": "Gemeinde und Gebäude durch 3 unabhängige Quellen bestätigt ...",   // v3, German, how the number came about
  "needs_review": false,               // v3: true when overall_confidence < 0.9 (Ralph's acceptance line) or locality/municipality is null
  "review": null,                      // v3: {status: offen|bestaetigt|korrigiert, fields: {name: value}, note, reviewed_at}, set by POST /review
  "rejected_hypotheses": [
    { "field": "municipality", "value": "Brunnen", "reason": "Mythen aus falschem Winkel; Seeufer fehlt" }
  ],
  "trace": [                           // agent steps for the live reasoning view
    { "step": 1, "type": "thought", "text": "Zwei Gipfel links, Kirchturm mit Spitzhelm ...", "ms": 0 },
    { "step": 2, "type": "tool_call", "tool": "similar_images", "input": { "k": 8 }, "output_summary": "5 von 8 Treffern in Schwyz", "ms": 410 }
  ],
  "usage": { "input_tokens": 28100, "output_tokens": 2900, "cost_usd": 0.085, "budget_hit": false },   // budget_hit: per-photo cost guard forced a final answer
  "created_at": "2026-10-23T21:14:09Z"
}
```

### Evidence

```jsonc
{
  "kind": "similar_image",     // visual_cue | text_on_card | similar_image | archive_record | swisstopo_place | terrain | map_layer
                               // v3: address_register | named_building | exif | session_photo
  "summary": "Referenzfoto ETH Mittelholzer 1931 zeigt dieselbe Kirchturmsilhouette",   // German, one sentence
  "ref_id": "smapshot:2772",   // optional PhotoRecord id
  "url": null,                 // optional external link
  "score": 0.83,               // optional similarity / match score
  "supports": true             // false = evidence against the value
}
```

## 4. Python interfaces (Data provides, Agent calls)

Importable from `data_pipeline` (installed in the shared venv). Agent must not read `data/` files directly except `results/`.

```python
def get_record(photo_id: str) -> dict | None: ...                         # PhotoRecord
def similar_images(image_path: str, k: int = 8, model: str = "best",
                   exclude_ids: list[str] = (), sources: list[str] | None = None,
                   verify: bool = False) -> list[dict]:
    """[{id, score, record}] sorted best first. exclude_ids prevents eval leakage (always pass the query card's own id).
    model: "best" | "clip" | "dinov2" | "megaloc" | "fused" (rank fusion; score is then an RRF score, max about 0.05,
    not a cosine). verify=True checks the top hits with LightGlue (about 1 s per hit on CPU) and adds
    {inliers, verified}; verified hits come first. A verified hit has the right municipality about 96% of the time."""
def archive_lookup(place: str | None = None, municipality: str | None = None,
                   year_from: int | None = None, year_to: int | None = None, limit: int = 20) -> list[dict]:
    """Dated, labelled Staatsarchiv records matching the filter. Excludes eval split ids."""
def split_composite(image_path: str) -> list[dict]:
    """[{bbox:[x,y,w,h], path}] ; one item (full image) when not composite."""
def timeline(lat: float, lon: float, radius_m: int = 1000) -> list[dict]:
    """[{id, year_from, year_to, distance_m, image_path}] sorted by year."""
def gazetteer() -> list[dict]: ...                                         # gemeinden.json
def address_lookup(lat: float, lon: float, radius_m: int = 100, limit: int = 10) -> dict:
    """v3. What is at a point (swisstopo, official names): {lat, lon, ortschaft, plz, municipality, bfs_nr, canton,
    in_canton, addresses: [{street, number, address, zip, ortschaft, municipality, distance_m, lat, lon, egid,
    category}], source}. addresses nearest first, within radius_m (max 500). Disk-cached; needs network once."""
def named_buildings(lat: float | None = None, lon: float | None = None, radius_m: int = 500,
                    name: str | None = None, kinds: list[str] | None = None, limit: int = 20) -> list[dict]:
    """v3. Named places in Kanton Schwyz from OpenStreetMap (offline): [{name, kind, lat, lon, address,
    municipality, osm, wikidata, alt_names, tags, distance_m?}]. Near a point (nearest first) and/or by name
    (accent-insensitive substring, e.g. name="Acherhof"). kind is a German label: Kirche/Kapelle, Kloster,
    Rathaus, Schule, Alters-/Pflegeheim, Spital, Bahnhof, Bergbahnstation, Schiffstation, Hotel, Berghütte,
    Museum, Historisch, Restaurant, Hafen, Berg, See/Gewässer, Fluss, Bach, Ort, Brücke, Gebäude, ..."""
def eval_ids() -> set[str]: ...                                            # ids in splits/eval.jsonl (eval runner + leakage tests share this)
```

Dating (`from data_pipeline.dating import ...`):

```python
def date_hints(photo_id: str | None = None, image_path: str | None = None, exclude_ids=()) -> list[dict]:
    """[{kind, year, year_low, year_high, weight, evidence, source?}] sorted by weight. evidence is German.
    kind: near_duplicate | card_number | nb_negative | publisher_rule | year_probe. year/low/high may be null
    (e.g. a posted near-duplicate only gives an upper bound). Eval cards are never used as a hint source."""
def rule_checklist() -> list[dict]:
    """Visual dating rules for the prompt: [{id, category, feature, year_min, year_max, confidence, source}]
    (postal rates, print techniques, Schwyz landmarks; every rule has a source URL)."""
def eval_exclusions(photo_id: str) -> list[str]:
    """Extra ids to exclude when scoring an eval item (LUBIS / NB survey series). Pass them to date_hints and
    similar_images in eval runs only."""
```

Scoring (`from data_pipeline.metrics import score`): `score(predictions) -> dict` with predictions
`[{id, municipality, municipality_confidence, year, year_low, year_high, place_name_printed?}]`.

Stub mode: with env `DATA_PIPELINE_STUB=1` the section 4 functions return fixture data from `contracts/fixtures/`, so Agent can build before the real index exists.

> Eval leakage rule: when the agent analyses an eval card, `similar_images` and `archive_lookup` must never return that card or its crops. `archive_lookup` and `date_hints` never use any eval card. Eval runs also pass `eval_exclusions(photo_id)`.

## 5. HTTP API (Agent serves on :8000, Frontend calls)

Base URL from env `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). JSON unless noted. CORS open for localhost.

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/health` | | `{ok: true, model, offline: bool, tiles_url}` (tiles_url = `/tiles` when offline, else the swisstopo WMTS base) |
| GET | `/photos` | `?split=&priority=&municipality=&q=&limit=50&offset=0` | `{items: PhotoRecord[], total}` (v3: `split=challenge&priority=1` = the 50) |
| GET | `/photos/{id}` | | `PhotoRecord` |
| GET | `/images/{id}` | `?w=` optional width | `image/jpeg` |
| POST | `/analyze` | JSON `{photo_id}` or multipart `file`; `?fresh=1` bypasses the cache | `{job_id, photo_id}` (cache hit returns a job that is already `done`) |
| GET | `/analyze/{job_id}` | | `AnalysisResult` (status may be `running`) |
| GET | `/analyze/{job_id}/events` | Server-Sent Events | one `trace` item per event, final event `result` with the full AnalysisResult |
| GET | `/results/{photo_id}` | | latest cached `AnalysisResult` or 404 |
| GET | `/timeline` | `?lat&lon&radius_m=1000` | `{photos: [{id, year_from, year_to, distance_m, image_url}], map_years: [18641231, ...]}` |
| GET | `/export.csv` | `?ids=a,b,c` (default: all with results) | CSV, see 6 |
| GET | `/export.xlsx` | `?ids=` or `?split=challenge&priority=1` | v3: the Excel deliverable, same columns as 6, one sheet `Metadaten` + one sheet `Methode` (how confidence is computed) |
| POST | `/review/{photo_id}` | `{status: "bestaetigt"\|"korrigiert", fields: {locality: "...", ...}, note}` | v3: stores `review` in the cached result; export uses reviewed values |
| GET | `/export.json` | same | `[ExportRow]` |
| GET | `/eval/summary` | | EvalSummary, see 7 |
| GET | `/demo` | | `[{id, why, record: PhotoRecord}]` in pitch order (from `splits/demo.json`) |
| GET | `/tiles/{layer}/{time}/{z}/{x}/{y}` | | cached swisstopo tile from `data/tiles/`, falls back to proxying wmts.geo.admin.ch when online |

Composite cards: `/results/{photo_id}` returns the parent result; its `composite.parts` ids are themselves valid for `/photos/{id}`, `/images/{id}` and `/results/{id}`.

Frontend modes: `NEXT_PUBLIC_MODE=mock|live|demo` (see SCOPE_3). Offline/demo: frontend uses `/tiles/...` (from `/health` `tiles_url`) instead of wmts.geo.admin.ch. With `AGENT_FAKE=1` the backend replays `contracts/fixtures/analysis_result.json` over SSE (no Claude calls).

`map_years` = the valid `ch.swisstopo.zeitreihen` TIME values (from WMTS GetCapabilities, cached).

## 6. Export row (Excel deliverable, v3)

`.xlsx` (sheet `Metadaten`, plus sheet `Methode` explaining the confidence scale), and the same columns as CSV (UTF-8 with BOM, `;`). One row per photo. No import format is fixed by the archive yet, so names are German and the order follows Ralph's priority. A field that could not be determined stays empty and is listed in `Nicht_bestimmbar`.

| Column | From |
|---|---|
| `Dateiname` | record.raw.file_name (unique key, e.g. `SG.CIV.17.3.jpg`) |
| `Signatur` | record.signature |
| `Prioritaet` | record.raw.priority (1 or 2) |
| `Ortschaft` | fields.locality (review value wins) |
| `Gemeinde` | fields.municipality |
| `Gebaeude` | fields.buildings joined `"; "` |
| `See_Fluss_Berg` | fields.landscape_features joined `"; "` |
| `Strasse` | fields.street |
| `Aufnahmedatum` | record.date.raw (EXIF) |
| `Breite_WGS84`, `Laenge_WGS84`, `E_LV95`, `N_LV95` | fields.coordinates |
| `Konfidenz_Ortschaft`, `Konfidenz_Gemeinde`, `Konfidenz_Gebaeude`, `Konfidenz_See_Fluss_Berg`, `Konfidenz_Strasse`, `Konfidenz_Gesamt` | confidences, 0 to 1 |
| `Konfidenz_Begruendung` | confidence_explanation |
| `Nicht_bestimmbar` | names of the fields left open, joined `", "` |
| `Pruefung_noetig` | `ja` / `nein` (needs_review) |
| `Review_Status` | review.status or `offen` |
| `Quellen` | top 3 evidence summaries with url / ref_id, joined `" \| "` |
| `KI_Modell`, `Analysedatum` | model, created_at |

## 7. EvalSummary (Agent's eval runner writes `data/results/eval_summary.json`)

```jsonc
{
  "n": 350, "model": "claude-opus-5-5", "created_at": "...",
  "municipality_accuracy": 0.0,     // exact Gemeinde match
  "decade_accuracy": 0.0,           // predicted decade == true decade (true decade from year_from..year_to)
  "decade_within_one": 0.0,         // off by at most one decade
  "median_coord_error_km": null,    // only where ground truth has coordinates
  "calibration": [{ "bin": "0.8-1.0", "n": 0, "accuracy": 0.0 }],
  "by_municipality": [{ "municipality": "Schwyz", "n": 0, "accuracy": 0.0 }],
  "baseline": { "similarity_only_municipality_accuracy": 0.0 },
  "failures": [{ "photo_id": "...", "expected": "...", "got": "...", "why": "..." }],
  "cost_usd": 0.0,
  "metrics": { }                     // data_pipeline.metrics.score(predictions): per subset, printed vs not printed, confidence levels, year ranges
}
```

## 8. Fixtures

`contracts/fixtures/` holds one valid example of each object (`photo_record.json`, `analysis_result.json`, `timeline.json`, `eval_summary.json`, `export.csv`, `date_hints.json`) using a public-domain reference image, so Agent and Frontend can build before real data or a real agent exists. Frontend mock mode (`NEXT_PUBLIC_MODE=mock`) reads them through a copy step (`npm run fixtures` copies `contracts/fixtures/` to `frontend/public/fixtures/`); never edit the copies.
