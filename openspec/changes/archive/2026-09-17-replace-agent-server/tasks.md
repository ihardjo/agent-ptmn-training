## 1. Branch Setup

- [x] 1.1 Create git branch: `git checkout -b experiment/plain-fastapi-serving`

## 2. Pydantic Models

- [x] 2.1 In `agent_server/agent.py`: define `ChatMessage(role, content)` and `ChatRequest(model, messages, stream)` Pydantic models
- [x] 2.2 Define `ChatCompletionChunk` and `ChatCompletionResponse` Pydantic models for non-streaming responses

## 3. Stream Converter

- [x] 3.1 In `agent_server/utils.py`: remove `mlflow.genai.agent_server` and `mlflow.types.responses` imports
- [x] 3.2 Remove `get_request_headers()` usage; replace `get_user_workspace_client()` to use FastAPI `Request` parameter instead
- [x] 3.3 Write `stream_to_chat_completions_chunks()` async generator that converts LangGraph `astream` events to Chat Completions SSE delta strings
- [x] 3.4 Handle tool call events in `stream_to_chat_completions_chunks()` — emit `tool_calls` delta chunks before final assistant text

## 4. Route Handlers

- [x] 4.1 In `agent_server/agent.py`: remove `@invoke()` and `@stream()` decorators and all `mlflow.genai.agent_server` / `mlflow.types.responses` imports
- [x] 4.2 Add `POST /v1/chat/completions` route handler: read `X-Session-Id` header, call `init_agent()`, stream via `stream_to_chat_completions_chunks()`
- [x] 4.3 Add `GET /health` route handler returning `{"status": "ok"}`

## 5. Server Wiring

- [x] 5.1 In `agent_server/start_server.py`: replace `AgentServer(...)` with `app = FastAPI()`
- [x] 5.2 Import and register route handlers from `agent.py` onto the FastAPI app
- [x] 5.3 Configure `uvicorn.run()` with workers and host/port matching the previous `AgentServer` behaviour

## 6. Langfuse Session Update

- [x] 6.1 In `agent_server/utils.py`: update `get_session_id()` (or remove it) — session ID now comes from `X-Session-Id` header passed directly into the route handler
- [x] 6.2 In the route handler: pass `session_id` from `X-Session-Id` header to `propagate_attributes(session_id=...)`

## 7. Verification

- [x] 7.1 Run `uv run start-app` and send `curl -X POST http://localhost:8000/v1/chat/completions -d '{"model":"agent","messages":[{"role":"user","content":"What time is it?"}],"stream":true}'`; confirm SSE response
- [x] 7.2 Send same request with `-H "X-Session-Id: test-session-001"`; confirm session appears in Langfuse
- [x] 7.3 Check Databricks MLflow experiment — confirm no new trace entries were created
- [ ] 7.4 Open chat UI at `localhost:3000`; confirm it connects and responds correctly
- [x] 7.5 Run `pytest` to confirm no regressions
- [x] 7.6 Run `databricks bundle validate` to confirm `databricks.yml` is still valid
