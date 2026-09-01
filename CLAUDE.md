# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

## Project Overview

This is a Databricks LangGraph agent built on the [`agent-langgraph`](https://github.com/databricks/app-templates/tree/main/agent-langgraph) template. It exposes a conversational agent via MLflow's `ResponsesAgent` interface (OpenAI Responses API-compatible), deployed as a Databricks App.

## Common Commands

All commands use `uv` (Python package manager, requires Python 3.11+).

```bash
# First-time setup: verifies tools, configures auth, starts server
uv run quickstart

# Start server + chat UI locally at http://localhost:8000
uv run start-app

# Start server only (no chat UI)
uv run start-server

# Explore available Databricks MCP tools
uv run discover-tools

# Run agent evaluation
uv run agent-evaluate

# Pre-deployment validation
uv run preflight
databricks bundle validate

# Deploy to Databricks
databricks bundle deploy
databricks bundle run agent_langgraph

# Run tests
pytest
```

**Test the API locally:**
```bash
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{"input":[{"role":"user","content":"hi"}]}'
```

**Query the deployed app** (OAuth token required — no PATs):
```bash
databricks auth token   # get token
curl -X POST <app-url>/invocations \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"input":[{"role":"user","content":"hi"}], "stream": true}'
```

## Architecture

```
agent_server/
  agent.py          ← All agent logic: tools, LangGraph graph, request handlers
  start_server.py   ← MLflow AgentServer entrypoint (registers agent.py, enables chat proxy)
  evaluate_agent.py ← MLflow evaluation harness
scripts/
  quickstart.py     ← First-run setup wizard
  start_app.py      ← Launches server + React chat UI
  preflight.py      ← Pre-deploy checks
  discover_tools.py ← Lists available MCP tools from Databricks
databricks.yml      ← DAB (Databricks Asset Bundle) — app config, env vars, permissions
pyproject.toml      ← Dependencies and uv script entry points
.env                ← Local config (copy from .env.example; never commit)
```

### Key Architectural Concepts

**ResponsesAgent wrapper** — `agent_server/agent.py` must use MLflow's `ResponsesAgent` interface. This is what enables AI Playground, Agent Evaluation, and Agent Monitoring integration. The agent is registered in `start_server.py` via `AgentServer(name="ResponsesAgent", enable_chat_proxy=True)`.

**`agent.py` is the single customization point** — add tools via `@tool` decorator, extend the LangGraph graph, or swap in MCP server tools. The file contains two async handlers:
- `stream_handler()` — core execution path, yields stream events
- `invoke_handler()` — collects stream into single response

**LLM endpoint** — defaults to `"databricks-gpt-5-2"` via `ChatDatabricks`. To use Unity AI Gateway for governed LLM access, pass the gateway endpoint name with `use_ai_gateway=True`.

**MCP tools** — `DatabricksMultiServerMCPClient` / `DatabricksMCPServer` connect to Databricks system MCP servers (Vector Search, Genie, code interpreter, UC functions). Tool connection code is present but commented out in `agent.py`; uncomment and grant permissions in `databricks.yml`.

**Authentication modes:**
- *App authorization (default)*: service principal, all users share permissions. Declare resources under `resources.apps.<app>.resources` in `databricks.yml`.
- *User authorization*: per-user permissions; call `get_user_workspace_client()` inside `stream_handler`/`invoke_handler` and set `user_api_scopes` in `databricks.yml`.

**Environment variables** (set in `databricks.yml` for deployed app, in `.env` for local):
- `MLFLOW_TRACKING_URI` — `databricks`
- `MLFLOW_REGISTRY_URI` — `databricks-uc`
- `MLFLOW_EXPERIMENT_ID` — references the experiment resource in the bundle

**Compute constraint** — only `medium` and `large` compute sizes are supported for Databricks Apps.

## Deployment Targets in `databricks.yml`

- **`dev`** (default) — development mode, local workspace
- **`prod`** — production mode; set workspace host before deploying
