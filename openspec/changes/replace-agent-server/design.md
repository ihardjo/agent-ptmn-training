## Context

The current serving layer is built on MLflow's `AgentServer`, which wraps FastAPI internally and exposes `/invocations` using the OpenAI Responses API format. All request/response types (`ResponsesAgentRequest`, `ResponsesAgentStreamEvent`, etc.) come from `mlflow.types.responses`. Even after removing `autolog`, the `@invoke`/`@stream` decorators still create MLflow traces for every request.

This design replaces that entire layer with a direct FastAPI application implementing the OpenAI Chat Completions format (`POST /v1/chat/completions`). The LangGraph agent internals and Langfuse tracing remain unchanged.

## Goals / Non-Goals

**Goals:**
- Eliminate MLflow trace creation entirely (no `@invoke`/`@stream`, no `AgentServer`)
- Expose `POST /v1/chat/completions` compatible with any OpenAI client
- Support both streaming (SSE) and non-streaming responses
- Preserve Langfuse session propagation via `X-Session-Id` request header
- Keep `databricks.yml` / `app.yaml` deployment config unchanged
- Implement on a git branch (`experiment/plain-fastapi-serving`) — not merged until validated

**Non-Goals:**
- Rewriting `evaluate_agent.py` (deferred)
- Removing `mlflow` from `pyproject.toml` (still needed by evaluate)
- Reimplementing the `/chat` React proxy (it already speaks Chat Completions)
- Supporting OpenAI Responses API format on the new endpoint

## Decisions

### Decision 1: OpenAI Chat Completions format over custom schema

**Chosen:** Implement `/v1/chat/completions` matching OpenAI's schema.

**Why:** The LangGraph agent already receives messages in Chat Completions format internally (via `to_chat_completions_input()`). Exposing this directly removes the conversion layer. Any OpenAI SDK client, LangChain caller, or the existing React chat UI can talk to it without modification.

**Alternative considered:** Custom schema. Rejected — loses all interoperability for no gain.

---

### Decision 2: Session ID via `X-Session-Id` header

**Chosen:** Read session ID from `X-Session-Id` request header in the FastAPI route handler, pass to `propagate_attributes(session_id=...)`.

**Why:** Chat Completions format has no built-in `context.conversation_id` field (that was ResponsesAgent-specific). Headers are the idiomatic way to pass per-request metadata in HTTP APIs. The React chat UI can set this header.

**Alternative considered:** Add `session_id` to the request body as a custom field. Valid but non-standard — headers are cleaner for metadata that doesn't belong in the message payload.

---

### Decision 3: Write own LangGraph → Chat Completions SSE converter

**Chosen:** Replace `output_to_responses_items_stream` and `create_text_delta` with a new `stream_to_chat_completions_chunks()` generator that yields Chat Completions delta objects.

**Why:** The existing converters are coupled to `ResponsesAgentStreamEvent` types. Chat Completions SSE uses a different envelope: `data: {"choices":[{"delta":{"content":"..."}}]}\n\n`. The conversion logic from LangGraph `messages` events to text deltas is straightforward and can be written in ~30 lines.

**Format:**
```
data: {"id":"...","object":"chat.completion.chunk","choices":[{"delta":{"role":"assistant"},"index":0}]}
data: {"id":"...","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hello"},"index":0}]}
data: {"id":"...","object":"chat.completion.chunk","choices":[{"delta":{"content":" world"},"index":0}]}
data: [DONE]
```

---

### Decision 4: Keep `mlflow` in `pyproject.toml`

**Chosen:** Do not remove `mlflow` from dependencies on this branch.

**Why:** `evaluate_agent.py` still imports from `mlflow.genai`. Removing the package would break the evaluation script. Decoupling evaluation is a separate future change.

## Risks / Trade-offs

- **API contract break** — Any caller using the current `/invocations` + ResponsesAgent format must update. On this experimental branch that's only the test `curl` commands in docs; the React chat UI speaks Chat Completions already. → Mitigation: document the new format clearly.
- **LangGraph tool call streaming** — The current `output_to_responses_items_stream` handles tool call items specially. The new converter must correctly handle `ToolMessage` outputs and not expose internal tool call details to the caller unless intentional. → Mitigation: test tool-calling flows explicitly.
- **Branch drift** — As an experimental branch, it will diverge from main over time. → Mitigation: keep scope tight, avoid unrelated changes, rebase periodically.
- **Losing `AgentServer`'s workers config** — `AgentServer` handles multi-worker uvicorn setup. The new `FastAPI` app must be launched with explicit worker configuration to match. → Mitigation: pass `workers` arg to `uvicorn.run()`.

## Migration Plan

1. Create branch: `git checkout -b experiment/plain-fastapi-serving`
2. Rewrite `start_server.py` — swap `AgentServer` for `FastAPI()`
3. Rewrite `agent.py` — remove decorators, add route handlers, own Pydantic models
4. Rewrite `utils.py` — remove MLflow imports, add Chat Completions stream converter
5. Test locally: `uv run start-app`, verify traces in Langfuse, verify no MLflow experiment entries
6. Test the chat UI at `localhost:3000` / deployed app URL

**Rollback:** Switch back to `main`. The branch is isolated — no production impact.

## Open Questions

- Should the endpoint be `/v1/chat/completions` (OpenAI-standard path) or keep `/invocations` (Databricks-standard path) for compatibility with `databricks.yml`'s `API_PROXY` env var?
- Should tool call results be included in the streaming response as separate `tool_calls` delta chunks, or collapsed into the final assistant message?
