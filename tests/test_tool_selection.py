"""Selecting the SQL tools, and telling the model when none was selected.

`TODO 3` in `init_agent` is meant to be edited during a workshop, so the three
settings it documents — `TOOLS_ALL`, a named list, `[]` — are all exercised
here rather than trusted to read correctly.

Two of these guard mistakes that leave no trace. Caching the *selection* rather
than the discovered list would bake the first request's choice into the
process, and `init_agent()` runs per request, so it would only show on the
second, differing call. And an inverted `no_sql` condition would stop telling
the model it has no way to query, which is the state `NO_SQL_NOTICE` exists to
prevent — the agent answers from nothing and the figure looks measured.
"""

from __future__ import annotations

import asyncio

import pytest

import agent_server.agent as agent_mod


class _Tool:
    """Stands in for a resolved MCP tool; only `.name` is ever read."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - test output only
        return f"_Tool({self.name!r})"


EXECUTE = "execute_sql"
POLL = "poll_sql_result"


@pytest.fixture
def discovered(monkeypatch):
    """A server that has already answered, so no network is involved."""
    tools = [_Tool(EXECUTE), _Tool(POLL)]
    monkeypatch.setattr(agent_mod, "_mcp_tools", tools)
    monkeypatch.setattr(agent_mod, "_mcp_unavailable", None)
    return tools


def _names(selection) -> list[str]:
    return [t.name for t in asyncio.run(agent_mod.mcp_tools(selection))]


# ── the three settings TODO 3 documents ──────────────────────────────────────


def test_all_takes_everything_the_server_offers(discovered):
    assert _names(agent_mod.TOOLS_ALL) == [EXECUTE, POLL]


def test_a_named_list_takes_only_those_in_the_order_asked_for(discovered):
    assert _names([POLL, EXECUTE]) == [POLL, EXECUTE]


def test_an_empty_list_takes_nothing(discovered):
    assert _names([]) == []


# ── mistakes that would otherwise be silent ──────────────────────────────────


def test_an_unknown_name_raises_and_says_what_is_available(discovered):
    """`stage_skills` raises for the same reason: a typo that silently drops a
    tool changes behaviour with nothing in the logs pointing at the cause."""
    with pytest.raises(ValueError) as exc:
        _names(["execute_sql_read_only"])
    message = str(exc.value)
    assert "execute_sql_read_only" in message
    assert EXECUTE in message and POLL in message


def test_a_narrow_selection_does_not_poison_the_cache(discovered):
    """Selection applies on the way out. Cached, it would bake the first
    request's choice into the process."""
    assert _names([EXECUTE]) == [EXECUTE]
    assert _names(agent_mod.TOOLS_ALL) == [EXECUTE, POLL]


# ── what the model is told when it cannot query ──────────────────────────────


NOTICE_HEADING = "# This run has no SQL tool"


def _prompt(monkeypatch, selected, unavailable=None) -> str:
    """The system prompt `init_agent` hands to `create_deep_agent`.

    Everything that would reach the network or a workspace is stubbed; the
    point is the wiring, not the graph.
    """
    captured: dict = {}

    def fake_create(**kw):
        captured.update(kw)
        return object()

    async def selection(*_, **__):
        return selected

    monkeypatch.setattr(agent_mod, "create_deep_agent", fake_create)
    monkeypatch.setattr(agent_mod, "ChatDatabricks", lambda **kw: object())
    monkeypatch.setattr(agent_mod, "build_backend", lambda *a, **kw: object())
    monkeypatch.setattr(agent_mod, "mcp_tools", selection)
    monkeypatch.setattr(agent_mod, "_mcp_unavailable", unavailable)
    asyncio.run(agent_mod.init_agent())
    return captured["system_prompt"]


def test_no_notice_when_a_query_is_possible(monkeypatch):
    assert NOTICE_HEADING not in _prompt(monkeypatch, [_Tool(EXECUTE), _Tool(POLL)])


def test_the_notice_fires_when_nothing_was_selected(monkeypatch):
    """`[]` is a documented setting of TODO 3, not only a failure."""
    prompt = _prompt(monkeypatch, [])
    assert NOTICE_HEADING in prompt
    assert "was selected for this run" in prompt


def test_the_notice_fires_when_only_the_poller_was_selected(monkeypatch):
    """The test is `execute_sql`, not emptiness: a poller alone is non-empty
    and still cannot answer anything."""
    assert NOTICE_HEADING in _prompt(monkeypatch, [_Tool(POLL)])


def test_the_notice_still_fires_when_the_server_is_unreachable(monkeypatch):
    """The older of the two causes; reachability must keep working."""
    reason = "the dbsql MCP server could not be reached (ConnectError)"
    prompt = _prompt(monkeypatch, [], unavailable=reason)
    assert NOTICE_HEADING in prompt
    assert reason in prompt, "the model is told which of the two causes applies"
