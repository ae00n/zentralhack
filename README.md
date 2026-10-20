# Zentral Hack 2026: Historische Fotos, Kanton Schwyz

Challenge "KI-Bilderkennung für historische Fotos" (Kanton Schwyz, category AI Agentic).
Our pitch: thousands of archive photos have no date and no exact location. Our agent finds place and period, with evidence and confidence, and turns the archive into a time journey.

Hack: Fri 23 Oct 19:00 to Sat 24 Oct 17:00 (submission + presentations at 17:00).

## Who owns what

| Scope | Owner | Folder | Doc |
|---|---|---|---|
| Data: scraping, splitting, embeddings, index, eval set | Dijar | `data_pipeline/` | [SCOPE_1_DATA](docs/SCOPE_1_DATA.md) |
| Agent: VLM loop, tools, FastAPI backend, eval runner | Said | `agent/` | [SCOPE_2_AGENT](docs/SCOPE_2_AGENT.md) |
| Frontend: map, time slider, then vs now, export, demo mode | Timo | `frontend/` | [SCOPE_3_FRONTEND](docs/SCOPE_3_FRONTEND.md) |

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
Open this repo with Claude Code or Codex and say who you are, e.g. "I'm Timo, read the repo and tell me what I do." `CLAUDE.md` / `AGENTS.md` route the agent to your branch and scope. No app code before Fri 19:00.
