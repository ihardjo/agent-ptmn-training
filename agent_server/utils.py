import json
import logging
import uuid
from typing import Any, AsyncGenerator, AsyncIterator

from databricks.sdk import WorkspaceClient
from langchain.messages import AIMessageChunk

logger = logging.getLogger(__name__)


def get_databricks_host_from_env() -> str | None:
    try:
        return WorkspaceClient().config.host
    except Exception as e:
        logger.exception(f"Error getting Databricks host from env: {e}")
        return None


def new_completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def normalize_content(content: str | list | None) -> str | None:
    """Flatten Responses API content parts (type: input_text) to a plain string."""
    if not isinstance(content, list):
        return content
    return "".join(
        part.get("text", "") if isinstance(part, dict) else str(part)
        for part in content
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _chat_chunk(completion_id: str, model: str, delta: dict, finish_reason=None) -> str:
    return _sse({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    })


async def _iter_text_chunks(async_stream: AsyncIterator[Any]) -> AsyncGenerator[str, None]:
    """Yield raw text strings from LangGraph astream 'messages' events."""
    async for event in async_stream:
        if event[0] == "messages" and event[1]:
            chunk = event[1][0]
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                yield chunk.content


async def stream_to_chat_completions_chunks(
    async_stream: AsyncIterator[Any],
    completion_id: str,
    model: str = "agent",
) -> AsyncGenerator[str, None]:
    yield _chat_chunk(completion_id, model, {"role": "assistant", "content": ""})
    async for text in _iter_text_chunks(async_stream):
        yield _chat_chunk(completion_id, model, {"content": text})
    yield _chat_chunk(completion_id, model, {}, finish_reason="stop")
    yield "data: [DONE]\n\n"


async def stream_to_responses_api_chunks(
    async_stream: AsyncIterator[Any],
    item_id: str,
) -> AsyncGenerator[str, None]:
    """Emit Responses API SSE events consumed by the Databricks ai-sdk-provider responses() client."""
    parts: list[str] = []
    async for text in _iter_text_chunks(async_stream):
        parts.append(text)
        yield _sse({"type": "response.output_text.delta", "item_id": item_id, "delta": text})
    yield _sse({
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "type": "message",
            "id": item_id,
            "role": "assistant",
            "content": [{"type": "output_text", "text": "".join(parts)}],
        },
    })


async def collect_chat_completion_content(async_stream: AsyncIterator[Any]) -> str:
    parts: list[str] = []
    async for text in _iter_text_chunks(async_stream):
        parts.append(text)
    return "".join(parts)
