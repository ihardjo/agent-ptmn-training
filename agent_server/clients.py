"""Reaching the Jakarta workspace: the SDK client, and the MCP client on top.

Kept apart from `tools.py` because this is how the agent connects, not what it
can do, which also keeps the imports acyclic.
"""

import logging
from typing import Optional

from databricks.sdk import WorkspaceClient
from databricks_langchain import DatabricksMCPServer, DatabricksMultiServerMCPClient

from agent_server.env import env

logger = logging.getLogger(__name__)


def jakarta_workspace_client() -> Optional[WorkspaceClient]:
    """A client for the Jakarta workspace, or None when it is not configured.

    The host is explicit because the ambient Databricks environment belongs to
    the workspace this app runs in, not the one holding the data. The profile
    branch is for a laptop with no service principal.
    """
    if profile := env("DATABRICKS_JAKARTA_PROFILE"):
        return WorkspaceClient(profile=profile)

    host = env("DATABRICKS_JAKARTA_HOST")
    client_id = env("DATABRICKS_JAKARTA_CLIENT_ID")
    client_secret = env("DATABRICKS_JAKARTA_CLIENT_SECRET")
    if not (host and client_id and client_secret):
        return None
    return WorkspaceClient(
        host=host,
        client_id=client_id,
        client_secret=client_secret,
        auth_type="oauth-m2m",
        profile="",
    )


def init_mcp_client() -> Optional[DatabricksMultiServerMCPClient]:
    """The Jakarta managed SQL MCP server, or None when it is not configured.

    The only server: `system.ai` functions are Unity Catalog UDFs, so the model
    reaches them through `execute_sql` rather than spending tool definitions.
    """
    jakarta = jakarta_workspace_client()
    if jakarta is None:
        logger.info("DATABRICKS_JAKARTA_* not configured — the agent will have no tools.")
        return None
    return DatabricksMultiServerMCPClient(
        [
            DatabricksMCPServer(
                name="dbsql",
                url=f"{env('DATABRICKS_JAKARTA_HOST')}/api/2.0/mcp/sql",
                workspace_client=jakarta,
                handle_tool_error=True,
            ),
        ]
    )
