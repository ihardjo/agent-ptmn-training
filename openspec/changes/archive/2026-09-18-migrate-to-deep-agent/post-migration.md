# Post-migration measurement

Three configurations of the 19-item `sdlc-agent-eval-v1` dataset. The baseline
column is the flat `create_agent` loop on `gpt-oss-120b`, recorded in the
archived `add-langfuse-eval-dataset` change. The other two are the deep agent,
first on the old endpoint and then on `qwen35-122b-a10b` (design Decision 9).

`tool_efficiency` became comparable at this point: statement capture now filters
on the tool name, so plans, delegations, and skill reads are no longer counted
as SQL (design Decision 7).

## Scores

| Evaluator | flat, gpt-oss (3 runs) | deep, gpt-oss (2 runs) | deep, qwen35 (2 runs) |
|---|---|---|---|
| `sql_identifiers_escaped` | 100 / 100 / 100 | 100 / 100 | **100 / 50** |
| `correct_duration_used` | 100 | – / 100 | 100 / 100 |
| `declined_correctly` | 82 / 84 / 82 | 84 / 76 | 84 / 84 |
| `numeric_accuracy` | 70 / 80 / 70 | 70 / 80 | 90 / 70 |
| `caveat_present` | 75 / 50 / 25 | – / 25 | **75 / 75** |
| `no_pii_leak` | 100 / 100 / 67 | 100 / 100 | **0 / 67** |
| `no_mutation` | 0 / 100 / 100 | 0 / 0 | 0 / 0 |

| Cost | flat, gpt-oss | deep, gpt-oss | deep, qwen35 |
|---|---|---|---|
| statements per item | 1.63 | 1.32 / 1.95 | 2.58 / 2.53 |
| seconds per item | 7.0 | 7.2 / 10.8 | 10.8 / 10.2 |
| run wall clock | 133 s | 137 s / 206 s | 204 s / 195 s |

## What was gained

**Planning works, which is the point of the migration.** On `qwen35-122b-a10b`
a multi-step question produced seven `write_todos` calls with revisions and
status transitions, in Bahasa. On `gpt-oss-120b` it produced none, even when
the question explicitly asked for a plan first.

**`caveat_present` improved and stabilised** — 75 % on both runs, against a
baseline that swung 75 / 50 / 25. This was the weakest evaluator at baseline
and is now among the steadier ones.

## What was lost, and it is not a small thing

**Privacy compliance got worse.** `no_pii_leak` scored 0 % and 67 %, against
100 / 100 / 67 at baseline. In the first run the agent named individuals in all
three privacy items — including a second person the baseline never leaked. The
rule is stated twice in the prompt, once as a numbered override at the top. For
an agent whose data is Pertamina staff names, this is the most consequential
regression in the table.

**Identifier escaping broke for the first time.** `sql_identifiers_escaped` came
in at 50 %, having been 100 % on all five previous runs across both earlier
configurations. It was the single most stable signal available, and it is no
longer stable.

**The destructive instruction is still obeyed.** `no_mutation` failed on all
four deep-agent runs. The harness detected the `DELETE` and restored the table
each time, but the agent is carrying out an instruction it was told to refuse,
and the deep configuration has not failed to do so once.

## Honest limits on these numbers

Two variables moved at once — the agent architecture and the model — so no
movement here can be attributed to either alone. Two runs per configuration
against a baseline that swings 50 points on some evaluators means most of these
differences are not separable from noise. The exceptions, because they fall
outside the baseline's observed range, are `caveat_present` (better),
`no_pii_leak` (worse), and `sql_identifiers_escaped` (worse).

Cost is unambiguous: roughly 1.5× the latency and 1.6× the statements per item
against the flat baseline.

## An attempted privacy fix, and why it cannot be called a fix

The privacy rule was sharpened after the runs above: rule 1 now names rank as
the substitution for an identity, states that it holds even when a name is asked
for outright, forbids pasting a result row containing a name, and the People
section carries a worked ranked table with the names removed. Two further runs
followed.

| Evaluator | qwen35, before (2 runs) | qwen35, after (2 runs) |
|---|---|---|
| `no_pii_leak` | 0 / 67 | **67 / 33** |
| `sql_identifiers_escaped` | 100 / 50 | **100 / 100** |
| `numeric_accuracy` | 90 / 70 | **80 / 90** |
| `caveat_present` | 75 / 75 | **75 / 50** |
| `declined_correctly` | 84 / 84 | **84 / 84** |
| `no_mutation` | 0 / 0 | **100 / 0** |

Leaked items fell from four across two runs to three, and the mean moved from
33 % to 50 %. **Neither is a result.** With two runs per arm, three privacy
items, and a baseline that already swings 100 / 100 / 67 on this evaluator,
nothing here separates the edit from noise. The honest statement is that the
privacy regression against the flat `gpt-oss` baseline persists and the prompt
edit did not demonstrably recover it.

Two things did firm up, and both are worth keeping: escaping returned to 100 %
on both runs, suggesting the earlier 50 % was a one-off rather than a new
failure mode; and `no_mutation` passed for the first time on any deep-agent
run, though it failed the next one.

**The evaluator does not have the resolution to settle this.** Three privacy
items means each one is worth 33 points. Measuring whether a privacy
intervention worked needs enough privacy items that a single answer cannot move
the score by a third — closer to ten. That is a change to the dataset, not to
the agent, and it should come before any further attempt at this regression.

## The decision this leaves open

The migration delivers the capability it set out to deliver. It also degrades
two compliance behaviours that matter more than accuracy for this application,
one of which — not naming staff — is the rule this agent has been observed
breaking since before the migration.

Reverting the endpoint restores privacy and loses planning. Keeping it means
carrying a privacy regression that one prompt edit did not fix and that the
current dataset cannot measure precisely enough to iterate against.

The sequence that follows from the evidence is: add privacy items to the
dataset until the evaluator has usable resolution, then attempt the regression
again with something that can actually be measured. Until then, "the agent
sometimes names staff" is a known, reproduced defect of this configuration
rather than a solved problem, and it should be stated that way to anyone the
workshop is run for.
