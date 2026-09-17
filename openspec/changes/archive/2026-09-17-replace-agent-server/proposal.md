## Why

MLflow's `AgentServer` and `ResponsesAgent` types couple the serving layer tightly to Databricks — every request still creates an MLflow trace even after migrating observability to Langfuse, and the agent cannot run outside a Databricks workspace. Replacing the serving layer with plain FastAPI implementing the OpenAI Chat Completions format removes this coupling, stops MLflow trace creation entirely, and makes the agent portable to any Python-capable host.

This is implemented as an **experimental branch** (`experiment/plain-fastapi-serving`) — not merged to main until validated. The goal is to prove the architecture works and learn the shape of the problem.

## What Changes

- Remove `AgentServer`, `@invoke`, `@stream` decorators from `start_server.py` and `agent.py`
- Remove all `mlflow.types.responses` types (`ResponsesAgentRequest`, `ResponsesAgentResponse`, `ResponsesAgentStreamEvent`, `to_chat_completions_input`, `create_text_delta`, `output_to_responses_items_stream`)
- Replace with a plain `FastAPI` app exposing `POST /v1/chat/completions` (streaming and non-streaming)
- Define own Pydantic request/response models matching OpenAI Chat Completions schema
- Write own LangGraph → Chat Completions SSE stream converter (replaces `output_to_responses_items_stream`)
- Replace `mlflow.genai.agent_server.get_request_headers()` in `utils.py` with FastAPI `Request` injection
- `evaluate_agent.py` is **explicitly out of scope** — untouched on this branch
- `mlflow` remains in `pyproject.toml` (still needed by `evaluate_agent.py`)

## Capabilities

### New Capabilities

- `chat-completions-serving`: FastAPI app serving `POST /v1/chat/completions` with streaming SSE, session context via `X-Session-Id` header, Langfuse tracing per-request

### Modified Capabilities

- `langfuse-tracing`: Session ID source changes from `request.context.conversation_id` (ResponsesAgent) to `X-Session-Id` request header (Chat Completions). Core tracing behavior unchanged.

## Impact

- **`agent_server/agent.py`**: Full rewrite of handler functions — remove decorators and MLflow types, add FastAPI route handlers
- **`agent_server/start_server.py`**: Replace `AgentServer` with `FastAPI()`, wire routes
- **`agent_server/utils.py`**: Remove MLflow imports; replace `get_request_headers()` with FastAPI `Request`; rewrite `process_agent_astream_events` to yield Chat Completions delta chunks
- **`agent_server/evaluate_agent.py`**: No changes
- **`databricks.yml` / `app.yaml`**: No changes — Databricks App still runs the same `uv run start-app` command
- **API contract**: Changes from ResponsesAgent format to OpenAI Chat Completions format — callers must update
- **Chat UI at `databricksapps.com`**: Compatible — the React proxy speaks Chat Completions natively
