"""The chat model, and the three endpoint quirks it works around.

1. `databricks_langchain` 0.20.0 attaches cumulative usage to every streamed
   chunk — measured at 29.5x the truth on a 405-token run.
2. LangChain tags tool-result blocks with an internal `id` that Anthropic-shaped
   endpoints reject outright.
3. `gpt-5-6-sol` defaults to a reasoning effort its own endpoint refuses to
   combine with function tools.

Workarounds with a version attached, not a design. Verified against
glm-5-3-flash, kimi-k3, claude-opus-5, gpt-5-6-sol and grok-4-6.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Iterator

from databricks_langchain import ChatDatabricks
from langchain_core.messages import AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk

logger = logging.getLogger(__name__)


class UsageRelay:
    """Strips cumulative usage from every chunk, re-emitting only the total.

    Apart from the model class because the sync and async streams differ only in
    how they iterate.
    """

    def __init__(self) -> None:
        self._last = None

    def strip(self, chunk: ChatGenerationChunk) -> ChatGenerationChunk:
        """The chunk with usage removed, remembering what was removed."""
        msg = chunk.message
        if not isinstance(msg, AIMessageChunk) or msg.usage_metadata is None:
            return chunk
        # Last wins, not sum: the values are already cumulative, so adding them
        # would reproduce the bug on the other side of the fix.
        self._last = msg.usage_metadata
        return ChatGenerationChunk(
            message=msg.model_copy(update={"usage_metadata": None}),
            generation_info=chunk.generation_info,
        )

    def tail(self) -> ChatGenerationChunk | None:
        """The one trailing chunk carrying the totals, or None if none were seen.

        None rather than zeros, so a stream that reported nothing does not gain
        a usage record stating zero tokens as a fact.
        """
        if self._last is None:
            return None
        return ChatGenerationChunk(
            message=AIMessageChunk(content="", usage_metadata=self._last),
            generation_info=None,
        )


class UsageCorrectedChatDatabricks(ChatDatabricks):
    """`ChatDatabricks` that reports each run's tokens once instead of per chunk."""

    def _stream(self, messages, stop=None, run_manager=None, **kwargs) -> Iterator[ChatGenerationChunk]:
        relay = UsageRelay()
        for chunk in super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs):
            yield relay.strip(chunk)
        if (tail := relay.tail()) is not None:
            yield tail

    async def _astream(
        self, messages, stop=None, run_manager=None, **kwargs
    ) -> AsyncIterator[ChatGenerationChunk]:
        relay = UsageRelay()
        async for chunk in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
            yield relay.strip(chunk)
        if (tail := relay.tail()) is not None:
            yield tail


def _strip_block_ids(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Tool results without LangChain's internal block `id`.

    Anthropic-shaped endpoints validate `tool_result.content` strictly and answer
    `400 … text.id: Extra inputs are not permitted`, killing the run on its first
    tool call. The id is LangChain bookkeeping nothing downstream reads.

    Copies rather than mutates, since the messages belong to graph state.
    """
    out: list[BaseMessage] = []
    for message in messages:
        if isinstance(message, ToolMessage) and isinstance(message.content, list):
            blocks = [
                {k: v for k, v in block.items() if k != "id"} if isinstance(block, dict) else block
                for block in message.content
            ]
            if blocks != message.content:
                message = message.model_copy(update={"content": blocks})
        out.append(message)
    return out


class _StripsBlockIds(UsageCorrectedChatDatabricks):
    """Removes the block ids on the way out, for endpoints that refuse them."""

    def _prepare_inputs(self, messages, *args, **kwargs):  # type: ignore[override]
        return super()._prepare_inputs(_strip_block_ids(list(messages)), *args, **kwargs)


NEEDS_REASONING_EFFORT_NONE = ("gpt-5-6-sol",)


def build_model(endpoint: str) -> ChatDatabricks:
    """The chat model the agent is built with, with per-endpoint quirks applied."""
    extra: dict = {}
    if any(name in endpoint for name in NEEDS_REASONING_EFFORT_NONE):
        extra["reasoning_effort"] = "none"
    return _StripsBlockIds(endpoint=endpoint, extra_params=extra)
