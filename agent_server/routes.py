import logging
import os
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langfuse.langchain import CallbackHandler

from agent_server.agent import init_agent
from agent_server.models import (
    AssistantMessage,
    ChatCompletionChoice,
    ChatCompletionResponse,
    ChatRequest,
    conversation_turns,
)
from agent_server.utils import (
    collect_message_parts,
    collect_response_output,
    error_chunk,
    new_completion_id,
    normalize_content,
    stream_to_chat_completions_chunks,
    stream_to_responses_api_chunks,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def trace_config(session_id: str | None = None) -> dict:
    """Langfuse callbacks for one run, or an empty config when no host is set.

    The host has to be the gate, and it has to be read here: `CallbackHandler`
    takes no host argument, and an unset host resolves to cloud.langfuse.com
    inside the SDK — so keys left in place with the host dropped would ship
    prompts and tool output to a third-party SaaS instead of failing. Missing keys
    need no branch; the SDK disables itself. LANGFUSE_BASE_URL wins, as in the SDK.
    """
    host = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST")
    if not host:
        logger.info("No LANGFUSE_HOST — this run will not be traced.")
        return {}
    config: dict = {"callbacks": [CallbackHandler()]}
    if session_id:
        config["metadata"] = {"langfuse_session_id": session_id}
    return config


def agent_stream(agent: Any, messages: list, session_id: str | None):
    """The agent's event stream for one request."""
    return agent.astream(
        input={"messages": [{"role": m.role, "content": normalize_content(m.content)} for m in messages]},
        stream_mode=["updates", "messages"],
        config=trace_config(session_id),
    )


def sse_response(chunks: AsyncGenerator[str, None]) -> StreamingResponse:
    """Serve SSE, reporting a mid-stream failure in the stream itself.

    Once the response has started the status code is spent, so an error event is
    the only way left to tell the caller.
    """
    async def guarded():
        try:
            async for chunk in chunks:
                yield chunk
        except Exception as e:
            logger.exception("Agent stream failed")
            yield error_chunk(str(e))

    return StreamingResponse(guarded(), media_type="text/event-stream")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatRequest, http_request: Request):
    session_id = http_request.headers.get("X-Session-Id")
    agent = await init_agent()
    stream = agent_stream(agent, request.messages, session_id)
    completion_id = new_completion_id()

    if request.stream:
        return sse_response(
            stream_to_chat_completions_chunks(stream, completion_id=completion_id, model=request.model)
        )

    content, reasoning = await collect_message_parts(stream)
    return ChatCompletionResponse(
        id=completion_id,
        object="chat.completion",
        model=request.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=AssistantMessage(
                    role="assistant", content=content, reasoning_content=reasoning or None
                ),
                finish_reason="stop",
            )
        ],
    )


@router.post("/invocations")
async def invocations_compat(body: dict, http_request: Request):
    """Handle requests from the React chat UI, which speaks the OpenAI Responses API.

    The Databricks ai-sdk-provider responses() client sends `input` as a list of
    messages and expects Responses SSE events back.
    """
    session_id = http_request.headers.get("X-Session-Id") or body.get("context", {}).get("conversation_id")
    agent = await init_agent()
    stream = agent_stream(agent, conversation_turns(body.get("input", [])), session_id)
    item_id = new_completion_id()

    if body.get("stream", False):
        return sse_response(stream_to_responses_api_chunks(stream, item_id=item_id))

    return {"output": await collect_response_output(stream, item_id=item_id)}
