# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

## Project Overview

This is a Databricks LangGraph agent originally based on the [`agent-langgraph`](https://github.com/databricks/app-templates/tree/main/agent-langgraph) template. It exposes a conversational agent as a plain FastAPI app serving the OpenAI Chat Completions interface, deployed as a Databricks App. The MLflow `AgentServer` layer the template shipped with has been removed; observability is handled by Langfuse.

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
  routes.py         ← FastAPI routes: /health, /v1/chat/completions, /invocations
  models.py         ← Pydantic request/response models
  tools.py          ← Tool definitions
  utils.py          ← Shared helpers (per-user workspace client, auth)
  start_server.py   ← FastAPI app + uvicorn entrypoint, chat proxy middleware
scripts/
  quickstart.py     ← First-run setup wizard
  start_app.py      ← Launches server + React chat UI
  preflight.py      ← Pre-deploy checks
  discover_tools.py ← Lists available MCP tools from Databricks
app.yaml            ← Databricks Apps config — used by UI/Git deploys
manifest.yaml       ← App metadata and resource specs
databricks.yml      ← DAB (Databricks Asset Bundle) — used by the GitHub Actions deploy
pyproject.toml      ← Dependencies and uv script entry points
.env                ← Local config (copy from .env.example; never commit)
```

### Key Architectural Concepts

**Plain FastAPI serving** — `start_server.py` builds a `FastAPI` app, mounts `routes.py`, and adds `ChatProxyMiddleware` to proxy UI paths to the chat app on `CHAT_APP_PORT`. There is no MLflow `AgentServer`, no `@invoke`/`@stream` decorators, and no `ResponsesAgent` types. Routes: `POST /v1/chat/completions` (primary, OpenAI-compatible), `POST /invocations` (compatibility shim), `GET /health`.

**`agent.py` is the single customization point** — add tools via `@tool` decorator, extend the LangGraph graph, or swap in MCP server tools.

**Observability** — Langfuse, via a per-request `CallbackHandler`. Gated on `LANGFUSE_HOST`; the agent starts fine without any `LANGFUSE_*` vars, just untraced.

**LLM endpoint** — defaults to `"databricks-gpt-5-2"` via `ChatDatabricks`. To use Unity AI Gateway for governed LLM access, pass the gateway endpoint name with `use_ai_gateway=True`.

**MCP tools** — `DatabricksMultiServerMCPClient` / `DatabricksMCPServer` connect to Databricks system MCP servers (Vector Search, Genie, code interpreter, UC functions). Tool connection code is present but commented out in `agent.py`; uncomment and grant permissions in `databricks.yml`.

**Authentication modes:**
- *App authorization (default)*: service principal, all users share permissions. Declare resources under `resources.apps.<app>.resources` in `databricks.yml`.
- *User authorization*: per-user permissions; call `get_user_workspace_client()` with the incoming FastAPI `Request` and set `user_api_scopes` in `databricks.yml`.

**Environment variables** (set in `app.yaml` for the deployed app, in `.env` for local):
- `CHAT_APP_PORT` / `CHAT_PROXY_TIMEOUT_SECONDS` / `API_PROXY` — chat UI proxy wiring
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` — tracing (optional)

**Compute constraint** — only `medium` and `large` compute sizes are supported for Databricks Apps.

## Deployment Targets in `databricks.yml`

- **`dev`** (default) — development mode, local workspace
- **`prod`** — production mode; set workspace host before deploying
