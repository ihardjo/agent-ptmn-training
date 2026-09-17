import logging
import os
from typing import Optional

from databricks.sdk import WorkspaceClient
from databricks_langchain import DatabricksMCPServer, DatabricksMultiServerMCPClient

from agent_server.utils import get_databricks_host_from_env

logger = logging.getLogger(__name__)

sp_workspace_client = WorkspaceClient()


def jakarta_workspace_client() -> Optional[WorkspaceClient]:
    """A client for the Jakarta workspace, or None when it is not configured.

    The host is explicit rather than derived: `get_databricks_host_from_env()`
    reads the ambient environment, which in the deployed app is Singapore. The
    data lives in a different workspace and metastore, so the two must not
    collapse onto one host if that environment shifts.
    """
    host = os.environ.get("DATABRICKS_JAKARTA_HOST")
    client_id = os.environ.get("DATABRICKS_JAKARTA_CLIENT_ID")
    client_secret = os.environ.get("DATABRICKS_JAKARTA_CLIENT_SECRET")
    if not (host and client_id and client_secret):
        return None
    return WorkspaceClient(
        host=host,
        client_id=client_id,
        client_secret=client_secret,
        # Pinned, not inferred. Left to its own devices the SDK walks its
        # credential chain and picks up the ambient Databricks auth first —
        # which mints a token for *this* workspace and sends it to Jakarta,
        # where it comes back as "Invalid Token".
        auth_type="oauth-m2m",
    )


def init_mcp_client(workspace_client: WorkspaceClient) -> DatabricksMultiServerMCPClient:
    host_name = get_databricks_host_from_env()
    servers = [
        DatabricksMCPServer(
            name="system-ai",
            url=f"{host_name}/api/2.0/mcp/functions/system/ai",
            workspace_client=workspace_client,
        ),
    ]

    # Unity Catalog tables in the Jakarta workspace, via its managed SQL MCP
    # server. Skipped rather than fatal when unconfigured, so the agent still
    # serves its other tools.
    if (jakarta := jakarta_workspace_client()) is not None:
        servers.append(
            DatabricksMCPServer(
                name="jakarta-sql",
                url=f"{os.environ['DATABRICKS_JAKARTA_HOST']}/api/2.0/mcp/sql",
                workspace_client=jakarta,
                # A statement that fails comes back as a normal result whose
                # payload carries the error, so this only covers transport
                # faults — leaving those to the model beats ending the turn.
                handle_tool_error=True,
            )
        )
    else:
        logger.info("DATABRICKS_JAKARTA_* not configured — remote SQL tools are unavailable.")

    return DatabricksMultiServerMCPClient(servers)
