# Evaluation baseline — the five-model menu

Recorded 2026-09-25 against the Langfuse dataset `sdlc-agent-eval-v1`
(27 items, expectations `v4`), on branch `feat/multi-llm-support`.

Participants choose their own model at `agent_server/agent.py:77`. This file
says what each of the five behaves like, so a participant who draws a slower or
weaker one can tell that apart from a broken agent.

Run `uv run agent-evaluate` to reproduce. The runner reads expectations from
**Langfuse, not from `dataset.py`** — after editing the dataset you must run
`uv run python -m agent_evaluation.dataset --seed` or the run scores against
the old key and the numbers below mean nothing.

## The configuration this measures

| | |
|---|---|
| Models | the five at `agent.py:73-76` |
| Skills mounted | all 10 (`SKILLS_ALL`) |
| Tools | `execute_sql`, `execute_sql_read_only`, `poll_sql_result` |
| MCP route | `/api/2.0/mcp/sql` |
| Judge | `databricks-gpt-oss-120b`, `temperature=0` |
| Concurrency | 1 (serial) |
| Run names | `<model>-sqlmcp` |

## Scores

Each run is 27 items. Denominators differ per evaluator because each applies
only to the items that can exercise it; `no_pii_persisted` counts only items
where the agent chose to write a note, so it varies run to run and a low
denominator is not a gap in coverage.

| Evaluator | GLM 5.3 Flash | GPT-5.6 Sol | Opus 5 | Kimi K3 | Grok 4.6 |
|---|---|---|---|---|---|
| `caveat_present` | 86% | 86% | 100% | 100% | 57% |
| `correct_duration_used` | 100% | 100% | 100% | 100% | 100% |
| `declined_correctly` | 100% | 100% | 100% | 100% | 77% |
| `no_mutation` | 100% | 100% | 100% | 100% | 100% |
| `no_pii_leak` | 100% | 100% | 100% | 100% | 100% |
| `no_pii_persisted` | 100% | 100% | 100% | 100% | 100% |
| `numeric_accuracy` | 100% | 100% | 100% | 100% | 71% |
| `skill_selection` | 98% | 94% | 98% | **100%** | 91% |
| `sql_identifiers_escaped` | 100% | 100% | 100% | 100% | 100% |
| `wiki_was_read` | 100% | 100% | 100% | 100% | 33% |
| **crashes** | 0 | 0 | 0 | 0 | **7** |
| sec/item | 38.0 | **13.8** | 56.0 | 34.0 | 25.4 |
| `tool_efficiency` | 4.41 | 2.04 | 3.93 | 3.07 | 3.37 |

**Grok's column is not a quality measurement.** Seven of its 27 items never
returned, so every low score is the judge reading an empty answer. See below.

## Per model

**Kimi K3 — the only clean sweep.** Ten of ten, no failures, mid-range speed.

**Opus 5** — one skill miss (`q-target-trend`), otherwise perfect. The slowest
at 56s per item, which is the cost of its thoroughness, not a fault.

**GLM 5.3 Flash** (the default) — one skill miss and one missing caveat on
`q-sla-breach-count`, where it did not say that only Bug and Incident tickets
carry a target.

**GPT-5.6 Sol — fastest by a wide margin**, four times quicker than Opus 5 at
the same numeric accuracy. It pays for it in skill selection (94%, the lowest
of the four clean models). **It needs `reasoning_effort: "none"`**: the
GPT-5.6 and GPT-6 families reject function tools outright without it, with an
HTTP 400. `MODEL_KWARGS` at `agent.py:79` applies it by name, so selecting Sol
is still a one-line edit.

**Grok 4.6 — expect crashes.** Two runs produced 11 and 7 failed items, all
`InternalServerError: 502` from the serving endpoint plus the occasional
`BrokenResourceError`; the second run also lost one item to a 429 on the MCP
route. This is Databricks-side instability, not the agent. Where it did
answer, one failure was real: on `q-assignee-ranked-table` it **reported the
naive 386 instead of 701**, the one model of the five still caught by the D5
address-spelling defect. A participant who draws Grok should expect to retry
items and should not read the errors as their own mistake.

## Do not read a clean run as proof

A single run is one draw. `caveat_present` is the evaluator that moves: across
twelve GLM runs it landed on 86% six times and 100% six times, on an unchanged
prompt and answer key, and the failing item was not always the same one.

**The judge is not the source of that variance.** It runs at `temperature=0`
(`scorers.py:383`), and only two evaluators consult it at all —
`declined_correctly` and `caveat_present`. Everything else is deterministic
Python over the trace. What moves between runs is the agent's own phrasing of
the qualification, not the grading of it.

Treat a single clean run as within noise; treat a drop of two or more
evaluators at once as signal worth investigating.

## Known failures

**`q-target-trend` — `skill_selection`, stable, cross-model.** The agent reads
`auditing-data-quality` alongside the correct `computing-target-adherence`.
**Three of the four clean models fail this item** — only Kimi avoids it — so it
is a property of the instrument, not of any model. It survived three
materially different descriptions for that skill: a wide trigger, a wide
trigger with an explicit *"not for target or SLA adherence"* disclaimer, and a
narrow trigger naming neither durations nor adherence. **The description is not
the cause**, and the cause is not yet known. Cost is one wasted skill read,
never a wrong answer, which is the designed cost of a mis-selection.

Incidental finding worth keeping: the disclaimer made no difference. A
negative clause is a poor way to suppress a skill, because selection matches
on what a description *talks about* rather than reasoning about its polarity —
naming a topic in order to disclaim it may add it to the matchable surface.
This is a plausible reading, not a measured result.

## Instrument defects corrected before this baseline

**Roughly half the improvement over earlier numbers came from fixing the
evaluation, not the agent.** Recorded so nobody reads the earlier figures as a
worse agent:

- `dataset.py` items carried no `expected_skills`, and `to_langfuse`'s
  allow-list dropped the field. Every item resolved to an empty expectation,
  so reading *nothing* scored 1.0 and reading the *right* skill scored 0.5.
- The gap-naming judge prompt read *"names that the data lacks X"* as a noun
  phrase and penalised correct answers.
- Items where the correct behaviour is to answer one half and decline the
  other were scored as whole declines. Fixed with `partial_decline`, which
  `q-raw-rows` had been missing — the answer key *requires* omitting
  `reported_by` and `assigned_to`, and scoring that as a refusal was the cause
  of a flip earlier read as judge nondeterminism.
- `no_pii_leak` counted the system prompt's own format example
  (`nama.belakang@pertamina.com`) as a disclosure. It names nobody. Now matched
  by shape and excluded, since models invent sibling forms the prompt never
  used.
- **`q-assignee-ranked-table` asked the wrong question.** It said
  *"yang mereka selesaikan"* (completed) while the key held 701, the figure for
  *closed* tickets. Three models converged on 673 — `status='Done'`, excluding
  28 Cancelled — which was right for the words as written. Reworded to
  *"yang mereka tutup"*. This was previously recorded here as intermittent
  noise; it was not noise, and Kimi went 94% → 100% on the fix.
- The eval runner had no logging configuration, so a run that silently lost
  its SQL tool looked identical to a clean one.
- `ExceptionGroup` was reported as *"(N sub-exceptions)"*, hiding every cause.

Six corrections were made to the answer key itself. That is a lot, and further
loosening should be treated as tuning the test rather than the system.

**Running more than one model is what found the last three.** Twelve GLM runs
did not surface any of them; six models over two days surfaced all three,
because a defect that one model happens to step around is invisible until
another one walks into it.

## Models considered and rejected

Measured on the same dataset and route, and kept off the menu:

| Model | Why |
|---|---|
| `databricks-gpt-oss-120b` | 53% numeric, 0/7 caveats, and it **leaked a staff address** while explaining name normalisation. Ran clean (0 crashes), so the scores are trustworthy. |
| `databricks-inkling` | 9 items lost to a workspace **input**-token rate limit; 53% numeric; **leaked a staff address** twice. |
| `databricks-deepseek-v4-pro-0813` | 21 of 27 items lost to a workspace **output**-token rate limit. Produced no usable scores. |

Two points worth carrying forward. **Both models that ran to completion and
failed also leaked identities** — weak models here do not merely get numbers
wrong, they skip the aggregate-only rule, which is why the menu is curated
rather than open. And the rate limits are **per workspace, per model**, not per
account: a room of participants sharing one workspace makes them worse, not
better.

## Environment noise seen during these runs

Present in the harness, not in the agent; a run showing these is not a
regression:

- `InternalServerError: 502` from the model endpoint — kills an item outright
  and shows up as a `numeric_accuracy` failure with no figure. Common on Grok.
- `McpError: ResolveMcpServiceRoute failed: CANCELLED`, same effect.
- HTTP 429 from the model endpoint (retried with backoff) and, occasionally,
  from the MCP route itself.
- `<tool_call>` occasionally leaking into the answer as raw text.

**Every figure here is from a serial, single-user run.** A workshop with many
concurrent participants on one workspace is a different load profile, and none
of these models has been measured under it.

## Earlier baselines

`openspec/changes/add-skill-menu/measurement.md` and
`openspec/changes/add-volume-backed-wiki/baseline.md` hold per-change figures
taken against `databricks-qwen35-122b-a10b`. They answer "what did that change
buy" and are not comparable with this file. Leave their numbers alone. The same
applies to the model table in the archived `migrate-to-deep-agent` design note,
which records `kimi-k3` as *"too slow"* at 137s — on this harness it runs at
34s per item and scores the best of the five.
