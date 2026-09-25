import logging
import os
from typing import Optional
import random

from datetime import datetime, timezone
from langchain_core.tools import tool

from databricks.sdk import WorkspaceClient
from databricks_langchain import DatabricksMCPServer, DatabricksMultiServerMCPClient

logger = logging.getLogger(__name__)


@tool
def get_current_time() -> str:
    """Get the current UTC time, ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


@tool
def days_until(iso_date: str) -> int:
    """Get whole days from today until the given date, negative if it has passed."""
    target = datetime.fromisoformat(iso_date).date()
    return (target - datetime.now(timezone.utc).date()).days


@tool
def roll_dice(sides: int = 6) -> int:
    """Roll a dice with the given number of sides."""
    return random.randint(1, sides)


def jakarta_workspace_client() -> Optional[WorkspaceClient]:
    """A client for the Jakarta workspace, or None when it is not configured.

    The host is explicit rather than derived. The ambient Databricks
    environment belongs to the workspace this app runs in, which is not the
    one holding the data.
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
        # Pinned to prevent SDK picking up the ambient Databricks auth, which produces
        # invalid token for *this* workspace.
        auth_type="oauth-m2m",
        # Pinned to prevent ambient CLI profile leaking.
        profile="",
    )


def init_mcp_client() -> Optional[DatabricksMultiServerMCPClient]:
    """The Jakarta managed SQL MCP server (DBSQL MCP Server), 
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
                name="DBSQL MCP Server",
                url=f"{os.environ['DATABRICKS_JAKARTA_HOST']}/api/2.0/mcp/sql",
                workspace_client=jakarta,
                # Covers transport faults to prevent ending the turn prematurely.
                handle_tool_error=True,
            ),
        ]
    )