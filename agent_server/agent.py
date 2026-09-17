import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from databricks.sdk import WorkspaceClient
from databricks_langchain import ChatDatabricks
from langchain.agents import create_agent

from agent_server.tools import init_mcp_client, sp_workspace_client

logger = logging.getLogger(__name__)

# Kept as prose in its own file so the agent's instructions can be edited and
# reviewed without touching Python. Read once at import, as a constant would be.
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system_prompt.md").read_text()


_mcp_tools: Optional[list[Any]] = None
_mcp_tools_lock = asyncio.Lock()


async def mcp_tools(workspace_client: WorkspaceClient) -> list[Any]:
    """MCP tools, discovered once per process.

    Both routes call `init_agent()` per request, and discovery is an
    `initialize` plus `tools/list` round trip to a server in another region —
    too much to put in front of every turn. The tool list is static, so cache
    it. A failure is not cached, so an unreachable server at startup degrades
    this run rather than the whole process.
    """
    global _mcp_tools
    if _mcp_tools is not None:
        return _mcp_tools
    async with _mcp_tools_lock:
        if _mcp_tools is None:
            try:
                tools = await init_mcp_client(workspace_client).get_tools()
            except Exception:
                logger.warning(
                    "Failed to fetch MCP tools (system-ai and/or jakarta-sql). "
                    "Continuing without them.",
                    exc_info=True,
                )
                return []
            logger.info("Resolved %d MCP tools: %s", len(tools), [t.name for t in tools])
            _mcp_tools = tools
    return _mcp_tools


async def init_agent(workspace_client: Optional[WorkspaceClient] = None):
    return create_agent(
        tools=await mcp_tools(workspace_client or sp_workspace_client),
        model=ChatDatabricks(endpoint="databricks-gpt-oss-120b"),
        system_prompt=SYSTEM_PROMPT,
    )
