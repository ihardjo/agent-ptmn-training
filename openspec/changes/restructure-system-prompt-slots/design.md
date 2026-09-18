## Context

See proposal.md — Why. The constraints that shape the approach:

- `agent_server/agent.py` reads the prompt once at import with `read_text()`, and the comment there records a deliberate intent: the instructions live as prose in their own file so they can be edited and reviewed without touching Python. Any structure added must not cost that.
- Reordering or re-sectioning a prompt can change model behavior even when no instruction is added or removed. This change therefore has a measurement dependency, not merely a sequencing preference.
- The current content already maps onto the five slots unevenly: role and task are one opening sentence, context is most of the file, format is absent, and there is no example.

## Goals / Non-Goals

**Goals:**
- A slot boundary that a diff can name and a script can extract.
- Content preserved, so any measured behavior change is attributable to restructuring alone.

**Non-Goals:**
- Not adding instructions. The Format and Example slots are established as sections but filled only with what the current prompt already implies.
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

### 4. Empty slots are declared, not omitted

The current prompt has no Format or Example content worth preserving. Both slots are created and left with a single line stating what belongs there. An absent slot reads as an oversight; a declared empty slot reads as an opening, and the first thing the tuning phase asks a trainee to do is fill it.

### 5. This change lands after a baseline evaluation exists

Restructuring can move behavior. Without a measurement, "content preserved" is an assertion. With the evaluation dataset in place, the restructure is verified by running the same eval before and after and confirming the score does not move.

This inverts the order proposed earlier and is the reason it is called out here rather than left implicit: a course whose whole thesis is *measure before you change* should not restructure its own prompt on faith.

## Risks / Trade-offs

- **Restructuring silently changes behavior** → verified by an unchanged evaluation score across the restructure. This is the only real risk in the change, and it is the reason for Decision 5.
- **Delimiters drift out of sync with content as trainees edit** → markers are inert comments, so a mismatched or deleted marker is visible in review; no runtime dependency on them exists in this change.
- **Declared-but-empty slots invite filler** → each empty slot states what belongs there rather than inviting prose for its own sake.
- **A future reader assumes the delimiters are load-bearing at runtime** → they are not, in this change. If later tooling extracts slots, that tooling introduces the dependency and should say so.

## Migration Plan

1. Run the evaluation and record the baseline score.
2. Restructure the file, preserving content.
3. Re-run the evaluation and confirm the score is unchanged.

**Rollback.** Revert the file. Nothing else changes, and no runtime behavior depends on the markers.
