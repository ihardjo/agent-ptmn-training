import logging
from datetime import datetime
from typing import Optional

from databricks.sdk import WorkspaceClient
from databricks_langchain import ChatDatabricks, DatabricksMCPServer, DatabricksMultiServerMCPClient
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from langchain.agents import create_agent
from langchain_core.tools import tool
from langfuse import propagate_attributes
from langfuse.langchain import CallbackHandler
from pydantic import BaseModel

from agent_server.utils import (
    collect_chat_completion_content,
    get_databricks_host_from_env,
    new_completion_id,
    stream_to_chat_completions_chunks,
)

logger = logging.getLogger(__name__)
langfuse_handler = CallbackHandler()
sp_workspace_client = WorkspaceClient()

app = FastAPI(title="Agent API")


# ── Request / Response models ──────────────────────────────────────────────────

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


# ── Tools ──────────────────────────────────────────────────────────────────────

@tool
def get_current_time() -> str:
    """Get the current date and time."""
    return datetime.now().isoformat()


def init_mcp_client(workspace_client: WorkspaceClient) -> DatabricksMultiServerMCPClient:
    host_name = get_databricks_host_from_env()
    return DatabricksMultiServerMCPClient(
        [
            DatabricksMCPServer(
                name="system-ai",
                url=f"{host_name}/api/2.0/mcp/functions/system/ai",
                workspace_client=workspace_client,
            ),
        ]
    )


async def init_agent(workspace_client: Optional[WorkspaceClient] = None):
    tools = [get_current_time]
    # To use MCP server tools instead, replace the line above with:
    #   mcp_client = init_mcp_client(workspace_client or sp_workspace_client)
    #   try:
    #       tools.extend(await mcp_client.get_tools())
    #   except Exception:
    #       logger.warning("Failed to fetch MCP tools. Continuing without MCP tools.", exc_info=True)
    return create_agent(tools=tools, model=ChatDatabricks(endpoint="databricks-gpt-5-2"))


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
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

    return {
        "id": completion_id,
        "object": "chat.completion",
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
