## Why

`agent_server/prompts/system_prompt.md` is one undelimited block of prose. The training course's second phase asks trainees to tune the agent's instructions one change at a time and measure the effect, which requires that a change be attributable to a named part of the prompt. In an undelimited file it is not: a diff shows that prose moved, not that the role was narrowed or the output format was tightened.

The same structure is also the substrate for a designed experiment — placing one procedure in the prompt versus in a skill and comparing accuracy and cost — which needs the prompt half of the comparison to be a single editable slot rather than a paragraph woven through others.

## What Changes

- Restructure `system_prompt.md` into five delimited slots: **Role**, **Task**, **Context** (topic / goal / detail), **Format**, **Example**.
- Use machine-readable delimiters so a diff names the slot that changed and tooling can extract one slot without parsing prose.
- Preserve existing instruction content semantically; this is a restructuring, not a rewrite of what the agent is told.
- Keep it as **one file**, not five. The read path in `agent_server/agent.py` stays a single `read_text()` and the file stays reviewable as continuous prose.

## Capabilities

No capability changes. The agent is told the same things in the same order; only the file's internal structure changes, so no spec-level behavior changes and `skip_specs: true` is set.

Note that "no behavior change" is the *intent*, not a guarantee — see design.md for why this change should land only once a baseline evaluation exists to detect drift.

## Impact

- **`agent_server/prompts/system_prompt.md`** — restructured.
- **`agent_server/agent.py`** — unchanged. The prompt is still read once at import as a single string.
- **Sequencing** — this change should follow `add-langfuse-eval-dataset`, not precede it. Restructuring instructions without a way to measure the result is the exact practice the course exists to discourage.
- **Downstream** — the tuning phase of the course, and the prompt-versus-skill placement experiment, both depend on these slot boundaries.
