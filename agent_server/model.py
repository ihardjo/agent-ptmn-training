"""The chat model, and the streaming-usage bug it has to work around.

`databricks_langchain` 0.20.0 attaches **cumulative** usage metadata to every
streamed chunk rather than to the last one. Each chunk restates the running
totals, so a consumer that accumulates usage across a stream — Langfuse, a cost
dashboard, anything summing `usage_metadata` — adds the same tokens once per
chunk and reports a multiple of the truth.

Measured against `databricks-glm-5-3-flash`: a fifteen-line answer arrived as 57
chunks, 56 of them carrying usage. The true total was 405 tokens; summing every
chunk gives 11,953, an inflation of **29.5x**. The input count is worse in kind
than in size — 23 input tokens restated 56 times — because it makes a short
prompt look like a context-window problem.

**The failure is silent and it points the wrong way.** Nothing errors; a number
is simply wrong, and wrong in the direction that makes the agent look
expensive. Acting on it means optimising a prompt that was never the cost.

The fix is to make the stream say once what it currently says continuously:
strip usage from every chunk, keep the last one, and emit a single trailing
chunk carrying the totals. Ported from the `brd-deep-agent` repo, which hit the
same bug on the same version.

Remove this when `databricks_langchain` emits usage only on the final chunk —
`UsageRelay` is a workaround with a version attached, not a design.
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

    Held apart from the model class because the sync and async streams differ
    only in how they iterate, and the accounting they would otherwise duplicate
    is the part worth getting right once.
    """

    def __init__(self) -> None:
        self._last = None

    def strip(self, chunk: ChatGenerationChunk) -> ChatGenerationChunk:
        """The chunk with usage removed, remembering what was removed."""
        msg = chunk.message
        if not isinstance(msg, AIMessageChunk) or msg.usage_metadata is None:
            return chunk
        # Last wins rather than accumulating: the values are already cumulative,
        # so the final chunk's figures are the run's totals. Summing them here
        # would reproduce the bug on the other side of the fix.
        self._last = msg.usage_metadata
        return ChatGenerationChunk(
            message=msg.model_copy(update={"usage_metadata": None}),
            generation_info=chunk.generation_info,
        )

    def tail(self) -> ChatGenerationChunk | None:
        """The one trailing chunk carrying the totals, or None if none were seen.

        None matters: a stream that carried no usage at all must not gain an
        empty usage record, which would report zero tokens as a fact rather
        than as an absence.
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
