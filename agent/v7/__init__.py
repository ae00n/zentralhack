"""v7 analysis: several independent Claude attempts, grounded in the registers, checked against imagery at
the spot, picked by a judge, scored by tier.

1. vision: Google Cloud Vision web detection (pages and entities that show the same scene), cached.
2. attempt (x3): Claude with zoom, web search, geo.admin search and the offline registers. The attempts see
   different hints (all hints / web hints only / the photo alone), so their agreement means something.
   Each answer names its subject point, which must come from a register or search hit, never typed.
3. ground: subject point -> Gemeinde (polygon), Ortschaft, street and building from the registers.
4. check: Mapillary and Commons photos taken within 150 m of the point, LightGlue against the photo.
5. judge: one Claude call sees the photo, the candidates and their check photos, and picks one or none.
6. tiers: A/B/C/unknown by rule (tiers.py); the shown confidence is the tier's measured hit rate once
   the hand check exists (agent/v7_tiers.json).

Returns the AnalysisResult of CONTRACTS section 3, so the server and the Excel export are unchanged.
Entry point: agent.v7.pipeline.analyze (CLI: python -m agent.v7.pipeline).
"""
