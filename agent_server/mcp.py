"""Discovering the SQL tools the MCP server offers, once per process.

The answer is static and the asking is not cheap — a `tools/list` is a session
plus a cross-region round trip, and `init_agent()` runs per request.
"""

import asyncio
import logging
from typing import Any, Optional, Sequence

from agent_server.clients import init_mcp_client

logger = logging.getLogger(__name__)

_mcp_tools: Optional[list[Any]] = None

_mcp_tools_lock = asyncio.Lock()
_mcp_unavailable: Optional[str] = None
CACHE_MODES = ("use", "refresh", "bypass")


async def mcp_tools(
    names: Optional[Sequence[str]] = None,
    *,
    cache_mode: str = "use",
) -> list[Any]:
    """Every SQL tool the server exposes, or only `names` of them.

    `MCPAdapter.list_tools` reimplemented, because that adapter reaches a server
    by URL and ours needs Databricks OAuth. Failures are not cached, so a
    recovered server degrades this run only.

    `cache_mode` is `use` to serve the cached list, `refresh` to repopulate it,
    or `bypass` to call the server and leave the cache alone.
    """
    global _mcp_tools
    if cache_mode not in CACHE_MODES:
        raise ValueError(f"cache_mode must be one of {CACHE_MODES}, not {cache_mode!r}")

    discovered = _mcp_tools if cache_mode == "use" else None
    if discovered is None:
        async with _mcp_tools_lock:
            # Re-checked under the lock: another request may have filled it
            # while this one waited.
            if cache_mode == "use" and _mcp_tools is not None:
                discovered = _mcp_tools
            else:
                discovered = await _discover()
                if discovered is None:
                    return []
                if cache_mode != "bypass":
                    _mcp_tools = discovered

    selected = [t for t in discovered if names is None or t.name in names]
    logger.info("Tools mounted (%d): %s", len(selected), [t.name for t in selected])
    return selected


async def _discover() -> Optional[list[Any]]:
    """One `tools/list` round trip, or None with `_mcp_unavailable` saying why."""
    global _mcp_unavailable
    try:
        client = init_mcp_client()
        if client is None:
            _mcp_unavailable = "DATABRICKS_JAKARTA_* is not configured for this process"
            logger.error("NO SQL TOOL: %s", _mcp_unavailable)
            return None
        tools = await client.get_tools()
    except Exception as exc:
        _mcp_unavailable = (
            f"the dbsql MCP server could not be reached ({type(exc).__name__})"
        )
        logger.error("NO SQL TOOL: %s", _mcp_unavailable, exc_info=True)
        return None
    _mcp_unavailable = None
    return tools
