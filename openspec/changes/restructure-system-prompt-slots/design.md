## Context

See proposal.md — Why. The constraints that shape the approach:

- `agent_server/agent.py` reads the prompt once at import with `read_text()`, and the comment there records a deliberate intent: the instructions live as prose in their own file so they can be edited and reviewed without touching Python. Any structure added must not cost that.
- Reordering or re-sectioning a prompt can change model behavior even when no instruction is added or removed. This change therefore has a measurement dependency, not merely a sequencing preference.
- The current content maps onto the five slots very unevenly, and far less evenly than when this change was written. The file is now 147 lines in eight sections: two numbered override rules, then *The data*, *Writing SQL*, *Reading results*, *Time: two different durations*, *What this data cannot tell you*, *People*, and *Format*. Role and Task are still one opening sentence; Context is now six sections; Format exists; Example still does not.
- An evaluation exists, with 26 items and recorded run-to-run variance. Three of its evaluators are too thinly covered to support a conclusion, and `agent-evaluation` now has a requirement saying so explicitly.

## Goals / Non-Goals

**Goals:**
- A slot boundary that a diff can name and a script can extract.
- Content preserved, so any measured behavior change is attributable to restructuring alone.

**Non-Goals:**
- Not removing or rewording any existing instruction. Every line the agent was told before, it is still told.
- Not changing the model, the tools, or the eval dataset, so that a measured movement has only one plausible cause.
- Not splitting into multiple files, and not moving the prompt into Python or YAML.
- Not changing the read path, caching, or reload behavior.

## Decisions

### 1. One file with delimiters, not five files

Five files would make each slot trivially extractable but would break the property the existing code comment is protecting: the prompt as one piece of continuous prose a reviewer can read top to bottom. A prompt read as five fragments is harder to keep coherent, and incoherence between slots is the failure mode that matters most.

*Alternative considered.* Five files under `prompts/slots/`, concatenated at import. Rejected on reviewability. *Also considered:* YAML or TOML with slot keys. Rejected — it turns prose into a quoted string and invites escaping problems in text that contains backticks and code fences.

### 2. Comment-style delimiters that survive rendering

Delimit slots with HTML comment markers, so the file remains valid, readable Markdown that renders cleanly and can still be extracted by a simple scan:

```
<!-- slot: role -->
...
<!-- /slot: role -->
```

Markdown headings alone were considered and rejected: headings are content, they appear in the text sent to the model, and a trainee editing a heading would change the prompt while appearing to change structure. Comment markers are inert.

### 3. Context keeps its three named sub-parts

The Context slot carries `topic`, `goal`, and `detail` as labelled sub-parts rather than free prose, because that is the distinction the course teaches and the one trainees most often collapse. These are content, not delimiters, so they are plain labels inside the slot.

### 4. The empty slots are filled, not declared empty — this reversed

The original decision was to create `goal` and `example` and leave each with a line saying what belongs there. Implementation made that untenable for a reason Decision 2 had wrong: the prompt is `read_text()` straight into `system_prompt=`, with no rendering step, so **HTML comments reach the model verbatim**. A declared-empty slot is therefore not inert scaffolding — its explanatory text becomes part of the agent's instructions, which is the thing the non-goal forbade.

Given the choice between adding placeholder prose the model reads as instruction, or adding the real content the slot is for, the real content is better. So both slots are filled:

- `context.goal` states who reads these answers and what they decide with them. The prompt has never said, and the Format rules ("lead with the figure that answers the question") only make sense against it.
- `example` carries a worked answer demonstrating the shape: figure first, evidence naming table and filter, which duration measure and why, then what was excluded and how many rows.

**The example carries no figures.** Placeholders stand where computed values go. A first draft used concrete numbers and got one wrong — it claimed 163 `Blocked` tickets where the table holds 121 — which would have put a false fact inside a prompt whose own override rule 2 forbids supplying numbers the data does not contain. Concrete figures also invite recitation instead of querying. Placeholders remove both risks.

*What this costs.* The change is no longer behaviour-neutral, and cannot be verified as though it were. Decision 6 already compares ranges rather than asserting equality; the difference is that a movement is now an expected result to be explained rather than a failure to be reverted.

*What remains of Decision 2.* Comment markers still reach the model — about ten short structural lines. That is accepted rather than solved: stripping them at load would make the delimiters load-bearing at runtime, which the risk section explicitly did not want, and the alternative of abandoning slots gives up the vocabulary the course teaches.

### 5. This change lands after a baseline evaluation exists

Restructuring can move behavior. Without a measurement, "content preserved" is an assertion. With the evaluation dataset in place, the restructure can be checked by running the same eval before and after.

This inverts the order proposed earlier and is the reason it is called out here rather than left implicit: a course whose whole thesis is *measure before you change* should not restructure its own prompt on faith.

### 6. "Unchanged" is only claimable on the evaluators that can carry it

The original plan was to confirm the score does not move. That is no longer a valid method, and the reason is a requirement this project added since: where one answer moves an evaluator by more than the variation between unchanged runs, the behaviour is **unmeasured rather than measured**, and no conclusion about an intervention may be drawn from its score.

By that rule the evaluators divide:

| Evaluator | Items | Points per answer | Can it certify "unchanged"? |
|---|---|---|---|
| `declined_correctly` | 26 | 4 % | yes |
| `numeric_accuracy` | 14 | 7 % | yes |
| `no_pii_leak` | 10 | 10 % | yes |
| `caveat_present` | 4 | 25 % | no |
| `sql_identifiers_escaped` | 2 | 50 % | no |
| `correct_duration_used` | 1 | 100 % | no |
| `no_mutation` | 1 | 100 % | no — and it has read 0 / 100 / 100 unchanged |

So the restructure is verified against the first three, over **three runs before and three after**, comparing the observed range rather than a single reading. A movement inside the pre-existing range is not evidence of drift; a movement outside it is. The other four are recorded but explicitly not used to accept or reject the change.

The counts are derived from the dataset rather than asserted here, and `sql_identifiers_escaped` is in the list because deriving them turned it up: at two items it has been 100 % on almost every run and read 50 % once, which is one answer moving and not a trend. It had been quoted earlier as though it were a stable signal.

*Consequence worth stating.* This change cannot prove the restructure is behaviour-neutral, and after Decision 4 it no longer claims to be. What the comparison can establish is the size and direction of the movement on the three evaluators with resolution, and whether it exceeds the variation those evaluators already show. Anyone reading "the score did not move" later should find that distinction here rather than having to reconstruct it.

### 7. Mapping eight sections onto five slots

Where each current section goes, so the mapping is reviewed rather than invented during implementation:

| Current section | Slot |
|---|---|
| opening sentence ("You are a delivery data assistant…") | **Role** |
| "You answer questions about… never from general knowledge" | **Task** |
| the two numbered override rules | **Role** — they are identity-level constraints, and they stay first inside it |
| *The data* | Context · topic |
| *Writing SQL*, *Reading results* | Context · detail |
| *Time: two different durations* | Context · detail |
| *What this data cannot tell you* | Context · detail |
| *People* | Context · detail, **whole and unsplit** — see the reversal below |
| *Format* | **Format** |
| — | **Example** stays declared and empty (Decision 4) |

The override rules stay in Role rather than becoming a sixth slot, because they define what the agent *is* permitted to be, and a slot that sits outside the five would defeat the point of having five.

**The *People* split was tried and reverted.** The argument for it was clean: the facts about the columns are Context, while "report in aggregate, identify by rank" is an instruction about output and belongs with the other output instructions. It was implemented, measured over three runs, and backed out.

The measurement is in `measurement.md`. In summary: no usable evaluator moved clear of its baseline band, but `no_pii_leak`'s band shifted down ten points at both ends, and per item three of ten privacy items got worse against one better — `q-who-closes-most` going from failing one run in three to failing all three. The risk register had named this split as the one plausible route to behavioural drift, and task 3.2 existed to watch for it, so the direction was pre-registered rather than found by looking afterwards.

That is a correlation and not a demonstration: two changes landed together and three runs a side cannot separate them. The reversal is a judgement rather than a finding — the split bought tidiness, the regression is on the one rule this agent has broken repeatedly since before any of this work, and the trade is not worth taking on suggestive evidence. *People* returns byte-identical to its original form, inside `context`.

*What is given up.* The slot model is now less clean: `context` carries an instruction about output. That is the honest state — the five slots are a useful vocabulary, not a taxonomy that the existing prompt happens to fit. A later change with wider privacy coverage could retry the split and actually measure it.

## Risks / Trade-offs

- **Restructuring silently changes behavior** → checked against the three evaluators with enough coverage to detect it, over three runs each side, per Decision 6. This is the only real risk in the change, and it cannot be fully retired — only bounded.
- **Splitting *People* across Context and Format changes emphasis even with wording preserved** → the privacy rule is the behaviour already known to be fragile, and `no_pii_leak` has the coverage to detect a change in it. Watched specifically rather than assumed safe.
- **Delimiters drift out of sync with content as trainees edit** → markers are inert comments, so a mismatched or deleted marker is visible in review; no runtime dependency on them exists in this change.
- **Declared-but-empty slots invite filler** → each empty slot states what belongs there rather than inviting prose for its own sake.
- **A future reader assumes the delimiters are load-bearing at runtime** → they are not, in this change. If later tooling extracts slots, that tooling introduces the dependency and should say so.

## Migration Plan

1. Run the evaluation three times and record the range per evaluator.
2. Restructure the file, preserving content, per the mapping in Decision 7.
3. Run three more times and compare ranges on the three evaluators that can carry the conclusion.

**Rollback.** Revert the file. Nothing else changes, and no runtime behavior depends on the markers.
