"""The middleware stack, and the two judgements it needs to make.

Both flags are for the evaluation harness rather than for serving: a scored run
that keeps the PII net measures the net, and one that retries a rate limit
measures the retry.
"""

import logging
from typing import Any

from langchain.agents.middleware import (
    PIIMiddleware,
    SummarizationMiddleware,
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


# Measured against every model this workshop may be pointed at:
# glm-5-3-flash, kimi-k3, claude-opus-5, gpt-5-6-sol and grok-4-6. Each was sent
# a ~200,000-token prompt with a marker at the front and asked to repeat it;
# all five recalled it, so none is silently dropping the head of the
# conversation at this size.
#
# The trigger counts with `count_tokens_approximately`, which sees neither the
# system prompt (~3,100 tokens) nor the skill files the filesystem middleware
# injects (~2,600) — fixed overhead, so real input is this number plus roughly
# six thousand.
#
# One analytical turn is ~8,500 counted tokens, so this is a **safety net rather
# than a working compactor**: about twenty turns pass before it fires. That is
# the intent — summarising discards tool results the next answer may need, and
# these models hold the context comfortably. Lower it toward 20,000 if the cost
# of resending a long history matters more than keeping it.
#
# A `("fraction", …)` trigger would follow the model instead of being pinned,
# but it raises `ValueError` without a model profile and these endpoints ship
# none.
SUMMARY_TRIGGER_TOKENS = 200_000
SUMMARY_KEEP_MESSAGES = 12


def build_middlewares(
    flag_pii: bool,
    flag_tool_retries: bool,
    flag_summarize: bool = True,
) -> list[Any]:
    """The middleware stack for one agent."""
    from agent_server.agent import MODEL_ENDPOINT
    from agent_server.model import build_model

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
    if flag_summarize:
        middlewares.append(
            SummarizationMiddleware(
                model=build_model(MODEL_ENDPOINT),
                trigger=("tokens", SUMMARY_TRIGGER_TOKENS),
                keep=("messages", SUMMARY_KEEP_MESSAGES),
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
