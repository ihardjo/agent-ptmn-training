## Context

See proposal.md — Why. The state this builds on:

- `agent_evaluation/dataset.py` holds 19 items; three carry `forbid_person_names`, which is what `no_pii_leak` applies to. The scorer returns nothing for items without that flag, so each evaluator's denominator is the number of items it applies to.
- `no_pii_leak` is programmatic: it matches the answer against every first-name/surname combination the generator could have produced, after collapsing case and whitespace. There is no judge involved and no tolerance to tune — only coverage.
- The recorded variance across unchanged runs is in the archived baseline: `caveat_present` moved 50 points, `no_mutation` 100. `no_pii_leak` itself read 0 / 33 / 67 / 67 / 100 / 100 across six runs.
- `sdlc_tickets` plants one person's name under five spellings across 45 % of their rows, so any aggregation by identity has to normalise first.
- Items upsert by stable id, so adding items is additive and re-seeding is safe to repeat.

## Goals / Non-Goals

**Goals:**
- Enough privacy coverage that an intervention's effect is separable from noise.
- A score that says *which* leak path failed, not only how many did.
- Protection against satisfying the privacy rule by refusing every question about people.

**Non-Goals:**
- No attempt to fix the leak. Deliberate, and the reason is in the proposal: a fix attempted before the measurement existed is what produced the unusable 33-versus-50 comparison.
- No change to `no_pii_leak` itself. The scorer was never the problem; it was exact and cheap and correct, applied to too few items.
- No change to the agent, the prompt, or the model.
- No attempt to make the *other* thin evaluators (`caveat_present` at 4 items, `no_mutation` and `correct_duration_used` at 1 each) adequate. They have the same defect and it is named below, but widening them is separate work.

## Decisions

### 1. Ten items, because ten is where the resolution crosses the noise

Ten items give ten points per answer. The observed run-to-run variation on this evaluator, once it has ten items rather than three, is 10 points — so a single item's worth of movement is the smallest thing the evaluator can now see, and an intervention worth more than one item is detectable.

Three items gave 33 points each, against variation of up to 67 points between unchanged runs: strictly worse than useless, because it produced numbers that looked like measurements.

*Alternative considered.* Twenty items, for finer resolution still. Rejected for now: run cost scales linearly and serially, privacy items are the slowest to author because each needs a distinct failure path rather than a variation, and ten already crosses the threshold that matters. Worth revisiting if a fix lands and the remaining failures need separating.

### 2. Distinct leak paths, not more of the same question

The three original items were all forms of "how concentrated is the work" — aggregate reporting. That is one route. A name also escapes through:

| Path | Item | Why it is different |
|---|---|---|
| ranked breakdown | `q-assignee-ranked-table` | the per-person table shape that leaked at baseline |
| reproduced record | `q-raw-rows` | the most direct leak, and the most innocent-sounding request |
| single-record lookup | `q-ticket-people` | the data *has* the identity; policy withholds it |
| method explanation | `q-normalisation-method` | inviting the variant spellings as examples |
| a second identity column | `q-top-reporter` | `reported_by` is flat (~2 %) where `assigned_to` is concentrated (23 %) |

Each fails independently, which is the point: a score aggregated over near-identical questions tells you a number, and a score aggregated over distinct paths tells you where to aim.

`q-ticket-people` is the only decline item in the dataset whose refusal is about *permission* rather than a missing field, and the spec now distinguishes the two so an agent cannot pass it by claiming the data lacks something it plainly has.

### 3. Two control items, because a privacy rule can be satisfied by uselessness

A third of this dataset already has refusal as the correct answer, and `no_pii_leak` can be satisfied outright by refusing anything that mentions a person. The counts of unassigned tickets and of distinct assignees are about people, answerable without naming one, and must not be refused.

This is not hypothetical. The regression this change exists to measure was partly *caused* by over-correction: after the privacy rule was strengthened, the agent began refusing to report concentration at all rather than reporting it anonymously. Controls make that visible as a failure instead of rewarding it.

### 4. The normalisation fragment is a named constant, and its escaping is a trap

Several items aggregate by identity and must collapse the planted spelling variants first. That SQL now lives in one `NORMALISED` constant.

It carries a comment because the escaping is genuinely treacherous: the runtime value must be the SQL text `'\\s+'`, which needs four backslashes in Python source. At two, the value is `'\s+'`, Spark unescapes the literal before the regex engine sees it, the pattern becomes `s+`, and it replaces the letter *s* inside names — mangling identities and inflating a `DISTINCT` count from 60 to 63 with no error raised.

This was caught by `--check`, which re-derives every expected value from the table. It is the clearest argument available for storing the query beside the number rather than only the number.

## Risks / Trade-offs

- **Ten items still may not be enough to separate small effects** → the achieved variation is recorded, so the next intervention can be judged against a known figure rather than an assumption. If it lands inside 10 points, that is the signal to widen again rather than to believe the result.
- **Scores before and after the widening are not comparable** → stated in the proposal and in the recorded diagnostic; the denominator changed from 3 to 10 and the archived baseline's privacy figures should not be read against anything measured after.
- **Run cost grows and the run is serial** → 26 items at roughly 10 s each. The mutation-risk item forces serial execution, so this does not parallelise away.
- **The controls could mask a real refusal problem** → they are counted under `declined_correctly` as well, so refusing them fails twice rather than being absorbed.
- **The other thin evaluators are untouched** → `caveat_present` has 4 items, `no_mutation` and `correct_duration_used` have 1 each. Every conclusion drawn from those carries the same defect this change fixes for privacy, and that should be stated wherever they are quoted until they are widened.

## Migration Plan

1. Add the items and the shared constant.
2. Re-derive every expected value from the table with `--check` before seeding anything.
3. Re-seed; confirm the item count and that upserting did not duplicate.
4. Run twice and record the per-item outcome, not only the score.

**Rollback.** Remove the items and re-seed. Ids are stable, so the removed items simply stop being upserted; nothing else in the dataset, the scorers, or the agent changes.
