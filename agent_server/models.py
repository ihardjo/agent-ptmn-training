from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str | list | None = None
    name: str | None = None

    model_config = {"extra": "allow"}


def conversation_turns(items: list[dict]) -> list["ChatMessage"]:
    """The conversation turns out of a Responses API `input` list.

    Clients replay the items we emitted — `reasoning`, `function_call`,
    `function_call_output`, `mcp_approval_*` — and none of those carry a `role`.
    LangGraph rebuilds its state from the turns alone, so they are skipped rather
    than failing validation.
    """
    return [ChatMessage(**item) for item in items if "role" in item]


class ChatRequest(BaseModel):
    model: str = "agent"
    messages: list[ChatMessage]
    stream: bool = False

    model_config = {"extra": "allow"}


# ── Response models (OpenAI Chat Completions format) ───────────────────────────

class AssistantMessage(BaseModel):
    role: str
    content: str | None = None
    # Mirrors the streaming path's `reasoning_content` delta key.
    reasoning_content: str | None = None


class ChatCompletionChoice(BaseModel):
    index: int
    message: AssistantMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str
    model: str
    choices: list[ChatCompletionChoice]
