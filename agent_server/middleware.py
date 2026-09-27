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
    wrap_tool_call,
)

logger = logging.getLogger(__name__)

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


@wrap_tool_call
async def flatten_tool_result_blocks(request, handler):
    """Return a tool result as text rather than as content blocks.

    `langchain-mcp-adapters` returns `[{"type": "text", "text": ..., "id": "lc_..."}]`.
    Most endpoints ignore the extra `id`; the Anthropic-backed ones reject the
    whole turn over it. Joining here is what keeps `MODEL_ENDPOINT` a one-line
    switch, and costs nothing on the endpoints that tolerated the blocks.
    """
    response = await handler(request)
    content = getattr(response, "content", None)
    if isinstance(content, list):
        response.content = "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return response


def build_middlewares(flag_pii: bool, flag_tool_retries: bool) -> list[Any]:
    middlewares: list[Any] = [TodoListMiddleware(), flatten_tool_result_blocks]
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
