"""Scope 2 (Agent): agent loop, tools, FastAPI backend and eval runner.

    python -m agent.run <photo_id>          # one photo, CLI
    uvicorn agent.server.app:app --port 8000 # backend (AGENT_FAKE=1 replays the fixture)
    python -m agent.eval.runner              # eval run
"""
