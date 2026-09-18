## 1. Baseline before touching the file

- [ ] 1.1 Run the evaluation dataset against the current agent and record the score per evaluator; verify the run is visible in Langfuse and the recorded numbers are reproducible across two runs
- [ ] 1.2 Confirm the current prompt's content maps onto the five slots, noting which slots have no existing content; verify the mapping accounts for every line of the current file so nothing is dropped in step 2

## 2. Restructure

- [ ] 2.1 Add inert comment delimiters for the five slots — `role`, `task`, `context`, `format`, `example` — per design Decision 2; verify the file still renders as valid Markdown and no delimiter text appears inside a slot's content
- [ ] 2.2 Move the existing role and task sentences into their slots without rewording; verify by diffing the slot contents against the original text that only position changed
- [ ] 2.3 Move the existing context content into the `context` slot, labelled as `topic`, `goal`, and `detail` per design Decision 3; verify every original context line lands under exactly one label
- [ ] 2.4 Create the `format` and `example` slots, each stating what belongs there and nothing more, per design Decision 4; verify neither slot adds an instruction the agent did not previously have
- [ ] 2.5 Confirm the read path is untouched — verify `agent_server/agent.py` still reads the prompt with a single `read_text()` and that the server starts and answers a request

## 3. Verify the restructure moved nothing

- [ ] 3.1 Re-run the evaluation and compare against the 1.1 baseline; verify the total and per-evaluator scores are unchanged
- [ ] 3.2 If any score moved, identify which slot's repositioning caused it and either restore the original ordering or record the movement as an accepted, explained consequence rather than leaving it unexplained
- [ ] 3.3 Confirm a single-slot edit is attributable — make a throwaway one-line change inside one slot, verify the diff identifies that slot unambiguously, then revert it
