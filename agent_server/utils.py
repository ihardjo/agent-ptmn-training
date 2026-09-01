import json
import logging
import uuid
from typing import Any, AsyncGenerator, AsyncIterator, Optional

from databricks.sdk import WorkspaceClient
from langchain.messages import AIMessageChunk, ToolMessage

logger = logging.getLogger(__name__)


def get_databricks_host_from_env() -> Optional[str]:
    try:
        w = WorkspaceClient()
        return w.config.host
    except Exception as e:
        logging.exception(f"Error getting databricks host from env: {e}")
        return None


def get_user_workspace_client(token: str) -> WorkspaceClient:
    return WorkspaceClient(token=token, auth_type="pat")


def new_completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def _sse_chunk(completion_id: str, model: str, delta: dict, finish_reason=None) -> str:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload)}\n\n"


async def stream_to_chat_completions_chunks(
    async_stream: AsyncIterator[Any],
    completion_id: str,
    model: str = "agent",
) -> AsyncGenerator[str, None]:
    yield _sse_chunk(completion_id, model, {"role": "assistant", "content": ""})

    async for event in async_stream:
        event_type, event_data = event[0], event[1]

        if event_type == "messages":
            try:
                chunk = event_data[0]
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    yield _sse_chunk(completion_id, model, {"content": chunk.content})
            except Exception as e:
                logger.exception(f"Error processing message chunk: {e}")

        elif event_type == "updates":
            for node_data in event_data.values():
                for msg in node_data.get("messages", []):
                    if isinstance(msg, ToolMessage):
                        content = (
                            msg.content
                            if isinstance(msg.content, str)
                            else json.dumps(msg.content)
                        )
                        logger.debug(f"Tool result from {msg.tool_call_id}: {content[:100]}")

    yield _sse_chunk(completion_id, model, {}, finish_reason="stop")
    yield "data: [DONE]\n\n"


async def collect_chat_completion_content(
    async_stream: AsyncIterator[Any],
) -> str:
    parts = []
    async for event in async_stream:
        event_type, event_data = event[0], event[1]
        if event_type == "messages":
            try:
                chunk = event_data[0]
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    parts.append(chunk.content)
            except Exception as e:
                logger.exception(f"Error collecting message chunk: {e}")
    return "".join(parts)
