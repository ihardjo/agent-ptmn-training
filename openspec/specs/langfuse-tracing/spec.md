# Langfuse Tracing

## Purpose

Defines the observability requirements for exporting agent traces to Langfuse. Covers trace generation for every agent invocation, session context propagation, credential configuration, and ensuring existing MLflow serving infrastructure remains unaffected.

## Requirements

### Requirement: Agent requests are traced to Langfuse
Every invocation of the agent (streaming or non-streaming) SHALL produce a trace in Langfuse containing all LangGraph node executions, LLM calls, tool calls, inputs, outputs, latencies, and token counts.

#### Scenario: Successful streaming request produces a trace
- **WHEN** a client sends a POST to `/invocations` with a user message
- **THEN** a trace SHALL appear in Langfuse within the configured flush interval, containing at least one LLM span with prompt and completion content

#### Scenario: Tool call is captured in trace
- **WHEN** the agent invokes a tool (e.g., `get_current_time`) during a request
- **THEN** the Langfuse trace SHALL contain a span for that tool call with its input arguments and output

### Requirement: Session context is propagated to traces
Each trace SHALL carry the `session_id` derived from `request.context.conversation_id` (or `custom_inputs.session_id` as fallback), enabling multi-turn conversations to be grouped in the Langfuse session view.

#### Scenario: Request with conversation_id groups traces into a session
- **WHEN** multiple requests share the same `conversation_id`
- **THEN** all corresponding Langfuse traces SHALL share the same `session_id` and be visible together in the Langfuse Sessions view

#### Scenario: Request without conversation_id produces a trace without session grouping
- **WHEN** a request has no `conversation_id` and no `session_id` in `custom_inputs`
- **THEN** the Langfuse trace SHALL be created without a `session_id` (no error, no crash)

### Requirement: Langfuse credentials are configurable via environment variables
The system SHALL read Langfuse credentials (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`) and optionally a host (`LANGFUSE_HOST`) from environment variables, with no credentials hard-coded in source.

#### Scenario: Self-hosted Langfuse instance is used
- **WHEN** `LANGFUSE_HOST` is set to an internal URL
- **THEN** all traces SHALL be sent to that host instead of Langfuse Cloud

#### Scenario: Missing Langfuse credentials do not crash the agent
- **WHEN** `LANGFUSE_PUBLIC_KEY` or `LANGFUSE_SECRET_KEY` are absent
- **THEN** the agent SHALL start and serve requests; trace export SHALL fail silently with a logged warning (not an unhandled exception)

### Requirement: Existing MLflow serving infrastructure is unaffected
The `AgentServer`, `@invoke`/`@stream` decorators, and all `ResponsesAgent` types SHALL remain unchanged. `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_ID` SHALL continue to be required for agent startup.

#### Scenario: Agent starts without Langfuse configured
- **WHEN** Langfuse env vars are absent but `MLFLOW_*` vars are present
- **THEN** the agent SHALL start successfully and serve requests, with no tracing sent to Langfuse
