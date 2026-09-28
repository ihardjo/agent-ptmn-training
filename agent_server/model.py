"""The chat model, and the streaming-usage bug it works around.

`databricks_langchain` 0.20.0 attaches cumulative usage to every streamed chunk,
so a consumer that sums them reports a multiple of the truth — measured at 29.5x
on a 405-token run. Remove this once the package emits usage only on the last
chunk.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Iterator

from databricks_langchain import ChatDatabricks
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

logger = logging.getLogger(__name__)


class UsageRelay:
    """Strips cumulative usage from every chunk and re-emits only the final total.

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

        None rather than zeros: a stream that reported nothing must not gain a
        usage record stating zero tokens as a fact.
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


def build_model(endpoint: str) -> ChatDatabricks:
    """The chat model the agent is built with."""
    return UsageCorrectedChatDatabricks(endpoint=endpoint)
