# CHALLENGE BRIEF (v3, Fri 23 Oct): what the jury actually wants

Read this before anything else. It replaces the "date old postcards" framing of the earlier docs. The detailed brief and the photo set arrived at the event (SharePoint zip, unpacked in `data/challenge/` on Dijar's machine and served by the data server).

> [!IMPORTANT]
> The test photos are **603 uncatalogued 21st-century photos** (`SG.CIV.17.*`, taken 2003 to 2013), not historical postcards. **50 are "Prio 1"** and must be done first. **Dating is not asked**: every photo has its EXIF capture date. The job is **where**, down to building and street.

## 1. The requirements, mapped to what we have

### MUST

| Requirement (brief) | Status | Owner |
|---|---|---|
| Working prototype (tool, app, macro) | agent + backend + frontend exist | all |
| Read and process the 50 Prio-1 photos, one result per photo | records ready: `split=challenge`, `raw.priority=1` | Data done; Agent runs them |
| Fields in priority **Ortschaft, politische Gemeinde, Gebaeude, See/Fluss/Berg, Strasse** | v3 fields `locality`, `municipality`, `buildings`, `landscape_features`, `street` | Agent (prompt + submit_result), Frontend (order) |
| Concrete names, not object types ("Alterszentrum Acherhof", not "Gebaeude") | `named_buildings`, `address_lookup`, reference titles | Agent uses the tools |
| Use reference sources (Staatsarchiv catalogue, E-Pics, geodata, web) | 20k reference photos + swisstopo + OSM | Data done |
| **One Excel row per photo**, unique link to the file, with the metadata | `/export.xlsx`, key `Dateiname` (CONTRACTS 6) | Agent |
| **Confidence value per row, and the method explained** | `confidence_explanation` + sheet `Methode` + one pitch slide | Agent, pitch |
| Unknowns marked as unknown, never invented | null + confidence 0 + `Nicht_bestimmbar` column | Agent (prompt rule), Frontend shows "nicht bestimmbar" |
| Quality control, and a live demo of how a result, its uncertainty and the Excel come about | hand-checked sample (section 4), live trace + export in the demo | all |

### SHOULD (nice to have, in value order)

1. Semi-automatic **review**: archivists confirm or correct a suggestion (`POST /review`, buttons in the UI). Timo + Said.
2. UI with image preview, metadata, source links, **map**. Mostly exists; add the review buttons and the source links.
3. Several sources compared automatically, main sources listed per result (`Quellen` column). Agent.
4. Separate confidence per field, plus a review flag. Already in the AnalysisResult; now also in the Excel.
5. Process beyond the 50 (the other 553). Agent batch run, about $0.05 per photo with Opus, so about $30 for all 603.

Out of scope (brief): perfect results on all 600, a measured >90% hit rate, live archive integration, training our own model, B/W-only focus.

## 2. Facts measured on the photos (Data, 23 Oct evening)

- **File names are the signature**: `SG.CIV.17.3.jpg`. None of these signatures is in the online catalogue, so nothing to look up and no leakage.
- **EXIF date on 601 of 603** (2003 to 2013). Camera make and model too.
- **GPS is useless**: 1 of 603 has real coordinates (`SG.CIV.17.291`, Morschach). The 15 Prio-1 GPS blocks are empty.
- **Sessions**: 267 photos were shot with the same camera within 30 minutes of another (`raw.session`), 22 of them in Prio 1. One located photo is strong evidence for its session siblings (evidence kind `session_photo`).
- **Reference retrieval still works for landmarks**: `similar_images(verify=True)` gives at least one LightGlue-verified match on **21 of 50** Prio-1 photos, with building names in the matched titles (Rathaus + Hotel Wysses Rössli Hauptplatz Schwyz, Café Haug Postplatz 4, Hotel Axenfels Morschach, Kapelle Maria Hilf Stoos, Insel Schwanau, Glattalp-Hütte). The other 29 (modern buildings such as the Acherhof) have no verified match: there the agent needs `named_buildings`, `address_lookup` and its own eyes.
- Precision of verified matches on these photos is not measured (the 96% figure is from postcards). Treat a verified match as strong, not certain.

## 3. The worked example from the brief

`SG.CIV.17.3` should give: Ortschaft **Schwyz**, Gemeinde **Schwyz**, Gebaeude **Alterszentrum Acherhof**, Berg **Mythen**, Strasse **Grundstrasse 32**.

How our tools get there: the model sees a modern care home with the Mythen behind it, guesses Schwyz, calls `named_buildings(name="Acherhof")` or `named_buildings(lat, lon, kinds=["Alters-/Pflegeheim"])` around Schwyz, takes the building's coordinates, then `address_lookup(lat, lon)` returns Ortschaft Schwyz, Gemeinde Schwyz and the official address `Grundstrasse 32.1`. Use this photo as the first agent test and as the first demo card.

## 4. Confidence method (proposal, Said decides, the pitch explains it)

Ralph's example: confirmed by 10 sources = 100%, 5 sources = 75%. Ralph accepts **above 90%**. A self-rated number is not a measured hit rate, so we show both.

Proposal, per field:
1. Count **independent** supporting evidence items (kinds differ or refs differ): a verified similar image, a named building within 150 m, the official address register, readable text in the photo, a session sibling, a terrain check.
2. Base score from the count: 1 source 0.5, 2 sources 0.7, 3 sources 0.85, 4 or more 0.95. Any contradicting evidence (`supports: false`) caps the field at 0.6.
3. Overall = the lowest of `locality` and `municipality`, raised by at most 0.05 when buildings and street agree with them.
4. `needs_review` = overall below 0.9, or locality or municipality unknown. That is the "accept or check" line in the Excel.
5. `confidence_explanation` states it in one German sentence, e.g. "Gemeinde durch 3 unabhängige Quellen bestätigt (verifiziertes Referenzfoto, Gebäudeadressverzeichnis, Session-Foto); Strasse nicht bestimmbar."

Quality control: on Saturday morning the team hand-checks about 20 Prio-1 results against Google Maps / Street View, writes them as ground truth to `data/splits/challenge_qc.jsonl` (`{id, locality, municipality, buildings, street}`), and the pitch shows the measured hit rate per confidence bin next to the self-rated scale. The 350-card postcard eval stays as the second proof (municipality accuracy on catalogued archive cards).

## 5. Per-scope to-do (v3)

### Data (Dijar), done 23 Oct
1. `scrapers/challenge.py`: 603 records with EXIF date, sessions, 1024 px images. Done.
2. `address_lookup(lat, lon)`: Ortschaft, Gemeinde, nearest official addresses. Done.
3. `named_buildings(...)`: named OSM places in the canton, offline. Done.
4. Contracts v3: schemas, fixtures (`address_lookup.json`, `named_buildings.json`), this brief. Done.
5. Saturday: `challenge_qc.jsonl` from the team's hand check, and data fixes for failures.

### Agent + backend (Said)
1. Tools `address_lookup` and `named_buildings` (CONTRACTS 4). Give the model the session siblings' results when they exist.
2. Prompt + `submit_result`: v3 fields in priority order, null + confidence 0 when unknown, no dating work for challenge photos (date comes from the record).
3. Confidence method from section 4, `confidence_explanation`, `needs_review` at 0.9.
4. `/photos?split=challenge&priority=1`, `/export.xlsx` (openpyxl) with the CONTRACTS 6 columns and a `Methode` sheet, `POST /review/{photo_id}`.
5. Run the 50 (cache in `data/results/`), then the 553 if budget allows. First test: `challenge:SG.CIV.17.3`.

### Frontend (Timo)
1. Home lists `split=challenge`, Prio 1 first (not `showcase`).
2. Result panel in the brief's order: Ortschaft, Gemeinde, Gebaeude, See/Fluss/Berg, Strasse. Show "nicht bestimmbar" for null fields, not an empty row.
3. Review: "Bestätigen" and "Korrigieren" (edit the value inline) per photo, calls `POST /review`. Shows `Review_Status`.
4. Sources with links per field; the `confidence_explanation` sentence under the overall score.
5. "Excel herunterladen" button: `/export.xlsx?split=challenge&priority=1`.
Time slider and then-vs-now are optional now (the photos are 2003 to 2013).

## 6. Pitch line

"The archive gets an Excel row per photo with Ortschaft, Gemeinde, Gebäude, Berg/See and Strasse, every value backed by named sources, every number explained, and nothing invented: what we cannot prove stays empty and is flagged for review."
