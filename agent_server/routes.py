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
    stream_to_chat_completions_chunks,
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
    messages = {"messages": [{"role": m.role, "content": m.content} for m in request.messages]}

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
    """Compatibility shim for the React chat UI and any caller using the ResponsesAgent format."""
    messages = [ChatMessage(**m) for m in body.get("input", [])]
    return await chat_completions(
        ChatRequest(messages=messages, stream=body.get("stream", False)),
        http_request,
    )
