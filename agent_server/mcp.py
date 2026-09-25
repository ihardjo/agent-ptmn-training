"""Discovering the SQL tools the MCP server offers, once per process.

`agent_server.tools` knows how to *reach* the server; this module knows how
often to ask it. The split matters because the answer is static and the asking
is not cheap: a `tools/list` is a session plus a round trip to another region,
and `init_agent()` runs per request.
"""

import asyncio
import logging
from typing import Any, Optional, Sequence

from agent_server.clients import init_mcp_client

logger = logging.getLogger(__name__)

_mcp_tools: Optional[list[Any]] = None

# One discovery at a time. Not an optimisation: the client holds no session,
# so concurrent `get_tools()` calls each open their own, and the server drops
# the extras. Four cold-start requests measured without this returned 3, 0, 3,
# 0 tools — half the agents built with no way to query, and only a log line to
# say so.
_mcp_tools_lock = asyncio.Lock()

# Why the SQL tool is absent, or None while it is present. Set on every
# resolution attempt, so a server that recovers mid-session stops warning.
_mcp_unavailable: Optional[str] = None

# `mcp.client.caching.CacheMode` (SEP-2549), spelled out rather than imported:
# the type belongs to the MCP SDK's own caching layer, which the Databricks
# client does not use, so importing it would claim a coupling that is not there.
CACHE_MODES = ("use", "refresh", "bypass")


async def mcp_tools(
    names: Optional[Sequence[str]] = None,
    *,
    cache_mode: str = "use",
) -> list[Any]:
    """Every SQL tool the server exposes, or only `names` of them.

    This is `langchain.mcp.MCPAdapter.list_tools(cache_mode="use")` — serve a
    cached tool list when one is present, call the server when it is not —
    reimplemented because that adapter is built on `fastmcp.Client` and reaches
    a server by URL. Ours is reached with Databricks OAuth, which
    `DatabricksOAuthClientProvider` holds and refreshes for us, so the client
    stays `databricks_langchain`'s and the caching comes here instead. Upstream
    keeps its cache on the client (SEP-2549); `DatabricksMultiServerMCPClient`
    has none, and its `get_tools()` opens a session and re-lists every call.

    A failure is not cached, so a server that recovers degrades this run rather
    than the whole process. Filtering happens on the way out, so a narrow
    selection never becomes the process's idea of what the server offers.

    Args:
        names: the tools to mount, or None for every tool the server offers.
        cache_mode: as upstream — `use` serves the cached list when there is
            one, `refresh` calls the server and repopulates, and `bypass`
            calls the server and leaves the cache alone.
    """
    global _mcp_tools
    if cache_mode not in CACHE_MODES:
        raise ValueError(f"cache_mode must be one of {CACHE_MODES}, not {cache_mode!r}")

    discovered = _mcp_tools if cache_mode == "use" else None
    if discovered is None:
        async with _mcp_tools_lock:
            # Re-checked under the lock: another request may have filled it
            # while this one waited, which is the whole point of the lock.
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
