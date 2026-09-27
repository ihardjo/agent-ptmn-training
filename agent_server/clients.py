"""Reaching the Jakarta workspace: the SDK client, and the MCP client on top.

Kept apart from `tools.py` because this is how the agent *connects*, not what
it can *do*. Separating them also keeps the imports acyclic: `mcp` needs the
client, and `tools` needs `mcp` to assemble the tool list.
"""

import logging
from typing import Optional

from databricks.sdk import WorkspaceClient
from databricks_langchain import DatabricksMCPServer, DatabricksMultiServerMCPClient

from agent_server.env import env

logger = logging.getLogger(__name__)


def jakarta_workspace_client() -> Optional[WorkspaceClient]:
    """A client for the Jakarta workspace, or None when it is not configured.

    The host is explicit rather than derived. The ambient Databricks
    environment belongs to the workspace this app runs in, which is not the
    one holding the data.

    `DATABRICKS_JAKARTA_PROFILE` runs under a CLI profile instead, for a
    laptop whose workspace has no service principal yet. The deployed app has
    no profile to fall back on, so it is unset there and the credentials below
    are what count.
    """
    if profile := env("DATABRICKS_JAKARTA_PROFILE"):
        return WorkspaceClient(profile=profile)

    # Stripped on the way in: these three arrive from a secret scope, and a
    # trailing newline on the secret is rejected as a wrong credential rather
    # than as a malformed one. See `agent_server/env.py`.
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
    """The Jakarta managed SQL MCP server (`/api/2.0/mcp/sql`),
    or None when it is not configured.

    SQL is the only server: `system.ai` functions are Unity Catalog UDFs, so
    the model reaches them through `execute_sql` rather than spending tool
    definitions on them.
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