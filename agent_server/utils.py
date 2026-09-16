import json
import logging
import uuid
from typing import Any, AsyncGenerator, AsyncIterator

from databricks.sdk import WorkspaceClient
from langchain.messages import AIMessage, ToolMessage
from mlflow.types.responses import (
    ResponseOutputItemDoneEvent,
    create_function_call_item,
    create_function_call_output_item,
    create_reasoning_item,
    create_text_delta,
    create_text_output_item,
)

logger = logging.getLogger(__name__)

TEXT = "text"
REASONING = "reasoning"
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"


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


def error_chunk(message: str) -> str:
    """Report a mid-stream failure, which otherwise just closes the connection.

    Valid on both routes: the chat UI's provider renders it, and it is the shape
    MLflow's own agent server uses.
    """
    return _sse({"error": message})


# ── LangGraph output → renderable parts ───────────────────────────────────────


def _reasoning_text(block: dict) -> str:
    """Thought text from a reasoning block.

    LangChain's standard block holds it under `reasoning`; Databricks models like
    gpt-oss arrive as the raw Responses item, carrying a `summary` list instead.
    """
    if isinstance(block.get("reasoning"), str):
        return block["reasoning"]
    return "".join(part.get("text", "") for part in block.get("summary") or [])


def _content_parts(message: AIMessage) -> list[tuple[str, str]]:
    """Split a message's content into (TEXT | REASONING, chunk) pairs.

    Reasoning models return `content` as a list of blocks that interleaves thought
    with answer. Passing it through whole puts the raw list on the wire, where the
    UI renders it as a JSON blob with the chain of thought inside.
    """
    if isinstance(message.content, str):
        return [(TEXT, message.content)] if message.content else []
    parts = []
    for block in message.content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == TEXT and (text := block.get("text")):
            parts.append((TEXT, text))
        elif block.get("type") == REASONING and (thought := _reasoning_text(block)):
            parts.append((REASONING, thought))
    return parts


async def _iter_message_parts(async_stream: AsyncIterator[Any]) -> AsyncGenerator[tuple[str, Any], None]:
    """Yield (kind, payload) for everything the UI can render, in arrival order.

    Both stream modes earn their place. `messages` streams content token by token,
    so text and reasoning come from there. `updates` fires once per node with the
    finished message, so tool calls come from there — on `messages` their arguments
    arrive as partial JSON fragments, unusable until reassembled.

    Payload is a str for TEXT and REASONING, a message for TOOL_RESULT, and a
    LangChain tool call for TOOL_CALL.
    """
    async for mode, payload in async_stream:
        if mode == "messages":
            message = payload[0]
            if isinstance(message, AIMessage):
                for part in _content_parts(message):
                    yield part
        elif mode == "updates":
            # A node returning nothing shows up as {node: None}, an interrupt puts
            # a tuple here instead of a state update.
            for update in payload.values():
                if not isinstance(update, dict):
                    continue
                for message in update.get("messages", []):
                    if isinstance(message, ToolMessage):
                        yield TOOL_RESULT, message
                    elif isinstance(message, AIMessage):
                        # Content already streamed via `messages`; calls did not.
                        for call in message.tool_calls:
                            yield TOOL_CALL, call


# ── Responses API (/invocations) ──────────────────────────────────────────────


def _item_done(item: dict) -> dict:
    """Wrap a completed output item, validating its shape on the way out."""
    return ResponseOutputItemDoneEvent(
        type="response.output_item.done", item=item
    ).model_dump(exclude_none=True)


def _run_item_id(item_id: str, kind: str, run: int) -> str:
    """Id for one uninterrupted run of text or reasoning.

    The provider starts a new part whenever the id changes, which is what keeps a
    thought from before a tool call separate from the one after it.
    """
    return f"{item_id}-{kind}-{run}"


async def _iter_responses_api_events(
    async_stream: AsyncIterator[Any],
    item_id: str,
) -> AsyncGenerator[dict, None]:
    """Convert LangGraph output to Responses API events, in arrival order.

    One event type per renderable thing: thoughts stream on
    `response.reasoning_summary_text.delta` (the UI's collapsible "Thinking..."
    block), the answer on `response.output_text.delta`, and tool calls and results
    as `function_call` / `function_call_output` items (the tool cards). Each run
    also closes with an `output_item.done`, which the provider de-duplicates
    against the deltas and which is all `collect_response_output` needs.

    No `responses.completed` is sent. It is the only carrier for token usage, but
    it also sets the finish reason, and the provider maps a completed response
    holding tool calls to `tool-calls` — claiming the client still owes tool
    results. This agent finished its own loop, so `stop` is the truthful answer and
    the token counts are the price.
    """
    run = 0
    open_kind: str | None = None
    buffered: list[str] = []

    def close_run() -> dict | None:
        """Flush the open text/reasoning run as a completed output item."""
        nonlocal buffered
        body, buffered = "".join(buffered), []
        if not body:
            return None
        run_id = _run_item_id(item_id, open_kind, run)
        return _item_done(
            create_text_output_item(text=body, id=run_id)
            if open_kind == TEXT
            else create_reasoning_item(id=run_id, reasoning_text=body)
        )

    async for kind, payload in _iter_message_parts(async_stream):
        if kind in (TEXT, REASONING):
            if kind != open_kind:
                if done := close_run():
                    yield done
                run += 1
                open_kind = kind
            buffered.append(payload)
            run_id = _run_item_id(item_id, kind, run)
            yield (
                create_text_delta(payload, item_id=run_id)
                if kind == TEXT
                # MLflow has no factory for a reasoning delta. Without it a thought
                # only appears once its turn is over, instead of streaming in.
                else {
                    "type": "response.reasoning_summary_text.delta",
                    "item_id": run_id,
                    "summary_index": 0,
                    "delta": payload,
                }
            )
            continue

        if done := close_run():
            yield done
        open_kind = None
        yield _item_done(
            create_function_call_item(
                # The provider learns a call's name only from this item, so it has
                # to precede the output or the card reads "unknown" and the provider
                # raises on a result it cannot pair. `arguments` is a JSON string.
                id=f"fc-{payload['id']}",
                call_id=payload["id"],
                name=payload["name"],
                arguments=json.dumps(payload["args"]),
            )
            if kind == TOOL_CALL
            else create_function_call_output_item(
                call_id=payload.tool_call_id,
                output=normalize_content(payload.content),
            )
        )

    if done := close_run():
        yield done


async def stream_to_responses_api_chunks(
    async_stream: AsyncIterator[Any],
    item_id: str,
) -> AsyncGenerator[str, None]:
    """SSE-frame the Responses API events for the ai-sdk-provider responses() client."""
    async for event in _iter_responses_api_events(async_stream, item_id):
        yield _sse(event)


async def collect_response_output(async_stream: AsyncIterator[Any], item_id: str) -> list[dict]:
    """The `output` list for a non-streaming response.

    Built from the completed items of the streaming path so the two cannot drift.
    """
    return [
        event["item"]
        async for event in _iter_responses_api_events(async_stream, item_id)
        if event["type"] == "response.output_item.done"
    ]


# ── OpenAI Chat Completions (/v1/chat/completions) ────────────────────────────


def _chat_chunk(completion_id: str, model: str, delta: dict, finish_reason=None) -> str:
    return _sse({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    })


async def stream_to_chat_completions_chunks(
    async_stream: AsyncIterator[Any],
    completion_id: str,
    model: str = "agent",
) -> AsyncGenerator[str, None]:
    """Emit Chat Completions SSE chunks.

    Tool activity is dropped rather than mapped: `delta.tool_calls` asks the client
    to run the tools and call back, which is wrong for an agent that runs its own
    loop. Callers that want the tool steps use /invocations.
    """
    yield _chat_chunk(completion_id, model, {"role": "assistant", "content": ""})
    async for kind, payload in _iter_message_parts(async_stream):
        if kind == TEXT:
            yield _chat_chunk(completion_id, model, {"content": payload})
        elif kind == REASONING:
            # `reasoning_content` is the de facto OpenAI-compatible field for
            # thoughts (Databricks FMAPI, vLLM, DeepSeek); others ignore the key.
            yield _chat_chunk(completion_id, model, {"reasoning_content": payload})
    yield _chat_chunk(completion_id, model, {}, finish_reason="stop")
    yield "data: [DONE]\n\n"


async def collect_message_parts(async_stream: AsyncIterator[Any]) -> tuple[str, str]:
    """(answer, thought) for a non-streaming chat completion."""
    text: list[str] = []
    thoughts: list[str] = []
    async for kind, payload in _iter_message_parts(async_stream):
        if kind == TEXT:
            text.append(payload)
        elif kind == REASONING:
            thoughts.append(payload)
    return "".join(text), "".join(thoughts)
