## Why

`agent_server/prompts/system_prompt.md` is one undelimited block of prose. The training course's second phase asks trainees to tune the agent's instructions one change at a time and measure the effect, which requires that a change be attributable to a named part of the prompt. In an undelimited file it is not: a diff shows that prose moved, not that the role was narrowed or the output format was tightened.

The same structure is also the substrate for a designed experiment — placing one procedure in the prompt versus in a skill and comparing accuracy and cost — which needs the prompt half of the comparison to be a single editable slot rather than a paragraph woven through others.

## What Changes

- Restructure `system_prompt.md` into five delimited slots: **Role**, **Task**, **Context** (topic / goal / detail), **Format**, **Example**.
- Fold the prompt's eight current sections into those five. The file has grown from roughly thirty lines to 147 since this change was first written — it now carries two top-level override rules plus sections on the data, writing SQL, reading results, the two duration measures, what the data cannot answer, people, and format. Most of that is Context; the mapping is a judgement and design.md records it rather than leaving it to be improvised.
- Use machine-readable delimiters so a diff names the slot that changed and tooling can extract one slot without parsing prose.
- Preserve every existing instruction. Nothing the agent was told is removed or reworded.
- **Fill the two slots the prompt has never had**, rather than declaring them empty: `context.goal` states who reads these answers and what they decide, and `example` carries a worked answer showing the expected shape. This makes the change a deliberate prompt change and not a neutral restructure — see design Decision 4, which reversed on this — so the verification measures an effect rather than asserting its absence.
- Keep it as **one file**, not five. The read path in `agent_server/agent.py` stays a single `read_text()` and the file stays reviewable as continuous prose.

## Capabilities

No capability changes, and `skip_specs: true` is set. No spec states what the prompt must contain — the agent's instructions are tested by the evaluation rather than specified — so restructuring them changes no requirement.

The agent is **not** told only the same things. Two slots gain content the prompt never had, and the *People* section is split across Context and Format. Both are routes to behavioural change, which is why the verification in design.md Decision 6 compares ranges rather than asserting equality — and why a movement is now a result to be explained rather than a failure.

Note that "no behavior change" is the *intent*, not a guarantee. A baseline evaluation now exists, but it cannot certify "unchanged" on every evaluator — see design.md, which states which ones can carry that conclusion and which the specs forbid drawing it from.

## Impact

- **`agent_server/prompts/system_prompt.md`** — restructured.
- **`agent_server/agent.py`** — unchanged. The prompt is still read once at import as a single string.
- **Sequencing** — this change should follow `add-langfuse-eval-dataset`, not precede it. Restructuring instructions without a way to measure the result is the exact practice the course exists to discourage.
- **Downstream** — the tuning phase of the course, and the prompt-versus-skill placement experiment, both depend on these slot boundaries.
