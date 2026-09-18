## Why

Nothing in this repository can answer the question "is the agent better than it was?" There is no evaluation harness — `AGENTS.md` advertises `uv run agent-evaluate` and `agent_server/evaluate_agent.py`, and neither exists — so every change to a tool, a prompt, or a model endpoint is currently judged by trying one question and forming an impression.

That gap is about to matter twice over. The training course's second phase asks trainees to tune the agent until a score rises, which is impossible without a score. And `sdlc_tickets` now has *recorded, verified* properties, so expected answers can be **derived from the data** rather than guessed — the one condition under which an evaluation set is worth building at all.

It also closes a loop already visible in this repository: the agent named an individual when its instructions forbade it, and that was caught by one person asking one question and reading the answer closely. A second instance would not have been caught.

## What Changes

- Create a Langfuse dataset **`sdlc-agent-eval-v1`** with **19 items** spanning questions that are answerable, questions the data cannot answer, out-of-role requests, privacy constraints, and methods that produce a plausible wrong answer.
- Each item is `input` plus `expected_output`. Signal comes from the **evaluators**, not from item metadata.
- Store a **`ground_truth_sql`** alongside each expected value, so regenerating the table refreshes the eval instead of rotting it. Items carry **stable ids** so a refresh upserts rather than duplicates.
- Add **8 evaluators**, evenly split between scoring the answer and scoring the method:
  - `numeric_accuracy`, `declined_correctly`, `no_pii_leak`, `caveat_present` — score the answer
  - `sql_identifiers_escaped`, `correct_duration_used`, `no_mutation`, `tool_efficiency` — score the method
- `no_pii_leak` is **programmatic, not judged**: the generator owns the name list, so leakage is an exact check.
- Detect and undo mutation: the dataset asks the agent to delete rows in order to check that it refuses, and the service principal can carry that out — so the harness scores writes programmatically, serialises runs containing that item, and restores the table if anything was written.
- Add an `agent-evaluate` entry point, making `AGENTS.md`'s existing claim true instead of removing it.
- Invoke the agent **in process** rather than over HTTP, so each dataset item's run links to its own Langfuse trace and the method-scoring evaluators have something to read.
- Version the expectations: in v1 the four resolution-target questions expect the agent to **decline**, because no target exists anywhere yet. A later change flips those same items to expect a computed answer once the wiki supplies the target.

## Capabilities

### New Capabilities
- `agent-evaluation`: How the agent's behavior is measured — a versioned dataset whose expected values derive from the data, scoring that covers method as well as answer, and the rule that expectations change when the system's capability changes.

### Modified Capabilities

None. `langfuse-tracing` already requires that every invocation produces a trace containing tool calls with their inputs and outputs, which is exactly what the method-scoring evaluators read; this change consumes that contract without altering it. `cross-workspace-sql` and `sdlc-ticket-dataset` are likewise only read from.

## Impact

- **New `agent_evaluation/` package** — `dataset`, `scorers`, `runner`; **`pyproject.toml`** gains the `agent-evaluate` entry point.
- **`AGENTS.md`** — its reference to `agent_server/evaluate_agent.py` is corrected to the real path.
- **Langfuse project** at `agentmonitoring.pertamina.ai` — one new dataset and one run per evaluation. Uses the credentials already configured for tracing; no new secret.
- **Judged evaluators consume model calls**, so a full run has a cost and a duration worth knowing before it is wired into anything automatic.
- **Runs against the agent as it is today** — the flat loop with SQL tools. It does not require `migrate-to-deep-agent`, the wiki, or the prompt-slot restructure. Two of those depend on *it*: `restructure-system-prompt-slots` needs a baseline to prove it changed nothing.
- **Establishes the baseline score** the course's first phase starts from.
