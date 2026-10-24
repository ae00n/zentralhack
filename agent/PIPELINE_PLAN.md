# Agent v4: a fixed pipeline instead of free tool use

State on Sat 24 Oct, early morning. Written for the pair-programming session on Dijar's machine.

## Why
The v3 agent lets Claude choose its own tools (up to 12 calls). Each run takes a different path, so:
- answers flip between runs (9 of 49 Prio 1 photos unstable with `--runs 2`);
- the right candidate is sometimes never checked (17.3: the Acherhof never went into the aerial view);
- cost and time vary a lot (0.20 to 0.95 USD per photo for 2 runs).

Last full Prio 1 run (all tools, 2 runs, high effort): 32 of 49 accepted, 17 review
(9 unstable, 3 without a Schwyz Gemeinde, 5 stable but at 0.85). Nobody knows yet whether the 32 are correct:
there is no ground truth until the hand check.

## The pipeline (same 5 stages for every photo)

| Stage | Who | What |
|---|---|---|
| 1. Read the clues | Claude, 1 call, structured output | Text read in the photo, building type, landmarks (peaks, lakes, towers) with their horizontal position x (0..1), sun or shadow side, view type (street, landscape, lake, from above). No place names yet. |
| 2. Candidates | our code | 3 to 5 candidate places from: verified `similar_images` hits (their positions), session siblings (results and positions), `named_buildings` of the building type near those places, `viewpoint_search` from the landmarks, EXIF GPS when present. Deduplicate by distance. |
| 3. Check every candidate | our code | For each candidate, the same pack: `photos_near` thumbnails, `aerial_view` as of the capture year, `skyline` + sun when the view has mountains, nearby `named_buildings` of the building type. |
| 4. Decide | Claude, 1 call, structured output | All candidates side by side with their packs. Picks one (and the building among the nearby ones) or "none fits", with the evidence per field. |
| 5. Names + score | our code | `address_lookup` at the chosen building, register check, `confidence.apply`, second run and `consistency.combine`. |

Expected: 2 to 3 Claude calls per run instead of up to 12, fewer flips, every candidate checked the same way.

## Rule fixes (free, recompute existing runs)
- A run that found nothing is an abstention, not a contradiction (`consistency.check`).
- Gemeinde stable across runs counts as stable even when the Ortschaft differs between neighbouring places;
  only the Ortschaft field is then marked uncertain.
- Photos outside the canton (17.390 Naefels GL, 17.583 Wasserauen AI): recognised correctly; show the canton
  and the outside municipality instead of "review". Team call on the Excel wording.

## Measure, do not guess
- Hand check of 20 Prio 1 photos on https://app.superset.sh/page/handpr-fung-prio-1-otzbd6 (team, about
  15 min). Output goes to `data/splits/challenge_qc.jsonl` (Dijar).
- Every change above is then measured against those 20: hit rate per field, before and after.

## Order
1. Rule fixes + start the hand check in parallel.
2. Build the pipeline: `agent/pipeline.py` (stages), reuse the existing tools in `agent/tools/` as functions,
   two new structured prompts in `agent/prompts.py`, `loop.analyze()` switches to the pipeline behind a flag
   (`AGENT_PIPELINE=1`) so v3 stays available for comparison.
3. Test on the 20 hand-checked photos, then all 50 Prio 1 (about 15 USD).

## Moving to another machine
- `data/` and `.env` are not in git. Needed there: `ANTHROPIC_API_KEY`, `DATA_PIPELINE_URL`,
  `DATA_PIPELINE_TOKEN` in `.env`, and the current results (`data/results/`, JSON only, no images) copied over
  privately (zip: `agent/.cache/results_for_dijar.zip` on Said's laptop). Without them the history and the
  report start empty.
- Cost so far: 55.28 USD of the 150 USD session limit (`AGENT_SESSION_BUDGET`). The ledger is
  `data/results/costs.jsonl`, so it moves with the results.
