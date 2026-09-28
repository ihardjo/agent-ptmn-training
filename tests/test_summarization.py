"""Compacting the conversation before it gets expensive.

Every model call resends the whole history and a turn makes roughly ten of
them, so an unbounded conversation costs quadratically. The endpoint accepted a
200,000-token prompt, so the context window is not what this guards — cost and
latency are.
"""

from __future__ import annotations

import pytest
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent_server.middleware import (
    SUMMARY_KEEP_MESSAGES,
    SUMMARY_TRIGGER_TOKENS,
    build_middlewares,
)


class _FakeModel(GenericFakeChatModel):
    """A real chat model with a canned reply, so the middleware constructs.

    A bare stub is not enough: the middleware calls `with_retry()` and reads
    `_llm_type`, so it needs the actual interface rather than two methods.
    """

    def __init__(self):
        super().__init__(messages=iter([AIMessage(content="summary")]))


def _stack(**kw):
    return [type(m).__name__ for m in build_middlewares(True, True, **kw)]


def test_summarization_is_in_the_stack_when_a_model_is_given():
    assert "SummarizationMiddleware" in _stack()


def test_it_can_be_switched_off():
    """The evaluation harness runs without it: a scored run that compacts its
    own history measures the compaction as much as the agent."""
    assert "SummarizationMiddleware" not in _stack(flag_summarize=False)


def test_it_runs_after_the_pii_net():
    """Order matters. The summariser makes its own model call over the history,
    so it must see what `PIIMiddleware` has already masked rather than the raw
    tool results."""
    stack = _stack()
    assert stack.index("PIIMiddleware") < stack.index("SummarizationMiddleware")


def test_the_trigger_is_an_absolute_token_count():
    """`("fraction", …)` would follow the model, but it raises `ValueError`
    without a model profile and this endpoint ships none — verified against the
    live endpoint, not assumed."""
    assert isinstance(SUMMARY_TRIGGER_TOKENS, int)
    m = SummarizationMiddleware(
        model=_FakeModel(), trigger=("tokens", SUMMARY_TRIGGER_TOKENS),
        keep=("messages", SUMMARY_KEEP_MESSAGES),
    )
    assert m is not None


def test_the_threshold_clears_a_single_turn():
    """One analytical turn measured 8,505 tokens by the counter the trigger
    uses. A threshold below that would summarise inside every turn, throwing
    away the tool results the answer is being built from."""
    assert SUMMARY_TRIGGER_TOKENS > 8_505 * 2, (
        "the trigger must leave room for at least two full turns"
    )


def test_what_is_kept_is_smaller_than_a_turn():
    """A turn is ~28 messages. Keeping 20 (the default) would retain little more
    than the turn that just ended, which is the part the summary already covers."""
    assert SUMMARY_KEEP_MESSAGES < 28


def test_the_summariser_goes_through_build_model():
    """Not a bare `ChatDatabricks`: the per-endpoint fixes in `model.py` — the
    usage relay, the stripped block ids, `reasoning_effort` — have to apply to
    the summary call as well. The import is deferred because `agent.py` imports
    this module."""
    import inspect

    from agent_server import middleware as mw

    src = inspect.getsource(mw.build_middlewares)
    assert "build_model(MODEL_ENDPOINT)" in src
    assert "from agent_server.model import build_model" in src
