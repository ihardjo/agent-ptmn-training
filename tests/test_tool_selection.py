"""Selecting the SQL tools.

`TODO 3` in `init_agent` is meant to be edited during a workshop, so the three
settings it documents — no names, a named list, `[]` — are all exercised here
rather than trusted to read correctly.

One of these guards a mistake that leaves no trace: caching the *selection*
rather than the discovered list would bake the first request's choice into
the process, and `init_agent()` runs per request, so it would only show on
the second, differing call.
"""

from __future__ import annotations

import asyncio

import pytest

import agent_server.mcp as mcp_mod


class _Tool:
    """Stands in for a resolved MCP tool; only `.name` is ever read."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - test output only
        return f"_Tool({self.name!r})"


EXECUTE = "execute_sql"
POLL = "poll_sql_result"
READ_ONLY = "execute_sql_read_only"


class _Client:
    """Stands in for the MCP client; only `get_tools` is ever called."""

    def __init__(self, tools: list) -> None:
        self._tools = tools

    async def get_tools(self) -> list:
        return self._tools


def _explodes():
    raise AssertionError("the server was reached when the cache should have served")


@pytest.fixture
def discovered(monkeypatch):
    """A server that has already answered, so no network is involved."""
    tools = [_Tool(EXECUTE), _Tool(POLL)]
    monkeypatch.setattr(mcp_mod, "_mcp_tools", tools)
    monkeypatch.setattr(mcp_mod, "_mcp_unavailable", None)
    return tools


def _names(*selection, **kwargs) -> list[str]:
    return [t.name for t in asyncio.run(mcp_mod.mcp_tools(*selection, **kwargs))]


# ── the three settings TODO 3 documents ──────────────────────────────────────


def test_no_names_takes_everything_the_server_offers(discovered):
    assert _names() == [EXECUTE, POLL]


def test_a_named_list_takes_only_those(discovered):
    """A filter, so the server's order is what comes back, not the order
    asked for. Nothing downstream depends on tool order."""
    assert _names([POLL]) == [POLL]
    assert _names([POLL, EXECUTE]) == [EXECUTE, POLL]


def test_an_empty_list_takes_nothing(discovered):
    assert _names([]) == []


def test_an_unknown_name_is_simply_absent(discovered):
    """No longer an error. A typo drops the tool silently, so the mounted
    list is logged at INFO on every call as the way to notice."""
    assert _names(["execute_sql_read_only"]) == []


def test_a_narrow_selection_does_not_poison_the_cache(discovered):
    """Filtering applies on the way out. Cached, it would bake the first
    request's choice into the process."""
    assert _names([EXECUTE]) == [EXECUTE]
    assert _names() == [EXECUTE, POLL]


# ── the cache modes, as `MCPAdapter.list_tools` defines them ─────────────────


def test_use_serves_the_cache_without_calling_the_server(discovered, monkeypatch):
    """The default. `discovered` has already filled the cache, so a client
    that would explode is never reached for."""
    monkeypatch.setattr(mcp_mod, "init_mcp_client", _explodes)
    assert _names() == [EXECUTE, POLL]


def test_bypass_calls_the_server_and_leaves_the_cache_alone(monkeypatch):
    monkeypatch.setattr(mcp_mod, "_mcp_tools", None)
    monkeypatch.setattr(mcp_mod, "init_mcp_client", lambda: _Client([_Tool(EXECUTE)]))
    assert _names(None, cache_mode="bypass") == [EXECUTE]
    assert mcp_mod._mcp_tools is None, "bypass must not populate the cache"


def test_refresh_replaces_a_stale_cache(discovered, monkeypatch):
    """The server grew a tool. `use` cannot see it; `refresh` can."""
    monkeypatch.setattr(
        mcp_mod, "init_mcp_client", lambda: _Client([_Tool(EXECUTE), _Tool(POLL), _Tool(READ_ONLY)])
    )
    assert _names() == [EXECUTE, POLL]
    assert _names(None, cache_mode="refresh") == [EXECUTE, POLL, READ_ONLY]
    assert _names() == [EXECUTE, POLL, READ_ONLY], "refresh repopulates the cache"


def test_an_unknown_mode_raises(discovered):
    with pytest.raises(ValueError, match="cache_mode"):
        _names(None, cache_mode="sometimes")
