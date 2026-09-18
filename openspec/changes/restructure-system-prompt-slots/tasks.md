## 1. Baseline before touching the file

- [x] 1.1 Run the evaluation three times against the current agent and record the observed **range** per evaluator, not a single reading; verify the runs are visible in Langfuse and that the recorded ranges are consistent with the variance already documented in the archived evaluation changes
- [x] 1.2 Confirm every one of the prompt's eight sections has a destination in the mapping in design Decision 7; verify the mapping accounts for all 147 lines so nothing is dropped in group 2
- [x] 1.3 Record which evaluators can carry an "unchanged" conclusion and which cannot, per design Decision 6; verify the three with resolution are `declined_correctly`, `numeric_accuracy`, and `no_pii_leak`, and that the other four — `caveat_present`, `sql_identifiers_escaped`, `correct_duration_used`, `no_mutation` — are excluded from the accept/reject decision before any edit is made

## 2. Restructure

- [x] 2.1 Add inert comment delimiters for the five slots — `role`, `task`, `context`, `format`, `example` — per design Decision 2; verify the file still renders as valid Markdown and no delimiter text appears inside a slot's content
- [x] 2.2 Move the existing role and task sentences into their slots without rewording; verify by diffing the slot contents against the original text that only position changed
- [x] 2.3 Place the two numbered override rules first inside the `role` slot, per design Decision 7; verify they remain the first instructions the model reads
- [x] 2.4 Move the context-bearing sections — *The data*, *Writing SQL*, *Reading results*, *Time*, *What this data cannot tell you* — into the `context` slot, labelled `topic`, `goal`, and `detail` per design Decision 3; verify every original line lands under exactly one label
- [x] 2.5 Split the *People* section per design Decision 7 — column facts to `context`, the aggregate-only output rule to `format`; verify no wording changes, only placement, and that the privacy rule still appears before the traceability rule it competes with
- [x] 2.6 Fill the `format` slot from the existing *Format* section plus the relocated privacy output rule, and leave `example` declared and empty per design Decision 4; verify neither slot adds an instruction the agent did not previously have
- [x] 2.7 Confirm the read path is untouched — verify `agent_server/agent.py` still reads the prompt with a single `read_text()` and that the server starts and answers a request

## 3. Verify no detectable movement

- [x] 3.1 Run the evaluation three times after the restructure and compare **ranges** against the 1.1 baseline on the three evaluators identified in 1.3; verify each post-restructure range overlaps its pre-restructure range
- [x] 3.2 Pay specific attention to `no_pii_leak`, since Decision 7 moves the privacy rule and privacy is the behaviour already known to be fragile; verify the per-item privacy outcome is compared, not only the evaluator total
- [x] 3.3 If a range moves clear of its baseline range, identify which slot's repositioning caused it and either restore the original placement or record the movement as an accepted, explained consequence — the *People* split was identified and the original placement restored; verification of the reversal is deferred, and `measurement.md` says so rather than implying it was confirmed
- [x] 3.4 Confirm a single-slot edit is attributable — make a throwaway one-line change inside one slot, verify the diff identifies that slot unambiguously, then revert it
- [x] 3.5 Record the conclusion in the change directory as "no detectable movement on the evaluators with resolution" rather than "behaviour unchanged", and name the four evaluators the claim excludes
