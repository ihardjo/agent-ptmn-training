"""Human approval before `execute_sql_read_only` runs.

Two protocols meet here. `HumanInTheLoopMiddleware` pauses the graph and expects
`{"decisions": [...]}` back; the chat client speaks the Responses MCP protocol,
reading `mcp_approval_request` items and replaying history with an
`mcp_approval_response` attached. The client is stateless and replays, LangGraph
is stateful and resumes, and `thread_id` is what reconciles them.
"""

from __future__ import annotations

import json

import pytest

from agent_server.approvals import approval_requests, decisions_from


class _Interrupt:
    def __init__(self, *names):
        self.id = "int-1"
        self.value = {"action_requests": [
            {"name": n, "args": {"query": f"SELECT {i}"}} for i, n in enumerate(names)]}


def test_one_request_per_pending_call():
    """The model batches tool calls, and the client approves each separately."""
    reqs = approval_requests(_Interrupt("execute_sql_read_only", "execute_sql_read_only"))
    assert [r["type"] for r in reqs] == ["mcp_approval_request"] * 2
    assert [r["id"] for r in reqs] == ["int-1:0", "int-1:1"]


def test_arguments_are_a_json_string_not_an_object():
    """The provider's schema declares `arguments: z.string()`; an object fails
    validation and the whole response is rejected."""
    args = approval_requests(_Interrupt("execute_sql_read_only"))[0]["arguments"]
    assert isinstance(args, str)
    assert json.loads(args) == {"query": "SELECT 0"}


def test_a_request_carries_the_tool_name():
    """The client shows it in the prompt, so an operator approves a named tool
    rather than an opaque one."""
    assert approval_requests(_Interrupt("execute_sql_read_only"))[0]["name"] == "execute_sql_read_only"


def test_an_interrupt_with_no_requests_yields_none():
    class _Empty:
        id = "x"
        value: dict = {}
    assert approval_requests(_Empty()) == []


# ── the resume direction ─────────────────────────────────────────────────────


def test_history_without_an_approval_is_not_a_resume():
    """Every ordinary turn replays history too, so the absence has to be the
    signal — treating one as a resume would drop the user's question."""
    assert decisions_from([{"role": "user", "content": "hi"}]) is None
    assert decisions_from([]) is None


def test_decisions_map_approve_and_reject():
    got = decisions_from([
        {"type": "mcp_approval_response", "approval_request_id": "int-1:0", "approve": True},
        {"type": "mcp_approval_response", "approval_request_id": "int-1:1", "approve": False},
    ])
    assert got == [{"type": "approve"}, {"type": "reject"}]


def test_decisions_are_ordered_by_position_not_arrival():
    """The middleware lines decisions up with `action_requests` positionally, so
    a client replaying them out of order would approve the wrong query."""
    got = decisions_from([
        {"type": "mcp_approval_response", "approval_request_id": "int-1:1", "approve": False},
        {"type": "mcp_approval_response", "approval_request_id": "int-1:0", "approve": True},
    ])
    assert got == [{"type": "approve"}, {"type": "reject"}]


def test_approval_items_round_trip():
    """What the server emits must be answerable by what the client sends back."""
    reqs = approval_requests(_Interrupt("execute_sql_read_only", "execute_sql_read_only"))
    replay = [{"type": "mcp_approval_response", "approval_request_id": r["id"], "approve": True}
              for r in reversed(reqs)]
    assert decisions_from(replay) == [{"type": "approve"}, {"type": "approve"}]


# ── what is gated, and what is not ───────────────────────────────────────────


def test_only_the_sql_tool_is_gated():
    """`poll_sql_result` reads a statement already approved and executed; gating
    it would ask the operator to approve the same query twice."""
    from agent_server.agent import INTERRUPT_ON

    assert set(INTERRUPT_ON) == {"execute_sql_read_only"}


def test_edit_and_respond_are_not_offered():
    """`edit` would let a decision rewrite the SQL, which is a different tool
    call from the one shown; `respond` would let it fabricate a result."""
    from agent_server.agent import INTERRUPT_ON

    assert INTERRUPT_ON["execute_sql_read_only"]["allowed_decisions"] == ["approve", "reject"]


def test_the_checkpointer_is_shared_across_requests():
    """`init_agent()` runs per request. A saver built inside it would lose the
    paused run it exists to hold, and no approval could ever be resumed."""
    import agent_server.agent as agent_mod

    assert agent_mod.CHECKPOINTER is agent_mod.CHECKPOINTER


def test_the_run_config_carries_a_thread_id():
    from agent_server.routes import run_config

    assert run_config("sess-1")["configurable"]["thread_id"] == "sess-1"


def test_a_missing_session_still_runs(monkeypatch):
    """Without a session the run cannot be resumed, but it must not fail — the
    checkpointer requires a thread id whether or not anyone will resume it."""
    from agent_server.routes import run_config

    assert run_config(None)["configurable"]["thread_id"]
