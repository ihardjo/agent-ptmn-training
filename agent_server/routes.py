import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langfuse import propagate_attributes
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
langfuse_handler = CallbackHandler()

router = APIRouter()


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
            with propagate_attributes(session_id=session_id):
                async for chunk in stream_to_chat_completions_chunks(
                    agent.astream(
                        input=messages,
                        stream_mode=["updates", "messages"],
                        config={"callbacks": [langfuse_handler]},
                    ),
                    completion_id=completion_id,
                    model=request.model,
                ):
                    yield chunk

        return StreamingResponse(generate(), media_type="text/event-stream")

    completion_id = new_completion_id()
    with propagate_attributes(session_id=session_id):
        content = await collect_chat_completion_content(
            agent.astream(
                input=messages,
                stream_mode=["updates", "messages"],
                config={"callbacks": [langfuse_handler]},
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
            with propagate_attributes(session_id=session_id):
                async for chunk in stream_to_responses_api_chunks(
                    agent.astream(
                        input=lg_messages,
                        stream_mode=["updates", "messages"],
                        config={"callbacks": [langfuse_handler]},
                    ),
                    item_id=item_id,
                ):
                    yield chunk

        return StreamingResponse(generate(), media_type="text/event-stream")

    with propagate_attributes(session_id=session_id):
        content = await collect_chat_completion_content(
            agent.astream(
                input=lg_messages,
                stream_mode=["updates", "messages"],
                config={"callbacks": [langfuse_handler]},
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
