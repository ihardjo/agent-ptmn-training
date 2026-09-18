"""Evaluation of the agent's behaviour.

Three modules, in dependency order:

- `dataset`  the questions and their expected outcomes, plus seeding and a
             drift check that re-derives every expected value from the table
- `scorers`  the evaluators; half score the answer, half score the method
- `runner`   drives the agent in process and reports per-evaluator scores

Kept out of `scripts/` because this is a package with internal structure rather
than a one-off tool, and out of `agent_server/` because none of it ships in the
deployed application. The data generator and loader it depends on stay in
`scripts/` — they build the table, they do not evaluate anything.

Entry point: `uv run agent-evaluate`.
"""
