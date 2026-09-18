## Why

The agent is a flat ReAct loop: `create_agent` with one tool list and one system prompt. It answers a question in a single undifferentiated context, which is adequate for a one-table lookup and inadequate for everything the training course is meant to teach — planning a multi-step investigation, delegating a bounded sub-task without polluting the main context, and reading procedures on demand rather than carrying every instruction in every turn.

It is also the blocking dependency for three later changes. Repo-held skills, the Volume-backed wiki, and the tool-and-skill wiring exercise all need a filesystem abstraction and a middleware stack that a flat loop does not have.

## What Changes

- Replace `create_agent` with a deep agent loop providing a **planning tool**, **subagent delegation**, and **filesystem middleware**.
- Introduce a **composite filesystem tiered by path prefix**, where the prefix states the lifetime and the provenance of what it holds:
  - `/` — turn-scoped scratch, discarded with the thread
  - `/skills/` — read-only, mounted from the repository, changes only by merge
- Load **skills from the repository** with progressive disclosure: descriptions in the prompt always, bodies read on demand.
- Make `/skills/` **read-only to the agent**, so no instruction can enter the prompt without passing human review in a diff.
- Add the `deepagents` dependency.
- **Isolate statement capture in the evaluation harness.** It currently treats every string argument of every tool call as a SQL statement, which was true while SQL was the only tool. A deep agent's plans, delegated sub-tasks, and skill reads would be captured the same way — inflating the effort metric past comparison with the recorded baseline, failing escaping checks on prose, and tripping the mutation guard on a plan step that merely starts with "Delete", which would restore the table for no reason.
- Preserve existing behavior unchanged: both routes, streaming and non-streaming, tool activity in the stream, Langfuse tracing, per-process MCP tool caching, and degradation to the remaining tools when the remote MCP server is unreachable.
- **BREAKING (internal)**: `init_agent()` returns a deep agent rather than the result of `create_agent`. No route or API contract changes.

The `/wiki/` tier — durable, agent-written knowledge on a Unity Catalog Volume — is deliberately **not** in this change. It arrives in `add-volume-backed-wiki`, which depends on the abstraction this change establishes.

## Capabilities

### New Capabilities
- `deep-agent-loop`: The agent's planning and delegation behavior, the tiered filesystem it reads and writes through, and how repository-held skills are discovered, disclosed, and protected from modification.

### Modified Capabilities
- `agent-evaluation`: The requirement *The method is scored, not only the answer* assumes every tool call the agent issues is a statement against the data. Once the agent also plans, delegates, and reads its own skills, that assumption is false — so the requirement changes to distinguish statements issued against the data from other tool activity, and to state that planning text resembling a data-modifying statement is not treated as a write.

`chat-completions-serving` is unaffected: it already requires that tool calls and their results appear in the streaming response, and a deep agent's planning and delegation surface as tool calls, so that contract is met without amendment. `cross-workspace-sql` and `langfuse-tracing` are likewise unaffected — the MCP tool set and the per-request callback handler are carried over as they are.

## Impact

- **`agent_server/agent.py`** — the agent construction is replaced. The MCP tool discovery cache and its failure handling are kept.
- **`pyproject.toml`** — adds `deepagents`. Compatibility with the pinned `langchain` / `langgraph` versions must be verified rather than assumed.
- **`agent_server/utils.py`** — unchanged, but see design.md: planning and delegation will render as generic tool cards in the chat UI, so the plan is legible in Langfuse and flat in the UI.
- **New directory `skills/`** — created empty, or with a single trivial skill to prove the load path. The menu of skills for the wiring exercise is a later change.
- **`agent_evaluation/runner.py`** — statement capture becomes tool-aware. Without this the first post-migration evaluation run mis-scores and may restore the table spuriously.
- **The recorded baseline** in the archived `add-langfuse-eval-dataset` change is the before-measurement for this migration. Note its variance table before drawing conclusions: across three identical runs `caveat_present` moved 50 points and `no_mutation` moved 100, so only large movements on the stable evaluators mean anything.
- **Downstream** — `add-volume-backed-wiki` and the wiring-exercise change both depend on this.
