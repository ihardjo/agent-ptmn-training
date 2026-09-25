"""What the model can call: the tools defined here, and the ones the SQL
server offers, assembled into the one list the agent is built with.

The connection to Databricks lives in `clients.py`; this module is only about
which tools reach the model.
"""

import logging
import random
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool

from agent_server.mcp import mcp_tools

logger = logging.getLogger(__name__)


@tool
def get_current_time() -> str:
    """The current UTC time, ISO-8601. Use this whenever the answer depends on
    what time it is now — you have no clock of your own."""
    return datetime.now(timezone.utc).isoformat()


@tool
def days_until(iso_date: str) -> int:
    """Whole days from today until the given date, negative if it has passed.

    `iso_date` is YYYY-MM-DD. Use this rather than counting by hand."""
    target = datetime.fromisoformat(iso_date).date()
    return (target - datetime.now(timezone.utc).date()).days


@tool
def roll_dice(sides: int = 6) -> int:
    """Roll a die with the given number of sides."""
    return random.randint(1, sides)

## TODO 3a: Tool Selection (Manually Defined Tools)
# The tools defined above. Drop one from this list to take it away from the
# model; the function itself stays here, unused.
SELECTED_CUSTOM_TOOLS = [
    get_current_time,
    days_until,
    roll_dice,
]

## TODO 3b: Tool Selection (Databricks Managed MCP)
# ["execute_sql", "execute_sql_read_only" "poll_sql_result"]
SELECTED_MCP_TOOLS = ["execute_sql_read_only", "poll_sql_result"]

async def agent_tools() -> list[Any]:
    """Every tool the agent is built with, remote ones first.

    An unreachable SQL server returns none of its own rather than raising, so
    the agent still starts with the locally defined tools — see `mcp_tools`.
    """
    sql_tools = await mcp_tools(SELECTED_MCP_TOOLS)

    return [
        *sql_tools,
        *SELECTED_CUSTOM_TOOLS,
    ]
