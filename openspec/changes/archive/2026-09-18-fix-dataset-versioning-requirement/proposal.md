## Why

`agent-evaluation` requires something the platform forbids.

The requirement *Expectations are versioned against system capability* says that when a capability makes a previously unanswerable question answerable, "the affected items SHALL be updated to expect an answer, **and the dataset version SHALL change**."

`add-volume-backed-wiki` did exactly the first half: the resolution-target items flipped from `decline` to `value` once the wiki supplied the target. It could not do the second. Langfuse dataset item ids are unique **per project across datasets**, and remain reserved after deletion — so seeding a `sdlc-agent-eval-v2` fails with a 409 on the first item that reuses an id.

Stable ids and a versioned dataset *name* are therefore mutually exclusive, and stable ids are the more valuable of the two: they are what makes a run comparable to an earlier run item by item, which is the whole point of the dataset. The implementation kept the ids and documented the conflict in `agent_evaluation/dataset.py`.

That leaves the capability non-conformant with its own spec. The requirement's intent is sound — a consumer must be able to tell which set of expectations a score was measured against — but it fixed on one mechanism for expressing that, and the mechanism is unavailable.

## What Changes

- Amend the requirement so it demands that the version **be recorded and discoverable**, rather than that the dataset's identity change. The obligation moves from the name to the record.
- State the consequence the current implementation already lives with and should not hide: because the dataset is mutated in place, **superseded expectations are not re-runnable**. Past runs keep their recorded scores, but the previous answer key is gone once the definitions change.
- Add a scenario for the platform constraint itself, so a future reader does not re-derive it: where item identity must be stable across versions, the version SHALL be carried alongside the dataset rather than inside its name.

## Capabilities

### Modified Capabilities
- `agent-evaluation`: The requirement *Expectations are versioned against system capability* currently mandates a dataset version change. Amended to require that the version be recorded and discoverable, with the immutability consequence stated, so the requirement is satisfiable on a platform where item ids are unique across datasets.

## Impact

- **`openspec/specs/agent-evaluation/spec.md`** — one requirement amended; the other seven unchanged.
- **No code changes.** `agent_evaluation/dataset.py` already records the version in the dataset description and the run name, and already documents why the name cannot carry it. This change makes the spec describe what is built rather than what was assumed buildable.
- **What is given up** — the ability to re-run a superseded answer key. That was already lost the moment the items were mutated in place; this change stops the spec implying otherwise.
