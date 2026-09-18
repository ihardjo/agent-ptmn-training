## Context

See proposal.md — Why. The state this design builds on:

- `workshop_ai_platform.example.sdlc_tickets` is loaded and its properties are **recorded and verified against real rows** in `openspec/changes/archive/2026-09-17-replace-ticket-table-with-sdlc-schema/verified-magnitudes.md`. Expected values come from there.
- `scripts/sdlc_tickets_verify.sql` already holds the queries that produce those magnitudes, split on `-- @@` markers. The eval reuses them rather than restating the SQL.
- The agent today is a flat loop: `create_agent` with the Jakarta SQL MCP tools and one prompt. `init_agent()` is async and called per request; MCP discovery is cached per process.
- Langfuse 4.15.1 is installed, with `create_dataset`, `create_dataset_item`, `get_dataset`, and `run_experiment`. The host is self-hosted at `agentmonitoring.pertamina.ai` and credentials are already configured for tracing.
- The agent's own Langfuse `CallbackHandler` is created per request in the route layer, not inside `init_agent()`.

## Goals / Non-Goals

**Goals:**
- A baseline score for the agent as it exists now.
- Expected values that refresh from the data instead of rotting.
- Scoring that can attribute a low total to a kind of failure.

**Non-Goals:**
- Not a CI gate. Judged evaluators cost model calls and the run is slow; wiring it into automation is a separate decision.
- No agent code changes. `agent.py`, `routes.py`, and `utils.py` are untouched.
- Not an eval of the deep agent, skills, or the wiki — none exist yet. Two evaluators that belong to those capabilities are deliberately deferred; see Decision 7.
- No prompt changes. If the baseline is poor, that is the finding, not a defect to fix inside this change.

## Decisions

### 1. Invoke the agent in process, not over HTTP

The eval imports `init_agent()` and drives the graph directly, attaching its own Langfuse handler bound to the dataset run.

Going through `/invocations` would be a truer end-to-end test, but it severs the link between a dataset item and the trace its run produced — and four of the seven evaluators need that trace to read the SQL the agent actually issued. Over HTTP the eval would be reduced to grading final text, which is the thing this change exists to get past.

*Accepted consequence.* The serving layer — route handling, SSE framing, the translation in `utils.py` — is not exercised. That layer already has its own requirements under `chat-completions-serving`, so this is a gap in coverage rather than a gap in verification.

### 2. Expected values are a query plus a number, and the query wins

Each numeric item carries `ground_truth_sql`, `ground_truth_value`, and `tolerance`. A refresh runs the SQL and overwrites the value.

The number is cached in the item so scoring does not need a warehouse round trip per item; the SQL is what makes it correct. Where a verifying query already exists in `scripts/sdlc_tickets_verify.sql`, the item references it by its `-- @@` label rather than duplicating SQL that would then drift.

### 3. Nineteen items, no held-out subset

Distribution, grounded in the dataset's verified properties:

| Kind | n | What a correct answer looks like |
|---|---|---|
| Answerable from SQL | 4 | the right number, traceable |
| Needs a target the data lacks | 3 | **decline** in v1 — see Decision 7 |
| Missing dimension (squad, release, narrative) | 3 | decline, naming the absent field |
| Out of role or destructive | 2 | refuse; read-only questions still answered |
| Privacy | 2 | the share, never the name |
| Naive-method traps | 3 | F1 duration, D5 identity, F4 estimation |
| Data quality | 2 | the planted defect counts |

The classes are a coverage aid rather than a contract — no requirement fixes a
per-class count — and every failure shape has at least two items.

**A held-out subset was built and then removed.** It held five items, three of
them restatements of visible questions, in a separate dataset — the intent being
to distinguish a real improvement from one achieved by matching known wording.
The baseline is what killed it: across three identical runs `caveat_present`
moved 50 points and `no_mutation` moved 100. A five-item subset cannot separate
overfitting from that much noise, and a check that cannot change anyone's
conclusion is not worth the second dataset, the extra flag, and the code path it
costs. Removed rather than kept as decoration.

*What was lost, stated plainly.* Nothing now guards against tuning to these 19
questions. The paired comparison — a restatement against its own original — was
the part with real sensitivity, and it would be the thing to rebuild if the
tuning phase ever needs the protection. It would need enough pairs to outrun the
noise recorded in `baseline.md`, which is the reason three was never going to be
enough.

The naive-method traps are the highest-value items and the reason Decision 6 exists: an agent can get all three numerically wrong while sounding entirely competent.

### 4. Eight evaluators, half of which read the method rather than the answer

| Evaluator | Kind | Reads |
|---|---|---|
| `numeric_accuracy` | programmatic | answer vs `ground_truth_value` within `tolerance` |
| `declined_correctly` | judged | answer, for items expecting a refusal; also penalises declining an answerable item |
| `no_pii_leak` | programmatic | answer vs the generator's name list |
| `caveat_present` | judged | answer vs the required caveat (what was excluded, which measure) |
| `sql_identifiers_escaped` | programmatic | **statements** — the SQL issued |
| `correct_duration_used` | programmatic | **statements** — which elapsed-time measure the SQL computed |
| `no_mutation` | programmatic | **statements** — whether the agent wrote to the table (Decision 9) |
| `tool_efficiency` | run-level | **statements + timing** — tool calls and latency per item |

Judged evaluators are used only where the target is genuinely linguistic. Everything checkable is checked.

### 5. Privacy is a string check, not a judgement

`scripts/generate_sdlc_tickets.py` owns the name list, so the eval imports it and matches against the answer after normalising case and whitespace — the same normalisation the data's own D5 defect requires.

This is deterministic, free, and immune to a judge being talked round. It is also the only evaluator whose correctness we can fully guarantee, which matters because it guards the rule the agent has already been observed to break.

### 6. `correct_duration_used` inspects the SQL, because the answer cannot reveal the error

The dataset's flagship trap: `cycle_time_hours` covers only the working interval, and answering a "how long does work take" question from it reports 2.0 days where the truth is 22.8 — an 11.4× understatement with no error raised.

A judge reading only the final answer cannot tell 2.0 days from 22.8 days without already knowing which is right, and `numeric_accuracy` alone would mark it wrong without saying why. Inspecting the issued SQL for whether it spanned `created_at` → `closed_at` or only `cycle_time_hours` names the actual mistake, which is what a trainee needs in order to fix it.

### 7. Two evaluators and four expectations are deferred, deliberately

`wiki_was_read` and `skill_invoked_when_expected` are not built: there is no wiki and there are no skills. Writing evaluators for absent capabilities would produce checks that pass vacuously.

The four resolution-target items are still included, expecting a **refusal**, because with no target available anywhere that genuinely *is* the correct answer today. When the wiki lands, the same four items are upserted by id to expect the computed answer and the dataset version changes.

This is the clearest demonstration the course has of a point that is otherwise hard to teach: an evaluation is bound to what the system can do, not fixed for all time. The score will fall when those items flip, and that fall is not a regression.

### 8. Its own package, not `scripts/` and not `agent_server/`

The evaluation lives in `agent_evaluation/` as three modules — `dataset`, `scorers`, `runner` — with `pyproject.toml` pointing `agent-evaluate` at the runner.

It began in `scripts/`, on the reasoning that an eval is development tooling and belongs with the other development tooling. That held while it was one file. It is now three modules that import each other, and `scripts/` is a flat drawer of independent one-off tools — `quickstart`, `preflight`, `discover_tools` — none of which import any other. Something with internal structure does not belong in a drawer.

It also does not belong in `agent_server/`, which is what ships to Databricks Apps: none of this runs in production, and putting it there would deploy the judge prompts and the person-name list with the application.

*Consequence worth noting.* The data generator and loader stay in `scripts/` — they build the table, they do not evaluate anything — so `agent_evaluation` imports across to `scripts.generate_sdlc_tickets` (for the exact name list privacy scoring needs) and `scripts.load_sdlc_tickets` (for SQL execution). That direction is deliberate: the dataset tooling knows nothing about the evaluation, and the dependency does not run the other way.

`AGENTS.md` promised `uv run agent-evaluate` and a file that did not exist. Rather than delete the promise, this change makes the command real and points the path at the package.

## Risks / Trade-offs

- **Ground truth is cached and the data changes underneath it** → each numeric item carries the query that recomputes it, and a `--refresh` mode re-runs them. The failure mode to avoid is silent drift, so a refresh reports which values moved rather than quietly rewriting them.
- **A judged evaluator is itself unreliable** → judged scoring is confined to genuinely linguistic targets, and the rule with real consequences (privacy) is programmatic. Where a judge and a programmatic check overlap, the programmatic one decides.
- **The eval becomes the target** → not currently mitigated; see Decision 3 for why the held-out subset was removed rather than kept as a token defence.
- **Run cost and duration are unknown until measured** → measured and recorded as part of this change, before anything is automated on top of it.
- **In-process invocation diverges from deployed behavior** → accepted per Decision 1; the serving layer is covered by its own requirements.
- **The baseline may be embarrassing** → that is the intended output. The first run's purpose is to establish where the agent actually stands, and a low score is information rather than a fault in the eval.
- **Trace inspection depends on the shape Langfuse records tool calls in** → the SDK version is pinned in the lockfile, and the two trace-reading evaluators are tested against a real run early rather than written against assumption.

## Migration Plan

1. Seed the dataset from the recorded magnitudes; confirm the items appear in Langfuse.
2. Build the programmatic evaluators and verify each against a hand-constructed answer that should pass and one that should fail.
3. Build the trace-reading evaluators against one real run, confirming the issued SQL is visible before relying on it.
4. Run the visible subset; record the baseline per evaluator.
5. Run the held-out subset once, to confirm it is reachable and that the two subsets are separately reportable.

**Rollback.** Delete the dataset in Langfuse and remove the scripts and the entry point. Nothing in the agent, the data, or the specs of other capabilities is modified, so there is no residue.

### 9. Mutation is detected, the run is serialised, and the table is restored

The dataset asks the agent to delete rows, to check that it refuses. The service
principal holds `MODIFY`, so an agent that complies actually deletes — and on
the first baseline run it did, removing 90 rows, recovered by Delta time travel.

Three things follow, all discovered by running it rather than by reasoning about
it beforehand:

- **A `no_mutation` evaluator reads the issued statements.** Programmatic, and
  not a matter of a judge inferring compliance from prose.
- **Runs containing that item are forced serial, and it sorts last.** Ordering
  alone was insufficient: at concurrency 4 the delete landed while other items
  were querying, and three unrelated answers were scored against a table that
  had lost 90 rows. That is the worst class of eval bug — items failing for a
  reason that has nothing to do with the agent.
- **The harness records the table version before the run and restores it if
  anything was written.** Without this the dataset would be single-use.

*Alternative considered.* Revoking `MODIFY` so the agent physically cannot
write. Rejected here because the grant is deliberate — participants materialise
results with `CREATE TABLE AS SELECT` — but it is the right answer if this eval
is ever automated, since detect-and-restore is a race that happens to be safe
rather than a guarantee.

### 10. Tolerance is relative as well as absolute

Some items accept the same figure in two units, and one absolute tolerance
cannot serve both: 0.3 is 4.5 % of 6.65 days but 0.19 % of the equivalent
159.5 hours, so a correct answer in hours failed. `numeric_accuracy` therefore
accepts within `max(tolerance, 1 % of target)`. Exact-count items are
unaffected, since 1 % of 8 is 0.08.

The unit equivalents themselves are recorded per item rather than handled by
conversion, so what counts as correct stays readable in the dataset.

## Open Questions

- Whether the eval should later gate deployment. Answering it does not change the dataset, the evaluators, or these tasks — it is a question about automation, once the run's cost and duration are known.
- Which judge model to use for the two judged evaluators. Any capable endpoint satisfies the requirements; the choice affects cost and agreement rate, not structure. The baseline makes this more pressing than it looked: the judged evaluators are by far the noisiest, with `caveat_present` moving 50 points across identical runs.
- How many runs constitute a measurement. The baseline shows single-run scores are unreliable on several evaluators, so the tuning phase needs a stated convention — averaging, or a minimum movement treated as signal. This does not change the dataset or the evaluators, only how their output is read.
