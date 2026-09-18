## Why

The workshop's only table, `workshop_ai_platform.example.data_tiket_it`, has seven Indonesian columns and undesigned contents. Two consequences block the training course: the data holds no findings worth discovering, so an analyst agent has nothing to be good at; and because nobody knows what is true in it, no evaluation set can be built against it. Ground truth cannot be derived from data whose properties are accidental.

Its column names are also uniformly hostile — every one needs backtick escaping. That teaches escaping by brute repetition rather than by inspection, and it models a table nobody would design.

## What Changes

- Add `workshop_ai_platform.example.sdlc_tickets`: 24 columns, vendor-neutral naming, spanning **planned and unplanned work** in one table (`ticket_type` ∈ Bug, Story, Task, Incident, Service Request, Change). The unified model is what makes capacity-split questions answerable at all.
- Split the single resolution timestamp into `created_at` / `started_at` / `closed_at`, yielding **wait time** and **cycle time** as distinct measures.
- Apply a language rule: **tool-generated fields in English, human-entered fields in Bahasa Indonesia** (`title` and `Custom Field (Root Cause)` are Bahasa; all enums are English).
- Keep a **hostile minority** of three carried-over custom-field columns (`Custom Field (Root Cause)`, `Time Spent (hours)`, `Env/Region`) so escaping must be learned by inspecting a schema rather than applied reflexively.
- Populate ~4,000 rows across 18 months with **seven planted findings** and **six planted defects**, so that discovery and data-quality work both have known answers.
- Enforce **five deliberate absences** (no SLA target, no squad, no release, no cost, no free-text description) so that questions with no answer in the data exist by design.
- Update `agent_server/prompts/system_prompt.md` to name the new table, its columns, and the narrowed escaping rule.
- **BREAKING**: `data_tiket_it` is renamed to `data_tiket_it_deprecated`, breaking any reference to it. A later, separately-confirmed step drops it.

## Capabilities

### New Capabilities
- `sdlc-ticket-dataset`: The shape and known properties of the workshop's training table — its schema, its language rule, the findings and defects planted in it, and the absences maintained in it. Requirements here are what later evaluation work derives ground truth from.

### Modified Capabilities
- `cross-workspace-sql`: The requirement *Generated SQL is valid against the remote catalog* assumes every column needs escaping and its scenarios name `data_tiket_it`. Both change: the target table is renamed, and escaping now applies to a documented minority of columns, so the agent must determine which from the schema rather than assume all.

## Impact

- **Jakarta workspace data** (`dbc-86b2f2e8-b955`, `workshop_ai_platform.example`) — one table added, one renamed. DDL requires table ownership, which the app's service principal does not hold; use the `jakarta-workshop` CLI profile.
- **`agent_server/prompts/system_prompt.md`** — rewritten for the new schema.
- **Recovery** — the rename is instantly reversible. The eventual drop is recoverable only via Delta time travel, bounded by `VACUUM` retention (7 days).
- **Downstream** — `add-langfuse-eval-dataset` cannot derive ground truth until this lands and its planted findings are verified in real rows.
- **No application code changes.** Tools, routes, and serving are untouched.
