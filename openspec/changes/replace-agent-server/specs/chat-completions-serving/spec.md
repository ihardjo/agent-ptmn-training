## ADDED Requirements

### Requirement: Agent serves POST /v1/chat/completions
The system SHALL expose a `POST /v1/chat/completions` endpoint accepting the OpenAI Chat Completions request format. The `messages` array SHALL be forwarded to the LangGraph agent as-is.

#### Scenario: Non-streaming request returns a full response
- **WHEN** a client sends `{"model":"...","messages":[{"role":"user","content":"hi"}],"stream":false}`
- **THEN** the server SHALL return `200 OK` with `{"choices":[{"message":{"role":"assistant","content":"..."}}]}`

#### Scenario: Streaming request returns SSE delta chunks
- **WHEN** a client sends the same request with `"stream":true`
- **THEN** the server SHALL return `text/event-stream` with `data:` lines in Chat Completions chunk format, ending with `data: [DONE]`

#### Scenario: Unknown fields in request body are ignored
- **WHEN** a client sends extra fields not in the Chat Completions schema
- **THEN** the server SHALL process the request normally without error

### Requirement: Tool calls are included in the streaming response
When the agent invokes a tool during a request, the streaming response SHALL include the tool call and its result before the final assistant message.

#### Scenario: Tool call appears in stream before final answer
- **WHEN** the agent calls a tool (e.g., `get_current_time`) during a streaming request
- **THEN** the SSE stream SHALL include a `tool_calls` delta chunk followed by a `tool` role chunk with the result, before the final assistant text delta

### Requirement: No MLflow traces are created per request
The serving layer SHALL NOT register any MLflow decorators (`@invoke`, `@stream`) or `AgentServer` that would cause MLflow trace creation on each request.

#### Scenario: Request completes without MLflow experiment entry
- **WHEN** a request is processed by the new FastAPI handler
- **THEN** no new trace SHALL appear in the MLflow experiment configured by `MLFLOW_EXPERIMENT_ID`

### Requirement: Health check endpoint is available
The server SHALL expose `GET /health` returning `{"status":"ok"}` for liveness probes.

#### Scenario: Health check returns 200
- **WHEN** a client sends `GET /health`
- **THEN** the server SHALL return `200 OK` with `{"status":"ok"}`
