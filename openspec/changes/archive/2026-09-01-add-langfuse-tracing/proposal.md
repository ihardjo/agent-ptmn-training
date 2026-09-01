## Why

MLflow tracing in this project is tightly coupled to Databricks, which limits visibility when running locally and creates a hard dependency on Databricks infrastructure. Replacing the tracing layer with Langfuse provides richer per-span observability, user/session-level analytics, and keeps the option open to run the agent outside Databricks — while keeping the `AgentServer` serving contract and deferring evaluation changes.

## What Changes

- Remove `mlflow.langchain.autolog()` and replace with Langfuse `CallbackHandler` injected per request
- Replace `mlflow.update_current_trace()` session tagging with Langfuse `propagate_attributes` context manager
- Remove `setup_mlflow_git_based_version_tracking()` from `start_server.py`
- Add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` environment variables to `.env.example` and `databricks.yml`
- `evaluate_agent.py` is **explicitly out of scope** — MLflow evaluation remains unchanged

## Capabilities

### New Capabilities

- `langfuse-tracing`: LangGraph agent tracing via Langfuse `CallbackHandler`, with per-request session and user context propagation

### Modified Capabilities

<!-- None — no existing specs exist and no requirement-level behavior is changing. The agent's external API contract (ResponsesAgent / AgentServer) is untouched. -->

## Impact

- **`agent_server/agent.py`**: Remove `mlflow.langchain.autolog()`, remove `mlflow.update_current_trace()`, add Langfuse `CallbackHandler` and `propagate_attributes`
- **`agent_server/start_server.py`**: Remove `setup_mlflow_git_based_version_tracking()`
- **`agent_server/utils.py`**: No changes — MLflow types (`ResponsesAgentRequest`, `ResponsesAgentStreamEvent`) remain
- **`agent_server/evaluate_agent.py`**: No changes — deferred
- **`databricks.yml`**: Add Langfuse env vars alongside existing `MLFLOW_*` vars
- **`.env.example`**: Add Langfuse env vars
- **`pyproject.toml`**: Add `langfuse` dependency
- **Existing `MLFLOW_*` env vars**: Remain — `AgentServer` still requires them
