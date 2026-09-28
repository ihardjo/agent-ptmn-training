import logging
from typing import Any, AsyncGenerator

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from langfuse.langchain import CallbackHandler

from agent_server.agent import init_agent
from agent_server.env import env
from agent_server.skills import skill_files
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

DEFAULT_TRACE_NAME = "LangGraph"


def trace_config(session_id: str | None = None) -> dict:
    """Langfuse callbacks for one run, or an empty config when no host is set.

    The host is the gate: an unset host resolves to cloud.langfuse.com inside the
    SDK, so keys left in place would ship prompts off-premises instead of
    failing. `run_name` is LangChain's — the handler reads it as the trace name.
    """
    host = env("LANGFUSE_BASE_URL") or env("LANGFUSE_HOST")
    if not host:
        logger.info("No LANGFUSE_HOST — this run will not be traced.")
        return {}
    name = env("LANGFUSE_TRACE_NAME") or DEFAULT_TRACE_NAME
    config: dict = {"callbacks": [CallbackHandler()], "run_name": name}
    if session_id:
        config["metadata"] = {"langfuse_session_id": session_id}
    return config


def agent_stream(agent: Any, messages: list, session_id: str | None):
    """The agent's event stream for one request.

    `files=` seeds the skills tier into this turn's state, which is how the
    model sees skill content it never wrote.
    """
    return agent.astream(
        input={
            "messages": [{"role": m.role, "content": normalize_content(m.content)} for m in messages],
            "files": skill_files(),
        },
        stream_mode=["updates", "messages"],
        config=trace_config(session_id),
    )


def sse_response(chunks: AsyncGenerator[str, None]) -> StreamingResponse:
    """Serve SSE, reporting a mid-stream failure in the stream itself, because
    once the response has started the status code is spent.
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
    """Handle requests from the React chat UI, which speaks the OpenAI Responses
    API: `input` as a list of messages, Responses SSE events back.
    """
    session_id = http_request.headers.get("X-Session-Id") or body.get("context", {}).get("conversation_id")
    agent = await init_agent()
    stream = agent_stream(agent, conversation_turns(body.get("input", [])), session_id)
    item_id = new_completion_id()

    if body.get("stream", False):
        return sse_response(stream_to_responses_api_chunks(stream, item_id=item_id))

    return {"output": await collect_response_output(stream, item_id=item_id)}


@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    session: str = Form(default=""),
):
    """Take one file from the chat and write it to the wiki Volume.

    The chat UI's paperclip calls `POST /api/files/upload` on the Node app,
    which forwards the multipart body here untouched. The response shape is the
    chat template's — its client shows `pathname` on the chip and puts `error`
    straight into a toast, so a refusal returns 400 with a sentence in it.
    """
    from agent_server.backends import uploads_backend
    from agent_server.uploads import (
        UploadRejected,
        agent_path,
        check_name,
        check_size,
        store,
    )

    try:
        name = check_name(file.filename or "")
        data = await file.read()
        check_size(name, len(data))
    except UploadRejected as rejected:
        # 400 and not 422: this is a decision about the file, not a malformed
        # request, and the sentence is meant for the person who chose it.
        raise HTTPException(status_code=400, detail={"error": str(rejected)})

    backend = uploads_backend()
    if backend is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Attachments need the wiki Volume, which this server "
                "cannot reach. Set DATABRICKS_JAKARTA_*."
            },
        )

    try:
        stored = store(backend, session, name, data)
    except Exception as exc:
        logger.exception("upload failed for %s", name)
        raise HTTPException(
            status_code=500,
            detail={"error": f"Could not write `{name}` to the wiki Volume: {exc}"},
        )

    visible = agent_path(session, name)
    logger.info("stored upload %s (%d bytes) at %s", name, stored.bytes_written, visible)
    return {
        "url": visible,
        "pathname": stored.filename,
        "contentType": file.content_type or "text/plain",
        "bytes": stored.bytes_written,
    }
