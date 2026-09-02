import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langfuse.langchain import CallbackHandler

from agent_server.agent import init_agent
from agent_server.models import (
    AssistantMessage,
    ChatCompletionChoice,
    ChatCompletionResponse,
    ChatMessage,
    ChatRequest,
)
from agent_server.utils import (
    collect_chat_completion_content,
    new_completion_id,
    normalize_content,
    stream_to_chat_completions_chunks,
    stream_to_responses_api_chunks,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def trace_config(session_id: str | None = None) -> dict:
    """Langfuse callbacks for one run, or an empty config when no host is set.

    The gate is the host, and it has to live here: `CallbackHandler` accepts no
    host argument, so the environment is the only place the decision can be made,
    and an unset host resolves to https://cloud.langfuse.com inside the SDK. Keys
    left in place while the host is dropped would therefore ship prompts and tool
    output to a third-party SaaS rather than fail — the opposite of what pointing
    at a self-hosted instance is for. LANGFUSE_BASE_URL wins over LANGFUSE_HOST,
    matching the SDK's own precedence.

    Missing keys get no branch: the SDK logs and disables the client itself.
    """
    host = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST")
    if not host:
        logger.info("No LANGFUSE_HOST — this run will not be traced.")
        return {}
    config: dict = {"callbacks": [CallbackHandler()]}
    if session_id:
        config["metadata"] = {"langfuse_session_id": session_id}
    return config


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatRequest, http_request: Request):
    session_id = http_request.headers.get("X-Session-Id")
    agent = await init_agent()
    messages = {"messages": [{"role": m.role, "content": normalize_content(m.content)} for m in request.messages]}

    if request.stream:
        completion_id = new_completion_id()

        async def generate():
            async for chunk in stream_to_chat_completions_chunks(
                agent.astream(
                    input=messages,
                    stream_mode=["updates", "messages"],
                    config=trace_config(session_id),
                ),
                completion_id=completion_id,
                model=request.model,
            ):
                yield chunk

        return StreamingResponse(generate(), media_type="text/event-stream")

    completion_id = new_completion_id()
    content = await collect_chat_completion_content(
        agent.astream(
            input=messages,
            stream_mode=["updates", "messages"],
            config=trace_config(),
        )
    )

    return ChatCompletionResponse(
        id=completion_id,
        object="chat.completion",
        model=request.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=AssistantMessage(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
    )


@router.post("/invocations")
async def invocations_compat(body: dict, http_request: Request):
    """Handle requests from the React chat UI which uses the OpenAI Responses API format.

    The Databricks ai-sdk-provider responses() client sends input as a list of messages
    and expects SSE events: response.output_text.delta + response.output_item.done.
    """
    session_id = http_request.headers.get("X-Session-Id") or body.get("context", {}).get("conversation_id")
    messages = [ChatMessage(**m) for m in body.get("input", [])]
    agent = await init_agent()
    lg_messages = {"messages": [{"role": m.role, "content": normalize_content(m.content)} for m in messages]}
    item_id = new_completion_id()

    if body.get("stream", False):
        async def generate():
            async for chunk in stream_to_responses_api_chunks(
                agent.astream(
                    input=lg_messages,
                    stream_mode=["updates", "messages"],
                    config=trace_config(session_id),
                ),
                item_id=item_id,
            ):
                yield chunk

        return StreamingResponse(generate(), media_type="text/event-stream")

    content = await collect_chat_completion_content(
        agent.astream(
            input=lg_messages,
            stream_mode=["updates", "messages"],
            config=trace_config(),
        )
    )

    return {
        "output": [
            {
                "type": "message",
                "id": item_id,
                "role": "assistant",
                "content": [{"type": "output_text", "text": content}],
            }
        ]
    }
