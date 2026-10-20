# Instructions for AI coding agents (Claude Code, Codex, others)

Zentral Hack 2026, Kanton Schwyz challenge: locate and date historical photos with an AI agent.

## Before you write anything
1. Read `docs/CONTRACTS.md`. It is the single source of truth for data shapes and APIs.
2. Read your own scope file. If you do not know which scope the human owns, ask them.
   - Data (Dijar): `docs/SCOPE_1_DATA.md`, folder `data_pipeline/`
   - Agent + backend + eval (Said): `docs/SCOPE_2_AGENT.md`, folder `agent/`
   - Frontend (Timo): `docs/SCOPE_3_FRONTEND.md`, folder `frontend/`

## Hard rules
- Stay inside your owned folder. Do not edit another scope's folder.
- Never edit `contracts/` or `docs/CONTRACTS.md` unless the whole team agreed. Then update schemas, fixtures and the doc in one commit.
- Never commit `data/`, images, `.env`, API keys or tokens. Keys come from env vars only (`ANTHROPIC_API_KEY`).
- Staatsarchiv Schwyz images are NOT openly licensed. Never publish them, upload them anywhere public, or put them in git.
- UI strings are German. Code, comments and docs are English.
- No em dashes anywhere (code, comments, UI, docs, commits).
- Agent output must never leak eval cards into its own tools (see the eval leakage rule in CONTRACTS.md section 4).

## Running things (filled in during the skeleton step)
- Data pipeline: `TODO`
- Backend: `TODO` (FastAPI on :8000)
- Frontend: `TODO` (Next.js on :3000, `NEXT_PUBLIC_MODE=mock|live|demo`)

## Git workflow
- One repo, one branch per person: `dijar/data`, `said/agent`, `timo/frontend`. Work and push only on your own branch.
- Each branch only touches its owner's folder (`data_pipeline/`, `agent/`, `frontend/`), so merges into `main` do not conflict.
- Merge into `main` at the integration checkpoints (Fri 23:00, Sat 10:00, Sat 14:00 code freeze). Pull `main` into your branch after each merge.
- Shared files (`docs/`, `contracts/`, `CLAUDE.md`, `AGENTS.md`) change only on `main`, after the team agrees.
