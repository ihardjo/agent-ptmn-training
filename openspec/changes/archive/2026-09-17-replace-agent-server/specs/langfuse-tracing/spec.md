## MODIFIED Requirements

### Requirement: Session context is propagated to traces
Each trace SHALL carry a `session_id` when the request supplies one, enabling multi-turn conversations to be grouped in the Langfuse session view. The `X-Session-Id` request header is the primary source. On the `/invocations` route, `context.conversation_id` in the request body SHALL be used when the header is absent. When neither is present, the trace SHALL be created without a `session_id`.

#### Scenario: Request with X-Session-Id header groups traces into a session
- **WHEN** multiple requests share the same `X-Session-Id` header value
- **THEN** all corresponding Langfuse traces SHALL share the same `session_id` and be visible together in the Langfuse Sessions view

#### Scenario: Request with conversation_id groups traces into a session
- **WHEN** requests to `/invocations` carry no `X-Session-Id` header but share the same `context.conversation_id`
- **THEN** all corresponding Langfuse traces SHALL share that value as their `session_id` and be visible together in the Langfuse Sessions view

#### Scenario: Request without conversation_id produces a trace without session grouping
- **WHEN** a request supplies neither an `X-Session-Id` header nor a `context.conversation_id`
- **THEN** the Langfuse trace SHALL be created without a `session_id` (no error, no crash)

### Requirement: Existing MLflow serving infrastructure is unaffected
The plain FastAPI serving layer SHALL NOT depend on `AgentServer`, `@invoke`/`@stream` decorators, or `ResponsesAgent` types. `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_ID` are no longer required for agent startup.

#### Scenario: Agent starts without MLFLOW_* vars set
- **WHEN** `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_ID` are absent from the environment
- **THEN** the agent SHALL start successfully and serve requests via the FastAPI handler

#### Scenario: Agent starts without Langfuse configured
- **WHEN** the `LANGFUSE_*` env vars are absent
- **THEN** the agent SHALL start successfully and serve requests, with no tracing sent to Langfuse
