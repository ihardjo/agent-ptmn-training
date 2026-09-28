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

EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"


def _is_rate_limited(exc: BaseException, depth: int = 0) -> bool:
    """Whether this failure is the SQL endpoint asking to be called less often.

    Matched on the response where one is attached and on the text otherwise,
    since the exception arrives through the MCP client and its type is not
    guaranteed. Recursive because the transport runs in a task group, so the 429
    arrives wrapped — matching only the outer layer is why the first version
    never fired.
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
                strategy="redact",
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
