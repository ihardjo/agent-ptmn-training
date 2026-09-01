## Context

The agent currently uses `mlflow.langchain.autolog()` for automatic LangChain/LangGraph tracing, with traces sent to a Databricks-hosted MLflow experiment (`MLFLOW_EXPERIMENT_ID`). The serving layer (`AgentServer`, `ResponsesAgent` types) is also MLflow-owned but is kept untouched — it is the integration contract with Databricks AI Playground, Agent Monitoring, and the OpenAI Responses API. Only the observability backend is being swapped.

Langfuse supports LangGraph natively via `CallbackHandler`, which is injected per-request into `agent.astream()`. This avoids global monkey-patching (autolog) and gives per-request control over session and user context.

## Goals / Non-Goals

**Goals:**
- Replace `mlflow.langchain.autolog()` with per-request Langfuse `CallbackHandler`
- Propagate `session_id` (from `request.context.conversation_id`) to Langfuse traces via `propagate_attributes`
- Keep `MLFLOW_*` environment variables intact — `AgentServer` still requires them
- Add Langfuse credentials to `.env.example` and `databricks.yml`
- Support self-hosted Langfuse via `LANGFUSE_HOST` env var

**Non-Goals:**
- Replacing `evaluate_agent.py` (MLflow evaluation deferred)
- Replacing `AgentServer`, `@invoke`, `@stream`, or any `ResponsesAgent` types
- Removing `mlflow` from `pyproject.toml` (still required for serving)
- Adding `user_id` tracking (no authenticated user context available in default service-principal mode)

## Decisions

### Decision 1: Per-request `CallbackHandler` vs. global singleton

**Chosen:** Instantiate `CallbackHandler` once at module level as a singleton, pass it via `config={"callbacks": [...]}` on each `astream()` call.

**Why:** Langfuse's `CallbackHandler` is stateless between requests — it flushes each trace independently. A singleton avoids re-instantiation overhead on every request while `propagate_attributes` provides per-request context (session_id, tags). An alternative of creating a new handler per request is also valid but unnecessary.

**Alternative considered:** Global `autolog`-style instrumentation. Langfuse does not offer an equivalent to `mlflow.langchain.autolog()` — the callback injection pattern is the standard approach.

---

### Decision 2: Session context via `propagate_attributes` context manager

**Chosen:** Wrap the `agent.astream()` call in `with propagate_attributes(session_id=session_id):`.

**Why:** This is Langfuse's documented approach for attaching session/user context to LangGraph traces without modifying the handler state directly. It uses Python context variables (contextvars), making it safe for async/concurrent requests.

**Alternative considered:** Setting `langfuse_handler.session_id` directly. This mutates shared state and is not safe for concurrent async requests.

---

### Decision 3: Keep dual observability (Langfuse + Databricks Agent Monitoring)

**Chosen:** Accept that Databricks Agent Monitoring will continue to collect telemetry from `ResponsesAgent` types independently of Langfuse.

**Why:** Removing Databricks-side monitoring would require modifying or replacing `AgentServer`, which is out of scope. The two streams are complementary — Langfuse for developer debugging, Databricks for production monitoring dashboards.

---

### Decision 4: `LANGFUSE_HOST` optional, defaults to Langfuse Cloud

**Chosen:** Document `LANGFUSE_HOST` as optional in `.env.example`. When absent, Langfuse SDK defaults to `https://cloud.langfuse.com`.

**Why:** Gives the team the option to self-host without requiring it upfront. Enterprise data sovereignty requirements (relevant for Pertamina) can be addressed by setting `LANGFUSE_HOST` to an internal instance.

## Risks / Trade-offs

- **Two observability streams** — Langfuse traces and Databricks Agent Monitoring telemetry coexist. Engineers need to know which to check for which use case. → Mitigation: document in README which system covers what.
- **`MLFLOW_*` vars remain required** — Removing them breaks `AgentServer` startup. Anyone cleaning up env vars may inadvertently break the server. → Mitigation: add comments in `.env.example` distinguishing serving vars from tracing vars.
- **Langfuse flush on shutdown** — In async contexts, Langfuse buffers traces and flushes on a background thread. If the Databricks App is killed without a graceful shutdown, the last traces may be lost. → Mitigation: call `langfuse_handler.langfuse.flush()` in a shutdown hook if this becomes an issue.
- **No `ConversationSimulator` equivalent** — Deferred evaluation means the quality regression detection gap remains until `evaluate_agent.py` is migrated separately.

## Migration Plan

1. Add `langfuse` to `pyproject.toml` dependencies
2. Update `agent_server/agent.py`: remove autolog, add `CallbackHandler` singleton and `propagate_attributes`
3. Update `agent_server/start_server.py`: remove `setup_mlflow_git_based_version_tracking()`
4. Update `.env.example`: add Langfuse vars with comments
5. Update `databricks.yml`: add Langfuse env vars (reference secrets if self-hosted)
6. Test locally with `uv run start-app` — verify traces appear in Langfuse UI
7. Deploy with `databricks bundle deploy`

**Rollback:** Revert `agent.py` and `start_server.py` changes. Langfuse vars in env have no effect if the callback is not registered — rollback is safe without touching infrastructure.

## Open Questions

- Should `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` be stored as Databricks secrets (vault) rather than plain env vars in `databricks.yml`? Depends on workspace secret management policy.
- Should `user_id` be forwarded to Langfuse when user-authorization mode is enabled (`get_user_workspace_client()`)? Out of scope now but worth revisiting when user-auth is activated.
