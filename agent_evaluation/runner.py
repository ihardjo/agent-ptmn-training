"""Run the `sdlc-agent-eval-v1` dataset against the agent and score it.

The agent is driven **in process** rather than over HTTP. The reason is the
method scorers: they need the SQL the agent actually issued, and going through
`/invocations` severs the link between a dataset item and its run. Driving the
graph directly lets the task function capture each statement as it happens and
hand it to the evaluators, while the Langfuse trace is still produced for a
human to read.

The consequence, recorded here because it is a real gap: the serving layer —
routes, SSE framing, the translation in `agent_server/utils.py` — is not
exercised by this harness. That layer has its own requirements under
`chat-completions-serving`.

Usage:
    uv run agent-evaluate                    # all 19 items
    uv run agent-evaluate --limit 3          # a quick smoke run
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import time
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
EVAL_TABLE = "workshop_ai_platform.example.sdlc_tickets"


def _load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")


def _langfuse():
    from langfuse import Langfuse

    return Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ["LANGFUSE_HOST"],
    )


# ── the task ──────────────────────────────────────────────────────────────────

# The dataset deliberately asks the agent to delete rows, to check that it
# refuses. The service principal holds MODIFY, so an agent that complies
# actually changes the table — which happened on the first baseline run and cost
# 90 rows, recovered by Delta time travel. Detecting the mutation is therefore
# part of the harness, not an afterthought: the run records the table version
# before starting and restores it if anything was written.
# The tools that issue statements against the data. Capture filters on the tool
# name because a deep agent also calls `write_todos`, `task`, `read_file` and
# the rest — and every one of those carries string arguments. Counting those as
# statements would inflate the effort metric past comparison with the baseline,
# fail escaping checks on prose, and — worst — trip the mutation guard on a plan
# step that merely begins "Delete", which restores the table for no reason.
#
# Filtering on the argument's shape was considered and rejected: SQL is just
# text, so any heuristic both admits prose that looks like SQL and rejects SQL
# that does not.
SQL_TOOLS = frozenset({"execute_sql", "poll_sql_result"})

# The filesystem tools, split by what they tell the evaluation. Reads say the
# agent consulted the wiki rather than inventing a policy fact; writes to the
# notes tier are durable output, and the privacy rule covers them as much as it
# covers the answer.
#
# Note that these are deliberately *not* added to SQL_TOOLS. That set is an
# allowlist, so a wiki read has never counted as a statement against the data —
# which is what keeps the method and effort figures comparable with the v1
# baseline instead of inflated by the agent's reading.
# One tool set, two tiers. `read_file` serves `/wiki/` and `/skills/` alike, so
# the tier is determined by the **path prefix** and never by the tool name —
# naming this set after the wiki is what previously let skill reads fall
# through the wiki branch and vanish.
FS_READ_TOOLS = frozenset({"read_file", "ls", "glob", "grep"})
WIKI_READ_TOOLS = FS_READ_TOOLS  # retained: the wiki tests import this name
WIKI_WRITE_TOOLS = frozenset({"write_file", "edit_file"})
WIKI_PREFIX = "/wiki/"
WIKI_NOTES_PREFIX = "/wiki/notes/"
SKILLS_PREFIX = "/skills/"


def _tool_paths(args: dict) -> list[str]:
    """Path-ish string arguments of a filesystem tool call."""
    keys = ("file_path", "path", "pattern")
    return [str(args[k]) for k in keys if isinstance(args.get(k), str)]


# What a refused write looks like coming back. `Refused:` is the privacy guard
# in `agent_server/backends.py`; `permission` covers the middleware deny rule.
_REFUSAL_MARKERS = ("refused", "permission denied", "not permitted")


def _write_refused(message: Any) -> bool:
    """Whether a write tool's result reports that the write did not happen."""
    if getattr(message, "status", None) == "error":
        return True
    content = getattr(message, "content", "")
    text = content if isinstance(content, str) else str(content)
    lowered = text.casefold()
    return any(marker in lowered for marker in _REFUSAL_MARKERS)

_MUTATING = re.compile(
    r"^\s*(insert|update|delete|merge|drop|truncate|alter|create|restore)\b",
    re.I)


def _is_mutation(statement: str) -> bool:
    return bool(_MUTATING.match(statement or ""))


def _table_version(client) -> int | None:
    """Current Delta version of the evaluation table, for restore-on-mutation."""
    try:
        rows = _sql(client, f"DESCRIBE HISTORY {EVAL_TABLE} LIMIT 1")
        return int(rows[0][0])
    except Exception:
        return None


def _sql(client, statement: str):
    from scripts.load_sdlc_tickets import DEFAULT_WAREHOUSE, run

    return run(client, DEFAULT_WAREHOUSE, statement)


def _databricks():
    from databricks.sdk import WorkspaceClient

    from scripts.load_sdlc_tickets import DEFAULT_PROFILE

    return WorkspaceClient(profile=DEFAULT_PROFILE)



async def _ask(question: str) -> dict:
    """Put one question to the agent, capturing the statements it issued.

    Returns the answer text, the SQL it ran, which wiki paths it read, what it
    wrote to its notes, and how long it took — everything the evaluators need,
    none of it fetched back from a trace that may not have been ingested yet.
    """
    from langchain.messages import AIMessage
    from langfuse.langchain import CallbackHandler

    from agent_server.agent import init_agent
    from agent_server.utils import TEXT, _content_parts

    # The PII net is off for evaluation. It pseudonymises identities before the
    # model sees them, so scoring a run with it on would measure the net rather
    # than the model and `no_pii_leak` would return 1.0 for every item. The net
    # is covered by `tests/test_output_redaction.py` instead.
    agent = await init_agent(flag_pii=False, show_provenance=False)
    # Same gate as the serving layer: an unset host resolves to Langfuse cloud
    # inside the SDK, so keys without a host would ship prompts off-premises.
    host = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST")
    config = {"callbacks": [CallbackHandler()]} if host else {}

    answer: list[str] = []
    statements: list[str] = []
    wiki_reads: list[str] = []
    skill_reads: list[str] = []
    wiki_writes: list[dict] = []
    pending_writes: dict[str, dict] = {}
    started = time.monotonic()

    async for mode, payload in agent.astream(
        input={"messages": [{"role": "user", "content": question}]},
        stream_mode=["updates", "messages"],
        config=config,
    ):
        if mode == "messages":
            message = payload[0]
            if isinstance(message, AIMessage):
                for kind, chunk in _content_parts(message):
                    if kind == TEXT:
                        answer.append(chunk)
        elif mode == "updates":
            for update in payload.values():
                if not isinstance(update, dict):
                    continue
                for message in update.get("messages", []):
                    # A write's outcome arrives as the tool's result, not with
                    # the call. The privacy guard refuses in-process, so the
                    # difference between "the agent tried to write a name" and
                    # "a name reached the Volume" is only visible here.
                    call_id = getattr(message, "tool_call_id", None)
                    if call_id and call_id in pending_writes:
                        pending_writes.pop(call_id)["refused"] = _write_refused(message)
                    for call in getattr(message, "tool_calls", None) or []:
                        name = call.get("name")
                        args = call.get("args") or {}

                        if name in FS_READ_TOOLS:
                            paths = _tool_paths(args)
                            wiki_reads.extend(
                                p for p in paths if p.startswith(WIKI_PREFIX)
                            )
                            skill_reads.extend(
                                p for p in paths if p.startswith(SKILLS_PREFIX)
                            )
                            continue
                        if name in WIKI_WRITE_TOOLS:
                            if any(p.startswith(WIKI_NOTES_PREFIX) for p in _tool_paths(args)):
                                # `content` on a write, `new_string` on an edit.
                                for key in ("content", "new_string"):
                                    if isinstance(args.get(key), str):
                                        attempt = {
                                            "content": args[key],
                                            # Resolved below from the tool's own
                                            # result. Assume it landed until the
                                            # result says otherwise: a refusal
                                            # scored as a success would hide the
                                            # exact failure this measures.
                                            "refused": False,
                                        }
                                        wiki_writes.append(attempt)
                                        if call.get("id"):
                                            pending_writes[call["id"]] = attempt
                            continue
                        if name not in SQL_TOOLS:
                            continue  # planning, delegation, skill reads
                        # The SQL MCP tools name their argument variously; take
                        # whichever string argument carries the statement.
                        for value in args.values():
                            if isinstance(value, str) and value.strip():
                                statements.append(value)

    return {
        "answer": "".join(answer),
        "statements": statements,
        "mutated": [s for s in statements if _is_mutation(s)],
        "wiki_reads": wiki_reads,
        "skill_reads": skill_reads,
        "wiki_writes": wiki_writes,
        "seconds": round(time.monotonic() - started, 2),
    }


def _describe(exc: BaseException, depth: int = 0) -> str:
    """An exception's cause, including the ones an `ExceptionGroup` hides.

    `run_experiment` drives tasks inside a `TaskGroup`, so a failure arrives
    wrapped and `str()` on the group names only how many were swallowed, never
    which — "unhandled errors in a TaskGroup (1 sub-exception)" is the whole
    message. The sub-exception is the entire diagnostic value, and two items a
    run were being lost to it.
    """
    text = f"{type(exc).__name__}: {exc}"
    if depth >= 3:
        return text
    if subs := getattr(exc, "exceptions", None):
        text += " -> " + "; ".join(_describe(e, depth + 1) for e in subs)
    elif exc.__cause__ is not None:
        text += f" (caused by {_describe(exc.__cause__, depth + 1)})"
    return text


async def task(*, item, **kwargs) -> dict:
    """Async because `run_experiment` drives tasks inside its own event loop —
    `asyncio.run` cannot nest, and the agent's graph is async throughout.

    Failures are returned rather than raised: `run_experiment` collapses a task
    exception into "unhandled errors in a TaskGroup", which loses the cause and
    silently drops the item from every denominator.
    """
    question = item.input["question"] if isinstance(item.input, dict) else str(item.input)
    try:
        return await _ask(question)
    except Exception as exc:  # noqa: BLE001 - the cause is the thing we need
        detail = _describe(exc)
        print(f"  !! item {item.id} raised {detail}"[:800])
        return {"answer": "", "statements": [], "mutated": [],
                "wiki_reads": [], "skill_reads": [], "wiki_writes": [], "seconds": 0.0,
                "error": detail}


# ── item selection ────────────────────────────────────────────────────────────


def _items(client, limit: int | None) -> list:
    """Dataset items to run.

    Mutation-risk items sort last. The agent can actually carry out a delete, so
    anything running after it — or beside it — reads a table that no longer
    matches the expected values.
    """
    from agent_evaluation.dataset import DATASET

    items = list(client.get_dataset(DATASET).items)
    items.sort(key=lambda i: bool((i.expected_output or {}).get("forbid_mutation")))
    return items[:limit] if limit else items


def _has_mutation_risk(items) -> bool:
    return any((i.expected_output or {}).get("forbid_mutation") for i in items)


# ── reporting ─────────────────────────────────────────────────────────────────


def _report(result) -> None:
    """Per-evaluator aggregation — the breakdown is the point, not the total."""
    from collections import defaultdict

    scores: dict[str, list[float]] = defaultdict(list)

    for item in result.item_results:
        for evaluation in item.evaluations or []:
            if isinstance(evaluation.value, (int, float)):
                scores[evaluation.name].append(float(evaluation.value))

    # Each denominator is the number of items the evaluator applied to, not the
    # size of the run — an evaluator that does not apply returns nothing.
    print("\n── score per evaluator (denominator = applicable items) ──")
    for name in sorted(scores):
        values = scores[name]
        got, total = sum(values), len(values)
        print(f"  {name:<26} {got:>5.1f} / {total:<3} = {got / total:>5.0%}")

    print("\n── failures ──")
    any_failure = False
    for item in result.item_results:
        question = (item.item.input or {}).get("question", "?")
        for evaluation in item.evaluations or []:
            if isinstance(evaluation.value, (int, float)) and evaluation.value < 1.0:
                any_failure = True
                print(f"  [{evaluation.name}] {question[:64]}")
                print(f"      {evaluation.comment}")
    if not any_failure:
        print("  none")

    for run_eval in result.run_evaluations or []:
        print(f"\n{run_eval.name}: {run_eval.value} — {run_eval.comment}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, help="run only the first N items")
    ap.add_argument("--run-name", help="name this run in Langfuse")
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()

    _load_env()

    from agent_evaluation.dataset import DATASET
    from agent_evaluation.scorers import ITEM_EVALUATORS, RUN_EVALUATORS

    client = _langfuse()
    warehouse = _databricks()
    before = _table_version(warehouse)
    if before is not None:
        print(f"{EVAL_TABLE} at version {before} before this run")

    items = _items(client, args.limit)
    print(f"running {len(items)} item(s) of {DATASET}")

    concurrency = args.concurrency
    if _has_mutation_risk(items) and concurrency != 1:
        # Ordering alone is not enough: the final batch would still run the
        # mutating item alongside readers.
        print("  (serial: this run includes an item the agent may execute as a "
              "write, and concurrent readers would see the changed table)")
        concurrency = 1

    result = client.run_experiment(
        name=DATASET,
        run_name=args.run_name or time.strftime("%Y%m%d-%H%M%S"),
        description="agent as of this working tree",
        data=items,
        task=task,
        evaluators=ITEM_EVALUATORS,
        run_evaluators=RUN_EVALUATORS,
        # Kept low deliberately: every item is a live cross-region SQL round
        # trip plus judge calls, and hammering the warehouse skews the latency
        # figures this run is supposed to report.
        max_concurrency=concurrency,
    )
    _report(result)

    mutations = [m for r in result.item_results
                 if isinstance(getattr(r, "output", None), dict)
                 for m in (r.output.get("mutated") or [])]
    if mutations:
        print(f"\n!! the agent wrote to {EVAL_TABLE} during this run "
              f"({len(mutations)} statement(s)):")
        for statement in mutations[:5]:
            print(f"     {statement.strip()[:110]}")
        if before is not None:
            _sql(warehouse, f"RESTORE TABLE {EVAL_TABLE} TO VERSION AS OF {before}")
            rows = _sql(warehouse, f"SELECT COUNT(*) FROM {EVAL_TABLE}")
            print(f"   restored to version {before}; {rows[0][0]} rows")
    client.flush()


if __name__ == "__main__":
    main()
