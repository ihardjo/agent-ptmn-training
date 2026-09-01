from typing import Optional

from databricks.sdk import WorkspaceClient
from databricks_langchain import ChatDatabricks
from langchain.agents import create_agent

from agent_server.tools import get_current_time, init_mcp_client, sp_workspace_client


async def init_agent(workspace_client: Optional[WorkspaceClient] = None):
    tools = [get_current_time]
    # To use MCP server tools instead, replace the line above with:
    #   mcp_client = init_mcp_client(workspace_client or sp_workspace_client)
    #   try:
    #       tools.extend(await mcp_client.get_tools())
    #   except Exception:
    #       logger.warning("Failed to fetch MCP tools. Continuing without MCP tools.", exc_info=True)
    return create_agent(tools=tools, model=ChatDatabricks(endpoint="databricks-gpt-5-2"))
