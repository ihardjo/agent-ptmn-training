"""The middleware stack, and the two judgements it needs to make.

Both flags are for the evaluation harness rather than for serving: a scored run
that keeps the PII net measures the net, and one that retries a rate limit
measures the retry.
"""

import logging
from typing import Any

from langchain.agents.middleware import (
    PIIMiddleware,
    TodoListMiddleware,
    ToolRetryMiddleware,
)

logger = logging.getLogger(__name__)

# langchain's built-in email pattern ends `[A-Z|a-z]{2,}` — a character class
# that literally contains a pipe, almost certainly meant as alternation. A pipe
# straight after the TLD is therefore part of the match. That was harmless while
# the SQL server returned JSON; `system.ai.dbsql` returns markdown tables, so
# every address now swallows its own column separator and, mid-row, the next
# cell's value with it. The same person then hashes two ways and the grouping
# that `strategy="hash"` exists to preserve is lost.
#
# Identical to the upstream pattern but for that class. See
# `test_a_pipe_separator_is_swallowed_upstream`.
EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"


def _is_rate_limited(exc: BaseException, depth: int = 0) -> bool:
    """Whether this failure is the SQL endpoint asking to be called less often.

    Matched on the response where one is attached and on the text otherwise,
    because the exception arrives through the MCP client rather than from an
    HTTP call this code made, and its type is not guaranteed.

    Recursive because the MCP client runs its transport in a task group, so the
    429 arrives wrapped: `str()` on the group is "unhandled errors in a
    TaskGroup (1 sub-exception)" and says nothing about the status. Matching
    only the outer layer is why the first version of this never fired.
    """
    if depth > 3:
        return False
    if getattr(getattr(exc, "response", None), "status_code", None) == 429:
        return True
    if "429" in str(exc):
        return True
    for inner in (*(getattr(exc, "exceptions", None) or ()), exc.__cause__):
        if inner is not None and _is_rate_limited(inner, depth + 1):
            return True
    return False


def build_middlewares(flag_pii: bool, flag_tool_retries: bool) -> list[Any]:
    middlewares: list[Any] = [TodoListMiddleware()]
    if flag_pii:
        middlewares.append(
            PIIMiddleware(
                "email",
                strategy="mask",
                detector=EMAIL_PATTERN,
                apply_to_input=True,
                apply_to_output=True,
                apply_to_tool_results=True,
            )
        )
    if flag_tool_retries:
        middlewares.append(
            ToolRetryMiddleware(
                max_retries=3,
                retry_on=_is_rate_limited,
                initial_delay=1.0,
                backoff_factor=2.0,
                jitter=False,
            )
        )
    return middlewares
