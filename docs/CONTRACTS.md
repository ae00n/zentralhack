# CONTRACTS: single source of truth

Every scope builds against this file. Change it only when all three agree (say it in the team chat first), then update the JSON Schemas in `contracts/schemas/` and the fixtures in `contracts/fixtures/` in the same commit.

Owners: Data = Dijar (`data_pipeline/`), Agent = Said (`agent/`), Frontend = Timo (`frontend/`).

Conventions:
- IDs are strings `"<source>:<source_id>"`, e.g. `stasz:514200`, `smapshot:2772`, `epics:LBS_MH01-001467`, `upload:7f3c...`. Crops of a composite card get `stasz:514200#1`, `#2`.
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
  records/all.jsonl            merged, deduplicated (Smapshot + E-Pics joined on E-Pics file name)
  images/<source>/<source_id>.jpg   max 1024 px long edge, watermark strip cropped (stasz)
  index/<model>.faiss          FAISS IndexFlatIP over L2-normalised embeddings
  index/<model>.ids.json       row -> PhotoRecord id
  index/<model>.meta.json      {model, dim, n, created_at}
  splits/eval.jsonl            {id, municipality, year_from, year_to}  (labelled ground truth)
  splits/showcase.jsonl        {id}  undated / unlocated cards for the demo
  splits/timeline_sets.json    [{place, lat, lon, ids:[...sorted by year]}]
  splits/demo.json             [{id, why}]  pre-picked, pre-tested demo cards
  splits/stats.json            counts per municipality / decade / source
  gazetteer/gemeinden.json     [{name, bfs_nr, lat, lon, aliases:[...]}]  Kanton Schwyz municipalities
  results/<photo_id>.json      cached AnalysisResult (written by Agent; frontend demo mode reads these)
  tiles/                       offline swisstopo tile cache for the demo area (Friday)
```

## 2. PhotoRecord

```jsonc
{
  "id": "stasz:514200",
  "source": "staatsarchiv",            // staatsarchiv | smapshot | epics | upload
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
    "method": "thema_gazetteer",       // smapshot_pose | epics_geo | thema_gazetteer
    "precision_m": 2000
  },
  "camera": null,                      // Smapshot only: {lat, lon, altitude_m, azimuth, tilt, roll, focal}
  "photographer": null,
  "license": {
    "code": "stasz-private",           // stasz-private | CC-BY-SA-4.0 | PDM | ...
    "credit": "Staatsarchiv Schwyz, SG.CIV.12.4743",
    "url": null
  },
  "image": { "path": "images/staatsarchiv/514200.jpg", "width": 767, "height": 476, "sha1": "..." },
  "parent_id": null,                   // set on crops of a composite card
  "crop_bbox": null,                   // [x, y, w, h] in parent pixels
  "split": "eval",                     // eval | showcase | reference | none
  "raw": { }                           // all source fields verbatim (e.g. Staatsarchiv labels)
}
```

Ground truth for evaluation = `municipality` (from Thema) and `date.year_from/year_to`.

## 3. AnalysisResult (produced by Agent)

```jsonc
{
  "photo_id": "stasz:514189",
  "run_id": "2026-10-23T21:14:02Z-ab12",
  "status": "done",                    // queued | running | done | needs_review | error
  "model": "claude-sonnet-5-5",
  "composite": {                       // null if single photo
    "is_composite": true,
    "parts": ["stasz:514189#1", "stasz:514189#2"]   // each part has its own AnalysisResult
  },
  "fields": {
    "municipality":       { "value": "Schwyz",               "confidence": 0.86, "evidence": [ /* Evidence */ ] },
    "place":              { "value": "Hauptplatz",            "confidence": 0.71, "evidence": [] },
    "buildings":          { "value": ["Pfarrkirche St. Martin", "Rathaus"], "confidence": 0.80, "evidence": [] },
    "landscape_features": { "value": ["Grosser Mythen", "Kleiner Mythen"],  "confidence": 0.90, "evidence": [] },
    "decade":             { "value": 1900,                    "confidence": 0.55, "evidence": [] },
    "year_range":         { "value": { "from": 1898, "to": 1912 }, "confidence": 0.55, "evidence": [] },
    "coordinates":        { "value": { "lat": 47.0207, "lon": 8.6541, "radius_m": 300 }, "confidence": 0.70, "evidence": [] }
  },
  "overall_confidence": 0.74,
  "needs_review": false,               // true when any core field (municipality, decade) < 0.5
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
                   exclude_ids: list[str] = (), sources: list[str] | None = None) -> list[dict]:
    """[{id, score, record}] sorted by score desc. exclude_ids prevents eval leakage (always pass the query card's own id)."""
def archive_lookup(place: str | None = None, municipality: str | None = None,
                   year_from: int | None = None, year_to: int | None = None, limit: int = 20) -> list[dict]:
    """Dated, labelled Staatsarchiv records matching the filter. Excludes eval split ids."""
def split_composite(image_path: str) -> list[dict]:
    """[{bbox:[x,y,w,h], path}] ; one item (full image) when not composite."""
def timeline(lat: float, lon: float, radius_m: int = 1000) -> list[dict]:
    """[{id, year_from, year_to, distance_m, image_path}] sorted by year."""
def gazetteer() -> list[dict]: ...                                         # gemeinden.json
def eval_ids() -> set[str]: ...                                            # ids in splits/eval.jsonl (eval runner + leakage tests share this)
```

Stub mode: with env `DATA_PIPELINE_STUB=1` every function returns fixture data from `contracts/fixtures/`, so Agent can build before the real index exists.

> Eval leakage rule: when the agent analyses an eval card, `similar_images` and `archive_lookup` must never return that card or its crops. `archive_lookup` never returns any eval card.

## 5. HTTP API (Agent serves on :8000, Frontend calls)

Base URL from env `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). JSON unless noted. CORS open for localhost.

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/health` | | `{ok: true, model, offline: bool, tiles_url}` (tiles_url = `/tiles` when offline, else the swisstopo WMTS base) |
| GET | `/photos` | `?split=&municipality=&q=&limit=50&offset=0` | `{items: PhotoRecord[], total}` |
| GET | `/photos/{id}` | | `PhotoRecord` |
| GET | `/images/{id}` | `?w=` optional width | `image/jpeg` |
| POST | `/analyze` | JSON `{photo_id}` or multipart `file`; `?fresh=1` bypasses the cache | `{job_id, photo_id}` (cache hit returns a job that is already `done`) |
| GET | `/analyze/{job_id}` | | `AnalysisResult` (status may be `running`) |
| GET | `/analyze/{job_id}/events` | Server-Sent Events | one `trace` item per event, final event `result` with the full AnalysisResult |
| GET | `/results/{photo_id}` | | latest cached `AnalysisResult` or 404 |
| GET | `/timeline` | `?lat&lon&radius_m=1000` | `{photos: [{id, year_from, year_to, distance_m, image_url}], map_years: [18641231, ...]}` |
| GET | `/export.csv` | `?ids=a,b,c` (default: all with results) | CSV, see 6 |
| GET | `/export.json` | same | `[ExportRow]` |
| GET | `/eval/summary` | | EvalSummary, see 7 |
| GET | `/demo` | | `[{id, why, record: PhotoRecord}]` in pitch order (from `splits/demo.json`) |
| GET | `/tiles/{layer}/{time}/{z}/{x}/{y}` | | cached swisstopo tile from `data/tiles/`, falls back to proxying wmts.geo.admin.ch when online |

Composite cards: `/results/{photo_id}` returns the parent result; its `composite.parts` ids are themselves valid for `/photos/{id}`, `/images/{id}` and `/results/{id}`.

Frontend modes: `NEXT_PUBLIC_MODE=mock|live|demo` (see SCOPE_3). Offline/demo: frontend uses `/tiles/...` (from `/health` `tiles_url`) instead of wmts.geo.admin.ch. With `AGENT_FAKE=1` the backend replays `contracts/fixtures/analysis_result.json` over SSE (no Claude calls).

`map_years` = the valid `ch.swisstopo.zeitreihen` TIME values (from WMTS GetCapabilities, cached).

## 6. Export row (archive field structure)

CSV, UTF-8 with BOM, `;` separator (Swiss Excel default). Column names follow the Staatsarchiv detail page labels where one exists.

| Column | From |
|---|---|
| `Signatur` | record.signature |
| `Titel` | record.title |
| `Entstehungszeitraum` | record.date.raw (original, unchanged) |
| `Entstehungszeitraum_KI` | `"1898-1912"` from fields.year_range |
| `Jahrzehnt_KI` | fields.decade |
| `Thema` | record.places joined `"; "` |
| `Gemeinde_KI` | fields.municipality |
| `Ort_KI` | fields.place |
| `Gebaeude_KI` | fields.buildings joined `"; "` |
| `Landschaft_KI` | fields.landscape_features joined `"; "` |
| `Breite_WGS84`, `Laenge_WGS84` | fields.coordinates |
| `E_LV95`, `N_LV95` | converted from WGS84 |
| `Konfidenz_Gemeinde`, `Konfidenz_Jahrzehnt`, `Konfidenz_Koordinaten`, `Konfidenz_Gesamt` | confidences |
| `Pruefung_noetig` | `ja` / `nein` |
| `Evidenz` | top 3 evidence summaries joined `" | "` |
| `KI_Modell`, `Analysedatum` | model, created_at |
| `URL` | record.source_url |

## 7. EvalSummary (Agent's eval runner writes `data/results/eval_summary.json`)

```jsonc
{
  "n": 300, "model": "claude-sonnet-5-5", "created_at": "...",
  "municipality_accuracy": 0.0,     // exact Gemeinde match
  "decade_accuracy": 0.0,           // predicted decade == true decade (true decade from year_from..year_to)
  "decade_within_one": 0.0,         // off by at most one decade
  "median_coord_error_km": null,    // only where ground truth has coordinates
  "calibration": [{ "bin": "0.8-1.0", "n": 0, "accuracy": 0.0 }],
  "by_municipality": [{ "municipality": "Schwyz", "n": 0, "accuracy": 0.0 }],
  "baseline": { "similarity_only_municipality_accuracy": 0.0 },
  "failures": [{ "photo_id": "...", "expected": "...", "got": "...", "why": "..." }],
  "cost_usd": 0.0
}
```

## 8. Fixtures

`contracts/fixtures/` holds one valid example of each object (`photo_record.json`, `analysis_result.json`, `timeline.json`, `eval_summary.json`, `export.csv`) using a public-domain reference image, so Agent and Frontend can build before real data or a real agent exists. Frontend mock mode (`NEXT_PUBLIC_MODE=mock`) reads them through a copy step (`npm run fixtures` copies `contracts/fixtures/` to `frontend/public/fixtures/`); never edit the copies.
