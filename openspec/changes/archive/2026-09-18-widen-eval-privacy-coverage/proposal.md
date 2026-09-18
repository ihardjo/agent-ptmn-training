## Why

The evaluation could not tell whether a privacy fix worked.

`no_pii_leak` guarded three items, so a single answer moved the score by 33 points. Across six runs it read 0, 33, 67, 67, 100, 100 — a 100-point spread on an agent nobody had changed. When the deep-agent migration made privacy worse and a prompt edit was written to recover it, the before-and-after was 33 % against 50 %: entirely inside that noise. The intervention could not be evaluated, so it could not be iterated on.

That is the worst failure available to an evaluation. A score that cannot detect a change invites the conclusion that the change worked.

This is also the one measurement blocking real progress, because the behaviour it fails to resolve is the most consequential one in the application: the agent's data is Pertamina staff names, and it has been observed naming them.

## What Changes

- Widen `no_pii_leak` coverage from **3 items to 10**, taking the dataset from 19 items to 26.
- Design the additions around **distinct leak paths** rather than more variations of the same question — a name escapes differently through a ranked table, a raw-row dump, a single-record lookup, and a methodology explanation, and each needs its own item:
  - the reporter column as well as the assignee column, where the distribution is flat rather than concentrated
  - a ranked per-person table, the exact shape that leaked at baseline
  - a direct request for one ticket's people, where the data *has* the answer and policy forbids reporting it
  - a raw-row dump, the most direct leak there is and the most innocent-sounding request
  - an explanation of the name-normalisation method, which invites quoting the variant spellings as examples
- Add **two control items** that concern people but need no name — the count of unassigned tickets, and the number of distinct assignees. Without them, a privacy rule pushed too hard scores well by refusing every question that mentions staff.
- Add a `NORMALISED` constant for the identity-normalisation SQL fragment, shared by the items that aggregate by person.
- Record the resulting diagnostic: which leak paths fail consistently, which intermittently, and which hold.

## Capabilities

### Modified Capabilities
- `agent-evaluation`: Two requirement changes. *Personal names are checked exactly, not judged* gains scenarios for the distinct ways a name reaches an answer, and for the case where the data holds an identity that policy forbids reporting. A new requirement states that coverage of a scored behaviour must be sufficient to resolve a change in it — the lesson three items taught, generalised so it applies to every behaviour under test rather than only this one.

## Impact

- **`agent_evaluation/dataset.py`** — seven items added, one shared SQL constant, 26 items total.
- **Langfuse `sdlc-agent-eval-v1`** — re-seeded; upserts by stable id, so no duplicates.
- **Run cost rises with item count** — roughly 26 items at ~10 s each, serial, because the mutation-risk item forces it.
- **Comparisons across the widening are not like-for-like.** `no_pii_leak` before and after this change have different denominators, and the archived baseline's privacy figures are not directly comparable to anything measured afterwards.
- **Does not fix the agent.** This change makes the regression measurable; it does not attempt to repair it. That is deliberately separate, because a fix attempted before the measurement existed is what produced the unusable 33-versus-50 comparison in the first place.
