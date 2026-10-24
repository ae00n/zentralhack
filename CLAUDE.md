# Instructions for AI coding agents (Claude Code, Codex, others)

Zentral Hack 2026, Kanton Schwyz challenge: locate and date historical photos with an AI agent.

## Handover (Sat 24 Oct, night; team decision)
Timo is asleep, so the scopes moved for the rest of the night:
- **Dijar = Data + Agent/backend**: `data_pipeline/` and `agent/`, branches `dijar/data` and `said/agent`.
- **Said = Frontend**: `frontend/`, branch `timo/frontend` (continue from Timo's latest commit).
- **Timo = Frontend** again when he is back; he and Said coordinate on `timo/frontend`.
- Results for the other machine: `agent/reports/` (Excel, reports without images, `results.zip` with `data/results` as JSON, no images) may be committed. That is the one exception to the `data/` rule below.

## Start here (first thing, every session)
1. The human tells you their name. Map it (see the handover above): Dijar = Data + Agent, Said = Frontend, Timo = Frontend. Unknown name: ask.
2. Make sure you are on their branch: `git checkout dijar/data` or `said/agent` (Dijar), `timo/frontend` (Said, Timo), then `git pull`.
3. Read `docs/CONTRACTS.md`, then their scope file, then `docs/ARCHITECTURE.md`.
4. Work through the **Build order** in the scope file, top to bottom. Each item has a check; it is done when the check passes. Friday and Saturday are for merging, the eval run, the demo and the pitch.

A good first prompt: "I'm Timo. Read the repo docs, explain my scope in 10 bullets, list what I need installed, and start on the first unfinished item of my build order."

## Before you write anything
1. Read `docs/CONTRACTS.md`. It is the single source of truth for data shapes and APIs.
2. Read your own scope file. If you do not know which scope the human owns, ask them.
   - Data (Dijar): `docs/SCOPE_1_DATA.md`, folder `data_pipeline/`
   - Agent + backend + eval (Dijar since the handover, before: Said): `docs/SCOPE_2_AGENT.md`, folder `agent/`
   - Frontend (Said since the handover, and Timo): `docs/SCOPE_3_FRONTEND.md`, folder `frontend/`

## Hard rules
- Stay inside your owned folder. Do not edit another scope's folder.
- Never do another scope's work, not even as an experiment, a "quick test", a prototype or a throwaway script outside the repo. That covers prompts, agent runs and eval runs (Agent), UI (Frontend) and data or index work (Data). If something in another scope blocks you or could be better, write down what you measured and what you need, give it to your human to pass on, and stop. Do not offer to do it yourself.
- Never edit `contracts/` or `docs/CONTRACTS.md` unless the whole team agreed. Then update schemas, fixtures and the doc in one commit.
- Never commit `data/`, images, `.env`, API keys or tokens. Keys come from env vars only (`ANTHROPIC_API_KEY`). Exception: `agent/reports/results.zip` (see the handover).
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
- Merge your branch into `main` at least once a day before the event (small merges, fewer conflicts), then at the checkpoints Fri 23:00, Sat 10:00 and the Sat 14:00 code freeze. Pull `main` into your branch after every merge.
- Shared files (`docs/`, `contracts/`, `CLAUDE.md`, `AGENTS.md`) change only on `main`, after the team agrees.
