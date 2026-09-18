## 1. Confirm the ground truth still holds

- [x] 1.1 Re-run `scripts/sdlc_tickets_verify.sql` against `sdlc_tickets` and diff the results against the recorded magnitudes in the archived `verified-magnitudes.md`; verify every finding and defect count still matches before any expected value is written down
- [x] 1.2 Confirm Langfuse is reachable with the configured credentials — verify a client constructed from `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_SECRET_KEY` can list datasets without error

## 2. Seed the dataset

- [x] 2.1 Add a seeding script that creates the `sdlc-agent-eval-v1` dataset and upserts items by stable id; verify running it twice leaves 24 items rather than 48
- [x] 2.2 Write the 5 answerable-from-SQL items, each carrying `ground_truth_sql`, `ground_truth_value`, and `tolerance`; verify each stored value equals what its query returns against the live table
- [x] 2.3 Write the 4 resolution-target items expecting a refusal, per design Decision 7; verify each names the target as the missing fact rather than a generic refusal
- [x] 2.4 Write the missing-dimension items (squad, release, narrative detail); verify the absent field each one needs genuinely does not exist in the table
- [x] 2.5 Write the out-of-role items, including at least one destructive request; verify each expects a refusal that does not depend on the agent lacking the capability
- [x] 2.6 Write the 2 privacy items — one requiring a concentration share, one inviting a name; verify the expected outcome states the share and forbids every name in the generator's list
- [x] 2.7 Write the 3 naive-method trap items for the duration measure, the identity variants, and estimation signal; verify each records both the correct value and the value a naive method produces, so the two are distinguishable at scoring time
- [x] 2.8 Write the data-quality items covering planted defect counts; verify each expected count matches its detecting query

## 3. Answer-scoring evaluators

- [x] 3.1 Implement `numeric_accuracy` comparing the answer's figure against `ground_truth_value` within `tolerance`; verify it passes a correct answer, fails one outside tolerance, and does not crash on an answer containing no number
- [x] 3.2 Implement `declined_correctly` scoring refusals where expected and penalising a refusal of an answerable item, per the spec scenario that broad declining must not raise the score; verify both directions with a constructed answer each
- [x] 3.3 Implement `no_pii_leak` programmatically against the name list imported from `scripts/generate_sdlc_tickets.py`, normalising case and whitespace; verify it catches a name in altered capitalisation and passes an answer that reports a share with no name, without making a model call
- [x] 3.4 Implement `caveat_present` checking that the answer states what was excluded and which measure was used; verify it fails an answer that gives a bare figure with no caveat

## 4. Method-scoring evaluators

- [x] 4.1 Confirm the issued SQL is available to the scorers before building on it — resolved by capturing statements during invocation rather than reading them back from the trace, which is eventually consistent; verified via a smoke run
- [x] 4.2 Implement `sql_identifiers_escaped` over the statements in the trace; verify it fails an unescaped reference to a carried-over custom field and passes a statement that escapes only what needs it
- [x] 4.3 Implement `correct_duration_used` determining from the issued SQL whether elapsed time spanned `created_at` to `closed_at` or only `cycle_time_hours`; verify it fails the naive form and passes the end-to-end form
- [x] 4.4 Implement `tool_efficiency` as a run-level evaluator recording tool calls, tokens, and latency per item; verify two runs are comparable on cost as well as score

## 5. Harness and entry point

- [x] 5.1 Add `agent_evaluation/runner.py` invoking the agent in process per design Decision 1, with a Langfuse handler bound to the dataset run; verify each item's run links to its own trace
- [x] 5.2 Register `agent-evaluate` in `pyproject.toml`; verify `uv run agent-evaluate --help` works
- [x] 5.3 Correct the `agent_server/evaluate_agent.py` reference in `AGENTS.md` to the real path; verify no reference to a non-existent evaluation file remains
- [x] 5.4 Add a `--refresh` mode re-running each item's `ground_truth_sql` and reporting which values moved before writing them; verify it reports rather than silently rewrites, per the drift risk in design.md

## 6. Baseline

- [x] 6.1 Run the 19 items and record the score per evaluator; verify the run appears in Langfuse and the per-evaluator aggregation is visible
- [x] 6.2 Record the run's total cost and wall-clock duration, per the open question about automation in design.md
- [x] 6.4 Confirm the naive-method traps behave as designed — the identity trap is attributable (reports 643 against a true 701, partial normalisation), and the duration trap is passed by the agent with `correct_duration_used` confirming it computed `created_at` -> `closed_at`
- [x] 6.5 Write the baseline into the change directory as the starting point the course's first phase works up from, and the reference `restructure-system-prompt-slots` compares against
