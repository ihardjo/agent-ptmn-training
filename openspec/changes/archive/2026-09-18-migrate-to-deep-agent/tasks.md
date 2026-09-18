## 1. Dependency and compatibility

- [x] 1.1 Add `deepagents` to `pyproject.toml` and resolve the lockfile; verify `uv sync` succeeds without downgrading the pinned `langchain` or `langgraph` versions
- [x] 1.2 Confirm the existing `databricks_langchain` streaming path is unaffected — verify a streamed request still yields reasoning blocks and text as separate parts rather than a JSON blob, per the handling in `agent_server/utils.py`
- [x] 1.3 If 1.1 or 1.2 fails, stop and record the conflict rather than bumping pinned versions as part of this change

## 2. Tiered filesystem

- [x] 2.1 Create a `skills/` directory at the repository root containing one trivial skill with a definition file, sufficient to prove the load path
- [x] 2.2 Build the composite backend per design Decision 2 — state as the default, a read-only repository mount at `/skills/` — and verify a write to an unprefixed path is readable within the request and gone afterward
- [x] 2.3 Verify the prefix selects the tier — list `/skills/` and confirm the repository skill appears with its prefix preserved, and that the same listing at `/` does not show it
- [x] 2.4 Verify the skills tier refuses writes — `write_file` and `delete` both return `permission denied for write ... (matches deny rule(s): /skills/**)` and the file is unchanged; `edit_file` shares the same `write` operation class as those two and is covered by the same rule, though the model declined to attempt it so that path was not observed directly
- [x] 2.5 Verify the read-only mount behaves identically in a local working tree and in a deployed copy — `SKILLS_DIR` derives from `__file__`, so a copied tree resolved, listed, and read its own `skills/` correctly

## 3. Agent loop

- [x] 3.1 Replace `create_agent` with the deep agent construction in `init_agent()`, carrying over the model, the system prompt, and the MCP tool list unchanged; verify the server starts and answers a non-streaming request
- [x] 3.2 Preserve the MCP discovery cache and its non-caching of failures exactly as it is today, and add a comment distinguishing it from skill discovery per design Decision 5; verify discovery happens once across successive requests
- [x] 3.3 Wire skills from the `/skills/` route; verify the discovered skill count is logged at startup and names the skill
- [x] 3.4 Verify progressive disclosure — confirm a request unrelated to any skill reads no skill body, and that a related request reads one, with the read visible in the trace

## 4. Planning and delegation

- [x] 4.1 Verify a multi-step question produces a recorded plan visible in the Langfuse trace, and that plan revisions appear in the order they occurred — 7 `write_todos` calls with status transitions on `qwen35-122b-a10b`; `gpt-oss-120b` produced none, which is why design Decision 9 changes the endpoint
- [x] 4.2 Verify a single-step question is answered without planning turns, so planning is available rather than mandatory
- [x] 4.3 Verify delegation returns only the sub-task result into the calling context, and that the delegation and its result are distinguishable from the caller's own tool calls in the trace
- [x] 4.4 Verify a failing delegated sub-task is returned to the caller as an actionable result and does not terminate the request

## 5. Preserved behavior

- [x] 5.1 Verify `POST /v1/chat/completions` and `POST /invocations` each answer identically to before the migration, streaming and non-streaming, including `data: [DONE]` termination on the chat route
- [x] 5.2 Verify tool calls and their results still appear in the stream before the final answer
- [x] 5.3 Verify `GET /health` still returns `{"status":"ok"}`
- [x] 5.4 Verify tracing — confirm a trace appears in Langfuse for a request, containing the agent's tool calls plus its planning and delegation activity
- [x] 5.5 Verify degradation with the remote MCP server unreachable: the agent starts, serves, logs the failure, and a later request can still succeed because the failure was not cached — required a fix, see design Decision 10; after it, an unreachable host yields 0 tools with the cache still unset, and restoring the host in the same process resolved 3 tools
- [x] 5.6 Verify degradation with `skills/` absent and with a malformed skill directory present: the agent starts and serves in both cases, reporting the problem in the log only
- [x] 5.7 Confirm a long delegated sub-task renders as an opaque tool card in the chat UI while remaining fully legible in the trace, and record this as the accepted consequence in design Decision 6 rather than a defect

## 6. Keep the evaluation honest across the migration

- [x] 6.1 Make statement capture in `agent_evaluation/runner.py` filter on the tool that was called, keeping the SQL MCP tools and discarding planning, delegation, and filesystem reads, per design Decision 7; verify a run in which the agent plans yields a statement list containing only SQL
- [x] 6.2 Verify the mutation guard no longer fires on planning text — construct or observe a plan step beginning with a data-modifying verb and confirm no write is reported and no table restore is triggered
- [x] 6.3 Verify `sql_identifiers_escaped` is unaffected by prose — confirm a plan or skill body mentioning a carried-over custom field without backticks does not score a method failure
- [x] 6.4 Run the full evaluation after the migration and compare per evaluator against the recorded baseline in the archived `add-langfuse-eval-dataset` change; verify `tool_efficiency` counts only SQL so the figure is comparable
- [x] 6.5 Interpret the comparison against the baseline's variance rather than as a single reading, per design Decision 8 — verify any conclusion drawn rests on a movement larger than the run-to-run noise recorded there, and record the post-migration scores in this change directory
