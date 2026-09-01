## 1. Dependencies

- [x] 1.1 Add `langfuse` to `pyproject.toml` dependencies
- [x] 1.2 Run `uv lock` to update the lockfile

## 2. Environment Configuration

- [x] 2.1 Add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` (optional) to `.env.example` with comments distinguishing them from `MLFLOW_*` serving vars
- [x] 2.2 Add Langfuse env vars to `databricks.yml` under the app's `config.env` section (alongside existing `MLFLOW_*` vars)

## 3. Agent Tracing

- [x] 3.1 In `agent_server/agent.py`: remove `import mlflow` (keep only if still needed elsewhere), remove `mlflow.langchain.autolog()`, and remove `mlflow.update_current_trace()`
- [x] 3.2 Add `from langfuse.langchain import CallbackHandler` and `from langfuse import propagate_attributes` imports to `agent_server/agent.py`
- [x] 3.3 Instantiate `langfuse_handler = CallbackHandler()` as a module-level singleton in `agent_server/agent.py`
- [x] 3.4 In `stream_handler`: wrap `agent.astream()` call with `with propagate_attributes(session_id=session_id):` context manager
- [x] 3.5 Pass `config={"callbacks": [langfuse_handler]}` to `agent.astream()` call in `stream_handler`

## 4. Server Cleanup

- [x] 4.1 In `agent_server/start_server.py`: remove `setup_mlflow_git_based_version_tracking()` call and its import

## 5. Verification

- [x] 5.1 Run `uv run start-app` locally and send a test request; confirm a trace appears in Langfuse UI
- [x] 5.2 Send two requests with the same `conversation_id`; confirm they are grouped under the same session in Langfuse
- [x] 5.3 Confirm agent starts successfully without `LANGFUSE_*` env vars set (graceful degradation)
- [x] 5.4 Run `pytest` to confirm no regressions
- [x] 5.5 Run `databricks bundle validate` to confirm `databricks.yml` is valid
