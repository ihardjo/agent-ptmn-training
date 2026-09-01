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
