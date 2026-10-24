# Zentral Hack 2026: Fotos verorten, Kanton Schwyz

Challenge "KI-Bilderkennung" of the Staatsarchiv Schwyz (category AI Agentic): 603 uncatalogued photos
(`SG.CIV.17.*`, taken 2003 to 2013), 50 of them Prio 1. Not when (every photo has its EXIF date) but
**where**: Ortschaft, Gemeinde, Gebäude, See/Fluss/Berg, Strasse, each with its sources and a measured
confidence, and one Excel row per photo. What cannot be proven stays empty ("nicht bestimmbar") and is
flagged for review. Details: [CHALLENGE_BRIEF](docs/CHALLENGE_BRIEF.md).

How it works (agent v7): three independent Claude investigations, the official registers (GWR, OSM,
KGS, swissNAMES3D) at the subject, an image check against photos taken there (LightGlue), a blind final
judge, and confidence tiers whose number is the hit rate measured by hand (40 Prio-1 photos: 38 right,
35 of 35 right at 90 % or more).

## Starten

Needs Python 3.12, Node 20+, an Anthropic API key and access to the team's data server.

```bash
# 1. Backend (FastAPI on :8000)
python3.12 -m venv .venv && .venv/bin/pip install -r agent/requirements.txt
cat > .env <<'ENV'
ANTHROPIC_API_KEY=...
DATA_PIPELINE_URL=https://zhdata.vatra.sh
DATA_PIPELINE_TOKEN=...
ENV
unzip -o agent/reports/results.zip -d data/      # the 50 Prio-1 results (JSON, no images)
.venv/bin/uvicorn agent.server.app:app --port 8000

# 2. Frontend (Next.js on :3000), second terminal
cd frontend && npm install
NEXT_PUBLIC_MODE=live NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Then open http://localhost:3000: the map desk with all photos, a photo opens its result, sources, the
agent's steps and review (Bestätigen / Korrigieren). "Excel herunterladen" gives the deliverable
(`/export.xlsx`, sheets Metadaten and Methode); `/nachweis` shows the hand check and the method.
"Foto hochladen" analyses a new photo live. `NEXT_PUBLIC_MODE=mock` runs the frontend without a backend.

Ready-made results without starting anything: `agent/reports/` (Excel, HTML reports without images).

## Who owns what

| Scope | Owner | Folder | Doc |
|---|---|---|---|
| Data: scraping, splitting, embeddings, index, eval set | Dijar | `data_pipeline/` | [SCOPE_1_DATA](docs/SCOPE_1_DATA.md) |
| Agent: v7 pipeline, tools, FastAPI backend, export | Said, then Dijar | `agent/` | [SCOPE_2_AGENT](docs/SCOPE_2_AGENT.md) |
| Frontend: map desk, review, upload, Nachweis | Timo and Said | `frontend/` | [SCOPE_3_FRONTEND](docs/SCOPE_3_FRONTEND.md) |

Shared: [CONTRACTS](docs/CONTRACTS.md) (read first), `contracts/` (schemas + fixtures).

## Docs
- [RESEARCH](docs/RESEARCH.md): verified facts on sources, licenses, swisstopo, rules
- [ARCHITECTURE](docs/ARCHITECTURE.md): system overview, models, costs
- [CONTRACTS](docs/CONTRACTS.md): data shapes and API, single source of truth

## Rules
- `data/` is never committed. Staatsarchiv images are not openly licensed.
- Keys via env vars only. See [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) for AI agent rules.

## Git workflow
- One repo, one branch per person: `dijar/data`, `said/agent`, `timo/frontend`. Work and push only on your own branch.
- Each branch only touches its owner's folder (`data_pipeline/`, `agent/`, `frontend/`), so merges into `main` do not conflict.
- Merge into `main` at the integration checkpoints (Fri 23:00, Sat 10:00, Sat 14:00 code freeze). Pull `main` into your branch after each merge.
- Shared files (`docs/`, `contracts/`, `CLAUDE.md`, `AGENTS.md`) change only on `main`, after the team agrees.

## For teammates
Open this repo with Claude Code or Codex and say who you are, e.g. "I'm Timo, read the repo and tell me what I do." `CLAUDE.md` / `AGENTS.md` route the agent to your branch and scope. Build your scope now; Friday and Saturday are for merging, the eval run and the demo.
