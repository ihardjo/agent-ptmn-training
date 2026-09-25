# Evaluation baseline — `databricks-glm-5-3-flash`

Recorded 2026-09-24 against the Langfuse dataset `sdlc-agent-eval-v1`
(27 items), on branch `feat/skills-dev`.

Run `uv run agent-evaluate` to reproduce. The runner reads expectations from
**Langfuse, not from `dataset.py`** — after editing the dataset you must run
`uv run python -m agent_evaluation.dataset --seed` or the run scores against
the old key and the numbers below mean nothing.

## The configuration this measures

| | |
|---|---|
| Model | `databricks-glm-5-3-flash` (now set in `agent_server/config.py`) |
| Skills mounted | all 10 — the whole menu, unfiltered |
| Tools | `execute_sql`, `poll_sql_result` |
| `auditing-data-quality` | v2 |
| Run name | `glm-5-3-flash-baseline-final` |

### The agent has since changed — a run today is not comparable

The numbers below measure the configuration in that table, which is no longer
the one `init_agent()` builds. Re-running `agent-evaluate` now answers a
different question, and a delta against this file is not a regression. What
moved, and why each one can shift a score:

| Change | Reaches the scores through |
|---|---|
| Skills: all 10 → the 3 in `SELECTED_SKILLS` | `skill_selection` — the distractors that made a mis-selection possible are no longer mounted, and `q-target-trend`'s known failure needs `auditing-data-quality` present to reproduce |
| SQL endpoint moved to `/api/2.0/mcp/sql`, which also offers `execute_sql_read_only` | `tool_efficiency`, `sql_identifiers_escaped` |
| `hide_unusable_tools` removed | `tool_efficiency` — `execute` and `task` are offered again, and neither can work here |
| Wiki split into a `raw/` landing tree and an OKF `notes/` wiki | `wiki_was_read` — the policy documents moved to `/wiki/notes/` |
| Ticket table is now `workshop_ai_platform.default.sdlc_tickets` on a different workspace | any numeric evaluator, if the rows ever diverge (they were verified identical at the move) |

`flag_pii` and the provenance middleware are not on this list: scored runs
already disabled the first and the second is gone, so neither changed what a
run measures.

To re-baseline, record a new file rather than editing this one — the
comparison between them is the finding.

## Scores

| Evaluator | Score | Denominator |
|---|---|---|
| `caveat_present` | 100% | 7 |
| `correct_duration_used` | 100% | 1 |
| `declined_correctly` | 100% | 23 |
| `no_mutation` | 100% | 1 |
| `no_pii_leak` | 100% | 11 |
| `no_pii_persisted` | 100% | 2 |
| `numeric_accuracy` | **94%** | 17 |
| `skill_selection` | **98%** | 27 |
| `sql_identifiers_escaped` | 100% | 2 |
| `wiki_was_read` | 100% | 3 |

`tool_efficiency`: 4.19 — 113 statements over 27 items, 1133s, 42.0s per item.

Denominators differ per evaluator because each applies only to the items that
can exercise it. `no_pii_persisted` in particular counts only the items where
the agent chose to write a note, so it varies run to run and a low denominator
is not a gap in coverage.

## Do not read this as 100%

The single run above is one draw. Across the four runs taken against this
answer key, the same configuration produced:

| Evaluator | Range over 4 runs |
|---|---|
| `caveat_present` | 86 – 100% |
| `declined_correctly` | 91 – 100% |
| `numeric_accuracy` | 94 – 100% |
| `skill_selection` | 96 – 98% |
| all others | 100% |

Over the full set of twelve runs in this session, `caveat_present` landed on
86% six times and 100% six times. The item that fails is not always the same
one, and the answer key and prompt did not change between several of those
runs. **At least one evaluator here behaves like a coin flip**, so no
configuration reaches a stable 100% and a run that does has not proven
anything. Treat a single clean run as within noise; treat a drop of two or
more evaluators at once as signal worth investigating.

## Known failures

**`q-target-trend` — `skill_selection`, stable, unexplained.** The agent reads
`auditing-data-quality` alongside the correct `computing-target-adherence`.
This failed across three materially different descriptions for that skill —
a wide trigger, a wide trigger with an explicit *"not for target or SLA
adherence"* disclaimer, and a narrow trigger naming neither durations nor
adherence. **The description is not the cause**, and the cause is not yet
known. Cost is one wasted skill read, never a wrong answer, which is the
designed cost of a mis-selection.

Incidental finding worth keeping: the disclaimer made no difference. A
negative clause is a poor way to suppress a skill, because selection matches
on what a description *talks about* rather than reasoning about its polarity —
naming a topic in order to disclaim it may add it to the matchable surface.
This is a plausible reading, not a measured result.

**`q-assignee-ranked-table` — `numeric_accuracy`, intermittent.** Passes and
fails across runs with no change to the prompt or the key. Not investigated,
because it cannot be distinguished from noise at this sample size.

## Instrument defects corrected before this baseline

**Roughly half the improvement over earlier runs came from fixing the
evaluation, not the agent.** Recorded so nobody reads the earlier numbers as a
worse agent:

- `dataset.py` items carried no `expected_skills`, and `to_langfuse`'s
  allow-list dropped the field. Every item resolved to an empty expectation,
  so reading *nothing* scored 1.0 and reading the *right* skill scored 0.5.
- The gap-naming judge prompt read *"names that the data lacks X"* as a noun
  phrase and penalised correct answers.
- Items where the correct behaviour is to answer one half and decline the
  other were scored as whole declines, and flipped verdict depending on which
  way they were declared. Fixed with `partial_decline`.
- The eval runner had no logging configuration, so a run that silently lost
  its SQL tool looked identical to a clean one.
- `ExceptionGroup` was reported as *"(N sub-exceptions)"*, hiding every cause.

Five corrections were made to the answer key itself. That is a lot, and
further loosening should be treated as tuning the test rather than the system.

## Environment noise seen during these runs

Present in the harness, not in the agent; a run showing these is not a
regression:

- `McpError: ResolveMcpServiceRoute failed: CANCELLED` — kills an item
  outright and shows up as a `numeric_accuracy` failure with no figure.
- HTTP 429 from the model endpoint (retried with backoff).
- `<tool_call>` occasionally leaking into the answer as raw text.

## Earlier baselines

`openspec/changes/add-skill-menu/measurement.md` and
`openspec/changes/add-volume-backed-wiki/baseline.md` hold per-change figures
taken against `databricks-qwen35-122b-a10b`. They answer "what did that change
buy" and are not comparable with this file. Leave their numbers alone.
