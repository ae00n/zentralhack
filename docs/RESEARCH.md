# RESEARCH: verified findings (2026-10-20)

Everything here was fetched live on 2026-10-20. Items marked **UNVERIFIED** were not confirmed from a primary source.

## 0. Corrections to the original brief

| Brief said | Verified | Source |
|---|---|---|
| Hack starts 19:30, presentations 19:00 Sat | Hack starts **Fri 19:00**; **submission and final presentations Sat 17:00**; awards 18:00 | https://www.zentralhack.ch/api/schedule |
| SG.CIV.12 has ~4,800 entries | **~6,417 entries** (tree paging: "noch 4700" + "noch 1617" + current 100) | archivplansuche.aspx |
| IDs usable as ranges | IDs are **not contiguous** (e.g. 514206 to 514218, 514242 to 514694; 514300 is an unrelated dossier) | detail.aspx samples |
| Team of 3 | FAQ: teams of 3 to 5; this challenge lists `"team_size": "3-4"` | /api/faqs, /api/categories |

## 1. Hackathon (Zentral Hack 2026)

Sources: https://www.zentralhack.ch (JS app), `/api/categories`, `/api/faqs`, `/api/schedule`, terms: https://raw.githubusercontent.com/stairch/zentral-hack/HEAD/app/agb/terms_en.md ("As of: May 2026", German prevails).

### Official schedule
| Day | Time | Item |
|---|---|---|
| Fri 23 Oct | from 17:00 | Check-in |
| | 18:00 | Begrüssung |
| | 18:30 | Challenge Pitches und Teamfindung |
| | 19:00 | Start des Hacks |
| | 20:00 | Dinner |
| | 23:00 | Prompt Battle |
| Sat 24 Oct | 08:00 / 12:00 | Brunch / Lunch |
| | 17:00 | Projekt-Abgabe und Abschlusspräsentationen |
| | 18:00 | Ende und Preisverleihung |

A lucerne-business.com summary gave later times (UNVERIFIED, not opened). Go by the official site.

### Challenge text (verbatim)
- EN: "Develop an AI-powered solution that analyzes historical photographs and identifies locations, municipalities, buildings, or landscape features. The goal is to automatically extract relevant metadata and structure it for further use in the archive system."
- DE: "Entwickelt eine KI-gestützte Lösung, die historische Fotos analysiert und darauf Orte, Gemeinden, Gebäude oder Landschaftsmerkmale erkennt. Ziel ist es, relevante Metadaten automatisch zu identifizieren und strukturiert für die weitere Nutzung im Archivsystem aufzubereiten."
- Sponsor Kanton Schwyz, category "AI Agentic", prize CHF 1'000 (first place).
- `datasets:false`, `apis:false`, contact fields empty. **Unknown whether the canton brings its own photos.**

### Judging weights (challenge `evaluation.criteria`)
| Criterion | Weight | Description |
|---|---|---|
| Innovation & Kreativität | 25 | Neuartigkeit, Originalität |
| Technische Umsetzung | 25 | Code-Qualität, Architektur |
| Problemlösung & Relevanz | 20 | Löst die Challenge das definierte Problem? |
| Präsentation & Pitch | 15 | Klarheit, Demo, Überzeugungskraft |
| Business-Potenzial | 15 | Umsetzbarkeit, Skalierbarkeit |

### Rules (verbatim excerpts)
- IP: "All intellectual property rights ... remain fully with the respective developers."
- License to sponsor/HSLU: "an irrevocable, non-exclusive, worldwide, royalty-free license to: Review and evaluate ... Present and communicate ... Further develop and use internally ... Use commercially the results".
- Third party: "Teams are responsible for ensuring that any third-party libraries, frameworks, datasets, or other materials used are licensed under compatible terms and properly attributed."
- **Not stated anywhere:** pre-event coding, pre-existing code, AI tool policy. Team decision: before Fri 19:00 only data, embeddings, eval split, docs, empty scaffold.
- Submission: team dashboard takes a GitHub URL (`regex(/github\.com/)`) plus file uploads (from site source code).
- Logistics: free, bring own laptop, HSLU public Wi-Fi, sleeping areas.

## 2. Staatsarchiv Schwyz (query.staatsarchiv.sz.ch, scopeArchiv)

### Access
| Item | Finding |
|---|---|
| robots.txt | none (404). www.sz.ch/robots.txt only disallows `/route/`, `/xml_1/` |
| OAI-PMH | none (`/oai`, `/oai2` 404; `/OAI/oai.aspx` redirects to error) |
| Export | only per-record PDF (`report.aspx?rpt=1&ID=`); no CSV/XML/EAD |
| OpenSearch | `https://query.staatsarchiv.sz.ch/OpenSearch/?q={term}&si={start}&format=rss`, `si` starts at 1, 25/page, **capped at 1,500 hits**, cannot search by signature |
| Tree | `archivplansuche.aspx?ID=X`, Telerik RadTreeView, IDs in `nodeData` JSON, **100 per page via postback** (needs Playwright) |
| Permalink | `https://query.staatsarchiv.sz.ch/detail.aspx?ID=<id>` |
| WAF | cookie `TS01e8e57d`; throttle |

### Subcollection node IDs
.01=267217, .02=267218 (no children), .03=267219, **.04=267220 (Flugaufnahmen)**, .05=267221, .06=267222, .07=436256, .08=267223, .09=369247, .10=267224, **.12=267225 (Ansichtskarten)**, .23=724682. Counts for .01 to .10 and .23: UNVERIFIED (need postbacks).

### Detail page fields (labels verbatim)
`Signatur`, `Signatur Archivplan`, `Titel`, `Darin`, `Entstehungszeitraum`, `Stufe`, `Archivalienart`, `Bisherige Zitierweise`, `Karten Nr.`, `Ansichtsbild`, `Autor/Fotograf/Künstler`, `Thema`, `Format I L x B (cm)`, `Dublette`, `Microfiche vorhanden`, `Digitalisat vorhanden`, `Digitalisiert ab`, `Zusatzinfos`, `Personendaten`, `Erforderliche Bewilligung`, `Physische Benützbarkeit`, `Zugänglichkeit`, `URL`.

- Date formats: `1914`, `keine Angabe`, `ca. 1915`, `05.07.1947 - 05.07.1947`.
- Thema: `;`-separated places, e.g. `Oberarth; Arth`.
- Example: ID 514200 = SG.CIV.12.4743 "Oberarth mit Gasthaus Engel", 1914 (confirmed).

### Preview images
- `getimage.aspx?veid={ID}&deid=10&sqnznr=1&width=520&klid=9`: 520x336 JPEG, ~26 KB.
- `width=3000` returns max **767x496** (~58 KB). No higher-res public viewer; full scans are paid.
- **Watermarked:** "Staatsarchiv Schwyz" bottom left, signature bottom right on a white strip. Crop the bottom ~20 px.

### Coverage (sampled)
- Dates: two 100-entry windows: 40 and 47 "Keine Angabe" so **~55% dated, ~45% undated**.
- Thema place tags: all 5 detail pages sampled had them (small sample).
- archives-quickaccess.ch/stasz groups SG.CIV.12 by municipality: page 1 lists 50 municipalities, 5,046 documents (Schwyz 1,042, Einsiedeln 556).

### Terms
- Benutzungsordnung (https://www.sz.ch/public/upload/assets/27871/Benutzungsordnung.pdf?fp=8): "Kopien, Fotografien, Abschriften usw. von Archivalien für den privaten Gebrauch sind gestattet. Bei Publikationen (Druck oder online) muss das Copyright des Staatsarchiv Schwyz beachtet werden."
- SG.CIV.04 (ID 267220): "Die Reproduktionsrechte dieser Aufnahmen liegen bei der ETH-Bibliothek ... Ein Teil des Bestandes war eine Schenkung. Von diesen Bildern liegen die Reproduktionsrechte beim STASZ."
- **No open license.** sz.ch Nutzungshinweise page returned 403 (UNVERIFIED).

### Recommendation
- Enumerate IDs via Playwright tree paging (~64 pages for SG.CIV.12), then `detail.aspx` + `getimage.aspx?width=767` at 1 request / 2 s (~7 h). Resumable, dedupe by ID.
- Keep images private: never in git, never public. Credit "Staatsarchiv Schwyz" in the demo.

## 3. Reference images

### Smapshot (HEIG-VD), primary
- Open API with OpenAPI docs: https://smapshot.heig-vd.ch/api/v1/docs/ . Arrays need `[]`, e.g. `bbox[]=8.38&bbox[]=46.88&bbox[]=9.03&bbox[]=47.22`; polygon via `wkt_roi`.
- Counts, Schwyz bbox, validated: **17,969 total, 6,356 pre-1970**; ETH (`owner_id[]=4`): 15,900 / 4,486 pre-1970.
- `/images/{id}/attributes`: full camera pose (lat, lon, altitude, azimuth, tilt, roll, focal), license, DOI.
- `original_id` = E-Pics file name (e.g. `LBS_MH01-001467`), so the two sources join.

### E-Pics (ETH-Bibliothek), secondary
- Frontend runs on Sharedien DAM. API `https://api.ethz.sharedien.com/api/v10`, Bearer token embedded in https://ba.e-pics.ethz.ch/ HTML. **Undocumented**: use politely (1 req/s).
- `POST /assets/search?limit=N&cursor=` with `advancedSearchFilters`: `InBoundingBox` on `eth_geo_location`, `LessThanOrEquals` on `eth_date_range`, `IdentifierEquals` on `eth_license`. Total in `x-total-count`.
- Schwyz bbox geocoded: 14,411 total, **4,463 pre-1970** (CC BY-SA 2,942, PDM 1,520). Postcards `PK_`: 383 (381 pre-1970).
- Derivations: Thumbnail 161x240, **Screen 805x1200**, Print, Original TIFF 64 MB (never download).
- Fields include `eth_geo_location`, `eth_geo_azimuth`, `eth_geo_altitude`, `eth_license`, `eth_dating`, `eth_download_forbidden`.
- Terms (https://www.e-pics.ethz.ch/en/ba_use/): "The images are licensed under Creative Commons BY-SA 4.0." Credit: "ETH-Bibliothek Zurich, Image Archive." Nothing about APIs or rate limits.
- Keep: CC BY-SA 4.0 and Public Domain Mark, `eth_download_forbidden=False`. Skip NC, unknown, restricted.
- Full-text place counts are inflated by fuzzy matching (Brunnen, Steinen, Sattel).

### Wikimedia Commons: not useful
- "Media contributed by the ETH-Bibliothek": 60,449 files, but geosearch around Schwyz returned **0** ETH-BIB files. Rate-limited after ~10 calls.

### Not checked (UNVERIFIED)
opendata.swiss (403), Europeana, Memobase, Notrepatrimoine, IIIF/OAI for E-Pics, E-Pics export row limit.

## 4. swisstopo / geo.admin.ch

### Layers (from https://wmts.geo.admin.ch/EPSG/3857/1.0.0/WMTSCapabilities.xml)
| Use | Layer ID | Time values |
|---|---|---|
| Journey Through Time | `ch.swisstopo.zeitreihen` | 178 values, `18441231` to `20211231` |
| Siegfried | `ch.swisstopo.hiks-siegfried` | 80 years from 1870 |
| Dufour | `ch.swisstopo.hiks-dufour` | `current` |
| SWISSIMAGE today | `ch.swisstopo.swissimage` | `current` (jpeg) |
| Historical orthophotos | `ch.swisstopo.swissimage-product` | 2025 back to 1926 |
| LUBIS aerial | `ch.swisstopo.lubis-luftbilder_schwarzweiss` etc. | 1921 onward |
| LUBIS ground photos | `ch.swisstopo.lubis-terrestrische_aufnahmen` | dated, with camera station |

### Tile URL (tested HTTP 200, `access-control-allow-origin: *`)
```
https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.zeitreihen/default/{YYYYMMDD}/3857/{z}/{x}/{y}.png
```
TIME must be an exact listed value (`18650615` returned 400). Snap to nearest listed value.

### REST (tested)
- Height: `https://api3.geo.admin.ch/rest/services/height?easting=2693000&northing=1208000&sr=2056` gives `{"height":"539.9"}`.
- Profile: `.../rest/services/profile.json?geom=<LineString>&sr=2056&nb_points=N`.
- Search: `.../rest/services/api/SearchServer?searchText=...&type=locations&sr=2056` returns swissNAMES (peaks, passes, settlements) with coordinates.
- Identify needs `mapExtent` and `imageDisplay`.

### Terms (https://www.geo.admin.ch/en/general-terms-of-use-fsdi)
- "Use of the geoservices of the FSDI does not require registration and is free-of-charge."
- Limits: REST **40 req/min**, WMTS 1,200 req/min. "Automatic parsing of geoservices via bots with high query intensities is to be avoided."
- Attribution mandatory: "©swisstopo". Commercial use allowed.

### Bonus
LUBIS ground photos carry `smapshot_id` and dated camera stations: extra ground truth if time allows.

## 5. Model pricing (platform.claude.com, 2026-10-20)

| Model | Input / Output per MTok |
|---|---|
| Claude Opus 5.5 | $4 / $20 |
| Claude Sonnet 5.5 | $2 / $10 |
| Claude Haiku 5.5 (prompt up to 100k) | $0.10 / $0.50 |

Images: `ceil(w/28) x ceil(h/28)` tokens; 1000x1000 = 1,296 tokens. Gemini Flash has a free tier (ai.google.dev pricing), not used.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Rules silent on pre-event code | Only data, index, docs, empty scaffold before Fri 19:00 |
| Staatsarchiv images not openly licensed | Private storage only, credit in demo, no redistribution |
| E-Pics API undocumented | 1 req/s, Screen size only, store license per image |
| SG.CIV.04 rights at ETH | Treat like E-Pics licensing |
| swisstopo REST 40/min | Cache all agent tool calls |
| mainframe has no GPU, ~3 GB free RAM | Small CPU batches or M4 Air MPS |
| Canton may bring own photos | Pipeline accepts any image folder |

## 7. Open questions

1. Does the canton hand out photos at the 18:30 pitch? (ask on Friday)
2. Exact submission format (GitHub link and/or files).
3. Child counts for SG.CIV.01 to .10 and .23.
4. Whether OpenSearch syntax can bypass the 1,500 cap (not needed if tree paging works).
5. E-Pics export row limit, Swissair prefix.
