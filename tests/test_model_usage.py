"""Token usage is reported once per run, not once per chunk.

`databricks_langchain` 0.20.0 attaches cumulative usage to every streamed chunk,
so anything summing them inflates the total — measured at 70x live. These use
synthetic chunks, so they pin the accounting without a workspace.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGenerationChunk

from agent_server.model import UsageCorrectedChatDatabricks, UsageRelay, build_model


def _chunk(text: str, out: int | None = None) -> ChatGenerationChunk:
    """A chunk carrying cumulative usage, the way 0.20.0 emits them."""
    usage = None if out is None else {"input_tokens": 23, "output_tokens": out,
                                      "total_tokens": 23 + out}
    return ChatGenerationChunk(message=AIMessageChunk(content=text, usage_metadata=usage))


# The shape the bug produces: totals restated and growing on every chunk.
CUMULATIVE = [_chunk("a", 1), _chunk("b", 2), _chunk("c", 3), _chunk("d", 4)]


def test_the_relay_strips_usage_from_every_chunk():
    relay = UsageRelay()
    stripped = [relay.strip(c) for c in CUMULATIVE]
    assert all(c.message.usage_metadata is None for c in stripped)


def test_the_relay_keeps_the_last_figures_not_their_sum():
    """The values are already cumulative, so the final chunk holds the run's
    totals. Adding them here would reproduce the bug on the other side of the
    fix."""
    relay = UsageRelay()
    for c in CUMULATIVE:
        relay.strip(c)
    assert relay.tail().message.usage_metadata == {
        "input_tokens": 23, "output_tokens": 4, "total_tokens": 27}


def test_the_content_survives_stripping():
    """Only the accounting is removed. Losing a token of text to fix a token
    count would be a worse bug than the one being fixed."""
    relay = UsageRelay()
    assert "".join(relay.strip(c).message.content for c in CUMULATIVE) == "abcd"


def test_a_stream_with_no_usage_gains_none():
    """A run that reported nothing must not acquire an empty usage record —
    zero tokens stated as a fact is worse than an absence."""
    relay = UsageRelay()
    for c in [_chunk("a"), _chunk("b")]:
        relay.strip(c)
    assert relay.tail() is None


def test_a_non_message_chunk_passes_through_untouched():
    relay = UsageRelay()
    chunk = ChatGenerationChunk(message=AIMessageChunk(content="x"))
    assert relay.strip(chunk) is chunk


def test_generation_info_is_preserved():
    """`generation_info` carries the finish reason, which the caller reads."""
    relay = UsageRelay()
    chunk = ChatGenerationChunk(
        message=AIMessageChunk(content="x", usage_metadata={"input_tokens": 1, "output_tokens": 1,
                                                           "total_tokens": 2}),
        generation_info={"finish_reason": "stop"})
    assert relay.strip(chunk).generation_info == {"finish_reason": "stop"}


# ── the model class wires both streams ───────────────────────────────────────


def _relayed(chunks):
    """What the model's override does to a parent stream."""
    relay = UsageRelay()
    out = [relay.strip(c) for c in chunks]
    if (tail := relay.tail()) is not None:
        out.append(tail)
    return out


def test_exactly_one_chunk_carries_usage_after_the_relay():
    out = _relayed(CUMULATIVE)
    carrying = [c for c in out if c.message.usage_metadata is not None]
    assert len(carrying) == 1
    assert carrying[0] is out[-1], "the totals must arrive last, after the text"


def test_a_summing_consumer_now_gets_the_truth():
    """The property the fix exists for, stated as the consumer sees it."""
    naive_before = sum(c.message.usage_metadata["total_tokens"] for c in CUMULATIVE)
    out = _relayed(CUMULATIVE)
    naive_after = sum(c.message.usage_metadata["total_tokens"]
                      for c in out if c.message.usage_metadata)
    true_total = CUMULATIVE[-1].message.usage_metadata["total_tokens"]
    # 24 + 25 + 26 + 27: each chunk restates the running total, so a consumer
    # that adds them reports nearly four times a 27-token run.
    assert naive_before == 102, "the bug being fixed"
    assert naive_after == true_total == 27


def test_both_stream_paths_are_overridden():
    """The agent streams asynchronously; overriding only `_stream` would leave
    the served path unfixed while every local test passed."""
    for name in ("_stream", "_astream"):
        assert name in vars(UsageCorrectedChatDatabricks), f"{name} is not overridden"


def test_build_model_returns_the_corrected_class():
    assert isinstance(build_model("some-endpoint"), UsageCorrectedChatDatabricks)


def test_the_agent_is_built_with_it():
    """A correct model class that the composition root does not use is no fix."""
    import inspect

    from agent_server import agent

    assert "build_model(MODEL_ENDPOINT)" in inspect.getsource(agent.init_agent)


# ── per-endpoint quirks ──────────────────────────────────────────────────────
# Two endpoints refuse a payload the others accept, for unrelated reasons. Both
# were found by running the real agent against all five models, and both fail
# on the first tool call — so neither shows up in a conversation without tools.


def test_tool_result_block_ids_are_stripped():
    """LangChain tags each content block with `id="lc_<uuid>"`, and
    Anthropic-shaped endpoints answer `400 … text.id: Extra inputs are not
    permitted`. Nothing downstream reads the id."""
    from langchain_core.messages import ToolMessage

    from agent_server.model import _strip_block_ids

    msg = ToolMessage(content=[{"type": "text", "text": "rows", "id": "lc_abc"}],
                      tool_call_id="c1", name="execute_sql_read_only")
    assert _strip_block_ids([msg])[0].content == [{"type": "text", "text": "rows"}]


def test_stripping_does_not_mutate_graph_state():
    """The messages belong to the checkpoint a resumed run reads back, so this
    copies rather than edits in place."""
    from langchain_core.messages import ToolMessage

    from agent_server.model import _strip_block_ids

    msg = ToolMessage(content=[{"type": "text", "text": "rows", "id": "lc_abc"}],
                      tool_call_id="c1", name="execute_sql_read_only")
    _strip_block_ids([msg])
    assert msg.content[0]["id"] == "lc_abc"


def test_a_string_tool_result_is_left_alone():
    """Most results are plain strings; only the block form carries ids."""
    from langchain_core.messages import ToolMessage

    from agent_server.model import _strip_block_ids

    msg = ToolMessage(content="rows", tool_call_id="c1", name="t")
    assert _strip_block_ids([msg])[0].content == "rows"


def test_reasoning_effort_is_sent_only_where_it_is_needed():
    """`gpt-5-6-sol` refuses function tools while a reasoning effort is set and
    sets one by default. glm-5-3-flash, claude-opus-5 and grok-4-6 all reject
    the parameter outright, so it cannot be sent globally."""
    from agent_server.model import build_model

    assert build_model("databricks-gpt-5-6-sol").extra_params == {"reasoning_effort": "none"}
    for other in ("databricks-glm-5-3-flash", "databricks-claude-opus-5",
                  "databricks-grok-4-6", "databricks-kimi-k3"):
        assert build_model(other).extra_params == {}, other
