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

# Upload the committed wiki bundle to the Volume (idempotent; never touches notes/)
uv run seed-wiki

# Check the seed and the live Volume against OKF v0.2 conformance
uv run check-okf

# Check the skills tier against the Agent Skills authoring standard
uv run check-skills

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
  backends.py       ← VolumeBackend: the /wiki/ tier over the UC Files API
  okf.py            ← Open Knowledge Format parsing, conformance, conformant writes
  privacy.py        ← The person-name set the write guard and the eval both use
  utils.py          ← Shared helpers (per-user workspace client, auth)
  start_server.py   ← FastAPI app + uvicorn entrypoint, chat proxy middleware
wiki_seed/          ← Committed OKF bundle uploaded to the wiki Volume
skills/             ← The agent's skill menu, mounted read-only at /skills/
  REGISTRY.md       ← Purpose, owner, version, dependencies, eval status per skill
  SECURITY-REVIEW.md← The published review checklist, completed against every skill
  <skill>/SKILL.md  ← One skill; only `name` + `description` reach the prompt
scripts/
  quickstart.py     ← First-run setup wizard
  start_app.py      ← Launches server + React chat UI
  preflight.py      ← Pre-deploy checks
  discover_tools.py ← Lists available MCP tools from Databricks
  seed_wiki.py      ← Uploads wiki_seed/ to the Volume's openwiki/ tree
  check_okf.py      ← Checks the seed and the Volume for OKF conformance
  check_skills.py   ← Checks the skills tier for authoring-standard conformance
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

**Filesystem tiers** — the agent reads and writes through one `CompositeBackend`
whose path prefix states a file's lifetime, who wrote it, and whether the agent
may write there. Built in `agent_server/agent.py:build_backend()`:

| Prefix | Lifetime | Written by | Agent may write |
|---|---|---|---|
| `/` | the thread | the agent | yes (scratch, discarded) |
| `/skills/` | a merge | people, via the repo | no — deny rule |
| `/wiki/openwiki/` | a sync | people, via OpenWiki | no — deny rule |
| `/wiki/notes/` | durable | the agent | yes |

Both `/wiki/` prefixes are subdirectories of **one** Unity Catalog Volume in the
Jakarta workspace, reached over the Files API because Databricks Apps have no
FUSE mount for Volumes. A volume grant is per-volume, not per-path, so
read-only on `/wiki/openwiki/` is enforced by the `FilesystemPermission` deny
rule in `filesystem_permissions()` and **not** by the grant — treat a gap there
as a correctness bug. Note `/wiki/` itself is deliberately not a route: a loose
`/wiki/x.md` falls through to scratch rather than quietly becoming durable.

**The skill menu** — `/skills/` holds ten skills: five carrying real procedures
and five deliberately over-broad *distractors*, which compete for selection and
then redirect or decline. A distractor competes through its **description**
only; its body is correct, so a mis-selection costs a wasted read and never a
wrong answer. Bodies that would contradict the system prompt's safety rules are
prohibited — the enterprise standard rates that High risk. Skill reads are
identified in a trace by the `/skills/` **path prefix**, not by tool name:
`read_file` serves `/wiki/` too.

Each tier is an **OKF v0.2** bundle (markdown + YAML frontmatter). The notes
write path supplies `type` and `generated` itself rather than asking the model
for them, so the bundle stays conformant by construction.

**Environment variables** (set in `app.yaml` for the deployed app, in `.env` for local):
- `CHAT_APP_PORT` / `CHAT_PROXY_TIMEOUT_SECONDS` / `API_PROXY` — chat UI proxy wiring
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` — tracing (optional)
- `DATABRICKS_WIKI_VOLUME` — the wiki Volume path (optional; without it the
  agent starts and serves normally, just with no `/wiki/` tier)

**Compute constraint** — only `medium` and `large` compute sizes are supported for Databricks Apps.

## Deployment Targets in `databricks.yml`

- **`dev`** (default) — development mode, local workspace
- **`prod`** — production mode; set workspace host before deploying
