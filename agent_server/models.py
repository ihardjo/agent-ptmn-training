from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str | list | None = None
    name: str | None = None

    model_config = {"extra": "allow"}


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
