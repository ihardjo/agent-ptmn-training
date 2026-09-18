## Context

See proposal.md — Why. The current state that constrains the approach:

- `agent_server/agent.py` builds the agent with `create_agent(tools=..., model=ChatDatabricks(...), system_prompt=...)`. `init_agent()` is called **per request** by both routes; the expensive part — remote MCP tool discovery — is cached in a module global with a lock, and a discovery failure is deliberately *not* cached so an unreachable server degrades one run rather than the process.
- `agent_server/utils.py` translates LangGraph output into two wire formats by hand. It recognises text, reasoning blocks, tool calls, and tool results. It has no concept of a plan or a subagent.
- The repository is on `langchain` 1.x with `langgraph >= 1.1`, so the middleware architecture `deepagents` builds on is already present.
- An evaluation capability now exists that did not when this change was first written: `agent_evaluation/` scores 19 items against the agent, four of its eight evaluators read the statements the agent issued, and a baseline is recorded in the archived `add-langfuse-eval-dataset` change. That harness assumes every tool call is a SQL statement.
- Databricks Apps deploy the repository to local disk. There is no FUSE mount for Unity Catalog Volumes, but the application's own source files are ordinary local files.

## Goals / Non-Goals

**Goals:**
- Planning, delegation, and a filesystem abstraction, with the existing serving contract untouched.
- A tier layout where the path prefix alone tells you a file's lifetime and who wrote it.
- Skills that cannot be introduced without review.

**Non-Goals:**
- No `/wiki/` tier and no Unity Catalog Volume access. That is `add-volume-backed-wiki`.
- No skill menu. This change proves the load path with at most one trivial skill; the menu with its distractors is the wiring-exercise change.
- No change to `utils.py`. Improving how plans and delegations render in the chat UI is deferred; see the risk below.
- No change to the *judge* model used by the evaluation. It stays on `gpt-oss-120b`, which now differs from the agent's model — an improvement, since the judge no longer grades output from the model that produced it.

## Decisions

### 1. `deepagents` rather than hand-building the middleware

Planning, delegation, filesystem tools, and progressive skill disclosure are all things `deepagents` provides on the `langchain` middleware the repository already depends on. Hand-rolling them would mean writing and maintaining four mechanisms to get a training exercise off the ground.

*Alternative considered.* Extending the existing graph with a todo tool and a nested `create_agent` call. Rejected: it reproduces two of the four mechanisms badly and leaves the filesystem abstraction — the part three later changes depend on — still to invent.

**Compatibility is verified, not assumed.** The dependency must resolve against the pinned `langchain` and `langgraph` versions, and the existing `databricks_langchain` integration must continue to stream reasoning blocks as `utils.py` expects. This is the first task in the list for that reason.

### 2. Tiers keyed on path prefix, with the default as scratch

```
CompositeBackend(
    default = StateBackend(),          #  /          turn scratch, dies with the thread
    routes  = {
        "/skills/": FilesystemBackend( #  /skills/   read-only, from the repository
            root_dir = <repo>/skills,
            virtual_mode = True),
    },
)
skills = ["/skills/"]
```

The default is state, not local disk. An agent that writes scratch files to a container's ephemeral filesystem has produced something that looks durable and is not; state makes the lifetime honest, and the tier prefix makes it visible.

`virtual_mode=True` is the documented setting for mounting a real directory at a virtual path beneath a composite backend. The general guidance to avoid a local-filesystem backend in production is about agent-*writable* local disk; a read-only mount of the deployed source is not that case.

`skills` paths resolve relative to the backend root, which is why the skills directory needs a route of its own rather than being reachable from the state default — the default holds nothing.

### 3. Skills in the repository, not on a Volume

Skills are human-authored configuration, so they belong where human-authored things are reviewed. A skill arriving as a pull request has a diff, a history, and an author; a skill arriving on a Volume has none of those, and it also means arbitrary text can reach the system prompt from a location the agent itself can write to.

This yields a provenance rule worth stating plainly, because it is the question people get wrong about agent memory: **if it is in the repository a person wrote it; if it is on the Volume the agent did.**

*Alternative considered.* Skills on the Volume, edited live without redeploying. Rejected on review and injection grounds. The iteration speed argument that favoured it does not survive contact with how the course actually runs — trainees work locally against `uv run start-app`, where a repository file edit plus a restart is faster than a Volume round trip anyway.

### 4. Read-only is enforced by the tier, not by instruction

The skills tier is mounted read-only. Telling the agent not to write to its own instructions is not a control; a backend that refuses the write is. This also means the guarantee holds against a prompt-injected instruction, not merely against an agent's good behavior.

### 5. Preserve the caching asymmetry deliberately, and document it

MCP tool discovery stays cached per process, for the reason already recorded in the code: it is a cross-region round trip in front of every turn. Skill discovery reads local files, so its cost is not comparable and it does not need the same treatment.

This is worth an explicit comment in the code rather than silence, because the two look like the same problem and are not — one is a network call to another region, the other is a local read.

### 6. The plan is legible in the trace and flat in the UI

`utils.py` maps tool calls and results, so a plan write and a delegation will both arrive as tool cards: the plan renders as a call with a list argument, and a subagent's work renders as one opaque call that may take a long time. Nothing breaks, but the UI stops narrating at exactly the point the agent becomes interesting.

Accepted for now. The trace carries the full structure, and the course already treats reading traces as the first skill rather than an afterthought. Improving the rendering is its own change with its own testable behavior, and bundling it here would put a streaming-protocol rewrite inside an agent-loop migration.

### 7. Statement capture is keyed on the tool, not on the argument's type

`agent_evaluation/runner.py` collects every string argument of every tool call into a list it calls `statements`. That was sound while the only tools were SQL. It stops being sound here, in three specific ways:

- `_is_mutation()` matches a statement beginning `insert|update|delete|merge|drop|truncate|alter|create|restore`. A plan step reading *"Delete the stale draft"* or a delegated sub-task beginning *"Create a summary…"* matches — and the harness responds by **restoring the evaluation table**, which is a destructive corrective action taken on the strength of a false positive.
- `tool_efficiency` reports statements per item. The baseline records 1.63. Counting plan writes and delegations would raise that for reasons unrelated to querying, destroying the comparison the metric exists for.
- `sql_identifiers_escaped` searches statements for a column name. A plan or skill body mentioning `Custom Field (Root Cause)` in prose, correctly unbackticked because it is prose, would be scored a method failure.

So capture filters on **which tool was called**, keeping the SQL MCP tools and discarding planning, delegation, and filesystem reads. Filtering on the argument's shape was considered and rejected: SQL is just text, and any heuristic that tries to recognise it will both admit prose that looks like SQL and reject SQL that does not look like it.

*Why this belongs in this change rather than its own.* Nothing is wrong with the harness today. It becomes wrong at the moment the agent gains tools that are not queries, which is exactly what this change does. Landing the migration without it means the first evaluation run afterwards produces numbers that are wrong in a way that looks like an agent regression.

### 8. The baseline is the before-measurement, read with its variance

The archived baseline is what this migration is measured against. Two cautions carried forward from it:

- Only large movements on the stable evaluators are signal. `caveat_present` and `no_mutation` each moved by 50 points or more across identical runs with no change to the agent.
- `tool_efficiency` is only comparable once Decision 7 lands. Before that, the post-migration number counts a different set of things.

The expectation is not that the score rises. A deep agent adds planning turns and latency to every request, including those that never needed them, and the specs already require that single-step questions are not forced through planning — which is a thing to verify rather than assume.

### 9. The model endpoint changes, because the capability depends on it

This began as a non-goal: model choice was to be a separate question. Implementation made that untenable. `databricks-gpt-oss-120b` never called `write_todos` on a genuinely multi-step question, even when explicitly instructed to plan the steps first — so the migration would have shipped the cost of a deep loop (extra turns, extra latency, a larger tool surface) without the planning it exists to provide.

Each open-weight endpoint served in the workspace was run against the identical configuration — same prompt, same 13 tools, same backend and permissions — with only the endpoint varied:

| Endpoint | Plans? | Latency | Note |
|---|---|---|---|
| `qwen35-122b-a10b` | yes, 3 of 4 runs | 30–44 s | **chosen** |
| `glm-5-3` | yes | 36 s | rate-limited (429) on the next two calls |
| `deepseek-v4-pro-0813` | yes | 46 s | |
| `kimi-k3` | yes | 137 s | too slow |
| `gpt-oss-120b` | **no** | 7.8 s | previous endpoint |
| `llama-4-maverick` | no | 16 s | |
| `qwen3-next-80b-a3b` | no | 20 s | |
| `gemma-3-12b` | — | — | tool calling unusable: 400, or empty content with tools bound |

`qwen35-122b-a10b` is chosen on three grounds: it plans most reliably of the candidates, its latency is the lowest among those that plan, and it showed no rate limiting — which `glm-5-3` did immediately, and which would matter with a cohort driving agents concurrently.

*What this costs.* Four to six times the latency per request. Every figure in `post-migration.md` is measured on this endpoint for that reason; comparisons against the `gpt-oss-120b` baseline now carry a model change as well as an architecture change, and cannot attribute a movement to either alone.

*What it does not fix.* Planning remains probabilistic — the chosen endpoint skipped it on one run in four. No endpoint makes it certain, which is why the requirement is about planning being available and used rather than guaranteed per request. Delegation (`task`) was not used by any endpoint on the question tested.

### 10. Remote-tool degradation had to be fixed to work at all

The requirement that an unreachable remote tool server degrades rather than fails was not met before this change, and the fault is older than it. `mcp_tools()` wrapped only `client.get_tools()` in its `try`; `init_mcp_client()` was called *before* it. Constructing a `WorkspaceClient` validates its configuration and raises on a bad or missing host, so a misconfigured remote produced a `ValueError` that propagated out of `init_agent()` and surfaced as a 500 from the route — precisely the behaviour the graceful-degradation comment in that function claimed to prevent.

Client construction now sits inside the `try`. Verified by pointing the host at a non-existent workspace: the call returns no tools, the module cache is left unset, the agent still constructs, and restoring the host in the same process resolves the tools — which is the part that matters, since caching the failure would have degraded the whole process rather than one run.

*Operational note.* An unroutable host degrades only after the SDK's network timeout, so the first request after a remote outage is slow rather than immediately toolless. Fine here; worth knowing before putting a latency budget in front of it.

## Risks / Trade-offs

- **`deepagents` does not resolve cleanly against the pinned `langchain` / `langgraph` versions** → verified first, before any other work. If it conflicts, the change stops at that task rather than dragging a dependency bump through the rest of the plan.
- **Reasoning-block streaming regresses** → `utils.py` handles a Databricks-specific case where reasoning blocks arrive JSON-encoded inside a string. A different middleware stack could change that shape. Verified explicitly by streaming a request and confirming thoughts still render as thoughts rather than as a JSON blob on screen.
- **A long subagent turn looks like a hang in the chat UI** → accepted per Decision 6; visible in Langfuse. Worth telling trainees before they see it, not after.
- **Planning adds turns, and therefore latency and cost, to requests that never needed it** → the specs require that single-step questions are not forced through planning; measured once the evaluation dataset exists, since cost per trace is exactly what it reports.
- **The current model endpoint may not hold a deep loop with progressive disclosure** → out of scope here, but it is the most likely cause of disappointing behavior after this lands. Named so it is not diagnosed as a wiring fault.
- **Read-only mount fails differently across local and deployed runs** → tested in both, because the local path is a working tree and the deployed path is a deployed copy.
- **The mutation guard fires on a plan step and restores the table** → Decision 7; verified by asserting no restore occurs on a run where the agent planned but issued no write.
- **The migration's effect is read off a noisy baseline** → Decision 8; large movements only, and `tool_efficiency` compared only after capture is fixed.

## Migration Plan

1. Add and resolve the dependency; confirm compatibility with the pinned versions.
2. Build the composite backend and the skills route; prove discovery with one trivial skill.
3. Replace the agent construction, carrying over the MCP cache, the failure handling, the model, and the prompt.
4. Verify the serving contract: both routes, streaming and not, tool activity, reasoning rendering, tracing.
5. Verify degradation with the remote server unreachable and with the skills directory absent.
6. Fix statement capture, then run the evaluation and compare against the recorded baseline.

**Rollback.** Revert `agent.py` and the dependency. Nothing outside the agent construction changes, no data is written, and no external resource is created — so rollback is a code revert with no residue.

## Open Questions

- Whether subagents should be given a narrower tool set than the calling agent. Answering it later does not change these specs or this task breakdown; it is a configuration choice once delegation works.
- Whether the plan should be surfaced in the chat UI as a distinct element rather than a tool card. Deferred to its own change per Decision 6.
