## MODIFIED Requirements

### Requirement: Session context is propagated to traces
Each trace SHALL carry the `session_id` derived from the `X-Session-Id` request header, enabling multi-turn conversations to be grouped in the Langfuse session view. If the header is absent, the trace SHALL be created without a `session_id`.

#### Scenario: Request with X-Session-Id header groups traces into a session
- **WHEN** multiple requests share the same `X-Session-Id` header value
- **THEN** all corresponding Langfuse traces SHALL share the same `session_id` and be visible together in the Langfuse Sessions view

#### Scenario: Request without X-Session-Id produces a trace without session grouping
- **WHEN** a request has no `X-Session-Id` header
- **THEN** the Langfuse trace SHALL be created without a `session_id` (no error, no crash)

### Requirement: Existing MLflow serving infrastructure is unaffected
The plain FastAPI serving layer SHALL NOT depend on `AgentServer`, `@invoke`/`@stream` decorators, or `ResponsesAgent` types. `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_ID` are no longer required for agent startup on this branch.

#### Scenario: Agent starts without MLFLOW_* vars set
- **WHEN** `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_ID` are absent from the environment
- **THEN** the agent SHALL start successfully and serve requests via the FastAPI handler
