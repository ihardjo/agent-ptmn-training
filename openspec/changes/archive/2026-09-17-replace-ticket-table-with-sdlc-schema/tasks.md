## 1. Establish the Jakarta execution path

- [x] 1.1 Confirm the `jakarta-workshop` profile targets `dbc-86b2f2e8-b955` and is valid — `databricks auth profiles` shows it `YES`; do not use the `jakarta` profile, which points elsewhere and is invalid
- [x] 1.2 Identify the compute that will run DDL and the row load — list warehouses with `databricks warehouses list --profile jakarta-workshop` and record the id, or establish the serverless statement endpoint to use; verify by executing `SELECT 1` through it
- [x] 1.3 Confirm the identity running DDL owns `data_tiket_it` — `SHOW GRANTS ON TABLE workshop_ai_platform.example.data_tiket_it` lists it as owner, so the later rename will succeed rather than failing at step 6.1

## 2. Generator

- [x] 2.1 Add a deterministic generator under `scripts/` taking a pinned seed and row count, emitting the 24 columns of design Decision 3; verify two runs with the same seed produce identical output
- [x] 2.2 Implement the language rule — English enums, Bahasa `title` and `Custom Field (Root Cause)`, Indonesian names from the committed name list; verify by sampling 20 rows and checking each field against design Decision 5
- [x] 2.3 Implement the three-timestamp model with `cycle_time_hours` covering only `started_at` → `closed_at`, and absent timestamps for work not yet at that stage; verify no row has a duration derived from an absent timestamp
- [x] 2.4 Implement the hand-specified distributions for findings F1–F7 per design Decision 7; verify each planted magnitude against the generated output in-process before any load
- [x] 2.5 Implement planted defects D1–D6 at the recorded counts per design Decision 8; verify each count exactly in the generated output
- [x] 2.6 Enforce the deliberate absences — no target, squad, release, cost, or description field is emitted; verify the emitted column list equals the 24 in design Decision 3
- [x] 2.7 Commit the verifying query for each of F1–F7 and the detecting query for each of D1–D6 alongside the generator, so ground truth can be refreshed later by re-running them

## 3. Create and load the table

- [x] 3.1 Create `workshop_ai_platform.example.sdlc_tickets` with the 24 columns and their types; verify with `DESCRIBE TABLE` that names and types match design Decision 3, including the three escaped identifiers
- [x] 3.2 Add a table comment recording that data-quality defects are intentional and pointing at the generator, so the planted defects are not read as a load failure
- [x] 3.3 Load ~4,000 generated rows spanning 18 months; verify the row count and that `MIN(created_at)` / `MAX(created_at)` span the intended window
- [x] 3.4 Verify the conformed core needs no escaping — run a query selecting several bare-word columns without backticks and confirm it parses and returns rows
- [x] 3.5 Verify the hostile minority needs escaping — run an unescaped reference to `Custom Field (Root Cause)` and confirm it fails to parse, then confirm the escaped form succeeds

## 4. Verify the planted properties against real rows

- [x] 4.1 Run each F1–F7 verifying query against `sdlc_tickets` and record actual magnitudes; verify each is present at the magnitude in design Decision 7
- [x] 4.2 Run each D1–D6 detecting query and record actual counts; verify each matches design Decision 8
- [x] 4.3 Confirm F1 produces the intended misrepresentation — verify that characterising duration from `cycle_time_hours` alone materially understates end-to-end time, so the naive answer is wrong rather than merely incomplete
- [x] 4.4 Confirm D5 silently understates F7 — verify that aggregating closures by raw `assigned_to` splits the concentrated individual across groups and lowers the reported share, with no error raised
- [x] 4.5 Confirm the deliberate absences hold — verify no column exists from which squad, release, cost, resolution target, or narrative description could be read
- [x] 4.6 Record the confirmed magnitudes and counts in the change directory, as the input the downstream evaluation change derives ground truth from

## 5. Point the agent at the new table

- [x] 5.1 Rewrite `agent_server/prompts/system_prompt.md` for `sdlc_tickets` — its 24 columns, the planned/unplanned distinction, the wait-versus-cycle distinction, and the absent-timestamp semantics
- [x] 5.2 Narrow the escaping instruction from "every column" to the three carried-over fields, instructing the agent to determine which identifiers need escaping from the schema; verify the agent escapes `Custom Field (Root Cause)` and does not report bare-word columns as unavailable
- [x] 5.3 State in the prompt that no resolution target exists in the data and that adherence questions are unanswerable until a target is supplied from outside it; verify the agent reports the gap rather than inventing a target
- [x] 5.4 State the aggregate-only rule for `reported_by` and `assigned_to`; verify the agent reports the F7 concentration as a share without naming the individual
- [x] 5.5 Run the agent locally with `uv run start-app` and confirm it answers a question over `sdlc_tickets` end to end from live Jakarta data

## 6. Retire the old table

- [x] 6.1 `ALTER TABLE workshop_ai_platform.example.data_tiket_it RENAME TO data_tiket_it_deprecated`; verify the old name no longer resolves
- [x] 6.2 Confirm nothing depended on the old name — verify the agent still answers from `sdlc_tickets` after the rename, and that no reference to `data_tiket_it` remains in `agent_server/`
- [x] 6.3 Leave `data_tiket_it_deprecated` in place; dropping it is out of scope for this change and requires separate confirmation
