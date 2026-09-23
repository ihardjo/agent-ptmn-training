"""Pseudonymising staff addresses before the model sees them.

**Read this before changing the configuration.** An earlier version ran on the
way *out* (`apply_to_output` with `strategy="redact"`). Every test passed, it
worked under `ainvoke`, and it protected no served request at all: both routes
stream with `astream(stream_mode=["updates", "messages"])`, and the answer is
emitted token by token on the `messages` channel *before* `after_model`
rewrites state. langchain's stream transformer would cover that, but it reads
langgraph v3 protocol events and never sees legacy `AIMessageChunk` tuples.

Two lessons are encoded here.

A synthetic `AIMessage` cannot tell you whether the net works, so the
behavioural tests below run against **the instance `init_agent` actually
builds**, recovered by capturing what it hands to `create_deep_agent`, rather
than a hand-written copy of the configuration that could drift from it.

And the wiring is as easy to get wrong as the settings: the `flag_pii` branch
was once inverted, so the default — every served request — silently got no
middleware at all. `test_the_net_is_on_by_default` is the guard for that.
"""

from __future__ import annotations

import asyncio

from langchain.agents.middleware import PIIMiddleware, TodoListMiddleware
from langchain.agents.middleware._redaction import detect_email
from langchain.messages import AIMessage, HumanMessage, ToolMessage

import agent_server.agent as agent_mod


def identities_in(text: str) -> list[str]:
    """Addresses disclosed by `text`, detected by shape.

    Was `agent_server.privacy.identities_in`, a closed vocabulary covering both
    the name form and the address form. That module is gone, so this checks the
    address shape only — a name in the text is no longer detected.
    """
    return sorted({m["value"].casefold() for m in detect_email(text)})

HERO = "budi.santoso@pertamina.com"
SECOND = "siti.wijaya@pertamina.com"


def _middleware(monkeypatch, **kwargs) -> list:
    """The middleware list `init_agent` hands to `create_deep_agent`.

    Everything that would reach the network or a workspace is stubbed; the
    point is the wiring, not the graph.
    """
    captured: dict = {}

    def fake_create(**kw):
        captured.update(kw)
        return object()

    async def no_tools(*_, **__):
        return []

    monkeypatch.setattr(agent_mod, "create_deep_agent", fake_create)
    monkeypatch.setattr(agent_mod, "ChatDatabricks", lambda **kw: object())
    monkeypatch.setattr(agent_mod, "build_backend", lambda *a, **kw: object())
    monkeypatch.setattr(agent_mod, "mcp_tools", no_tools)
    asyncio.run(agent_mod.init_agent(**kwargs))
    return captured["middleware"]


def _net(monkeypatch, **kwargs):
    for m in _middleware(monkeypatch, **kwargs):
        if isinstance(m, PIIMiddleware):
            return m
    return None


def _rows(*pairs) -> str:
    """Grouped rows as the SQL tool returns them: JSON, one array per row."""
    return "\n".join(f'["{who}", {n}]' for who, n in pairs)


def _keys(content: str) -> set[str]:
    """The identity key of each row, however it was rewritten."""
    return {line.split('", ')[0].split('["')[-1] if '["' in line else line
            for line in content.splitlines() if line.strip()}


# Rows are JSON, not pipe-delimited, on purpose: langchain's built-in email
# pattern ends `[A-Z|a-z]{2,}`, a character class that literally contains a
# pipe, so a `|` immediately after the TLD is swallowed into the match. See
# `test_a_pipe_separator_is_swallowed_upstream`.
def _tool_state(rows: str) -> dict:
    return {
        "messages": [
            AIMessage(content="", tool_calls=[{"name": "sql", "args": {}, "id": "1"}]),
            ToolMessage(content=rows, tool_call_id="1"),
        ]
    }


# ── the wiring ───────────────────────────────────────────────────────────────


def test_the_net_is_on_by_default(monkeypatch):
    """Every served request takes this path — `routes.py` calls `init_agent()`
    with no arguments. An inverted branch here leaves production unprotected
    while every other test still passes."""
    assert _net(monkeypatch) is not None


def test_the_net_is_off_for_evaluation(monkeypatch):
    """With it on, `no_pii_leak` would score the net instead of the model."""
    assert _net(monkeypatch, flag_pii=False) is None


def test_planning_survives_either_way(monkeypatch):
    for kwargs in ({}, {"flag_pii": False}):
        assert any(isinstance(m, TodoListMiddleware)
                   for m in _middleware(monkeypatch, **kwargs)), kwargs


# ── the configuration ────────────────────────────────────────────────────────


def test_detects_email(monkeypatch):
    assert _net(monkeypatch).pii_type == "email"


def test_strategy_is_hash_not_redact(monkeypatch):
    """`redact` collapses every identity to one token, which would destroy the
    grouping the concentration finding depends on."""
    assert _net(monkeypatch).strategy == "hash"


def test_tool_results_are_scrubbed(monkeypatch):
    """The load-bearing setting; see the module docstring."""
    assert _net(monkeypatch).apply_to_tool_results is True


def test_input_is_scrubbed(monkeypatch):
    assert _net(monkeypatch).apply_to_input is True


def test_output_is_still_scrubbed_as_a_backstop(monkeypatch):
    """Reaches non-streaming `ainvoke` callers, where `after_model` applies."""
    assert _net(monkeypatch).apply_to_output is True


def test_url_detection_is_not_enabled(monkeypatch):
    """The OKF `sources:` URLs are citations the format rule requires.

    A regression guard: it fails the moment url detection is added.
    """
    assert all(m.pii_type != "url" for m in _middleware(monkeypatch)
               if isinstance(m, PIIMiddleware))


# ── what the model receives ──────────────────────────────────────────────────


def test_an_address_never_reaches_the_model(monkeypatch):
    out = _net(monkeypatch).before_model(
        _tool_state(_rows((HERO, 701), (SECOND, 54))), None)
    assert out is not None, "tool results must be rewritten before the model call"
    scrubbed = out["messages"][-1].content
    assert identities_in(scrubbed) == []
    assert "@pertamina.com" not in scrubbed


def test_distinct_people_stay_distinct(monkeypatch):
    """The property `hash` buys over `redact`: grouping survives."""
    out = _net(monkeypatch).before_model(
        _tool_state(_rows((HERO, 701), (SECOND, 54))), None)
    assert len(_keys(out["messages"][-1].content)) == 2


def test_the_same_person_hashes_the_same_way(monkeypatch):
    out = _net(monkeypatch).before_model(_tool_state(_rows((HERO, 1), (HERO, 2))), None)
    assert len(_keys(out["messages"][-1].content)) == 1, "one person must not split"


def test_the_d5_lesson_survives(monkeypatch):
    """The digest is over the raw value, so an un-normalised aggregation still
    splits the hero across spellings and still understates the concentration —
    the planted defect is not quietly repaired by the middleware."""
    out = _net(monkeypatch).before_model(_tool_state(_rows(
        (HERO, 1), (HERO.upper(), 1), ("Budi.Santoso@pertamina.com", 1))), None)
    assert len(_keys(out["messages"][-1].content)) > 1, \
        "normalising for the agent would delete the D5 lesson"


def test_an_address_in_the_question_is_scrubbed(monkeypatch):
    out = _net(monkeypatch).before_model(
        {"messages": [HumanMessage(content=f"Berapa tiket ditutup {HERO}?")]}, None)
    assert out is not None
    assert identities_in(out["messages"][-1].content) == []


# ── the answer, for non-streaming callers ────────────────────────────────────


def test_an_address_in_the_answer_is_scrubbed_under_ainvoke(monkeypatch):
    out = _net(monkeypatch).after_model(
        {"messages": [AIMessage(content=f"{HERO} closed 701 tickets.")]}, None)
    assert identities_in(out["messages"][-1].content) == []
    assert "701" in out["messages"][-1].content


def test_a_ranked_answer_is_returned_unchanged(monkeypatch):
    ranked = "Peringkat 1 (tertinggi) menutup 701 tiket (23,3 %)."
    assert _net(monkeypatch).after_model(
        {"messages": [AIMessage(content=ranked)]}, None) is None


def test_a_cited_source_url_survives(monkeypatch):
    cited = (
        "Target diambil dari `resolution-targets.md` "
        "(https://openwiki.pertamina.ai/itsm/service-level-charter-2026)."
    )
    assert _net(monkeypatch).after_model(
        {"messages": [AIMessage(content=cited)]}, None) is None


def test_a_pipe_separator_is_swallowed_upstream():
    """Documents a bug in langchain's built-in pattern, so nobody rediscovers it.

    The pattern ends `[A-Z|a-z]{2,}` — a character class that literally
    contains `|`, almost certainly meant as alternation. A pipe immediately
    after the TLD is therefore part of the match and disappears into the
    digest, corrupting the row. Harmless while results are JSON; a trap if the
    separator ever changes.
    """
    from langchain.agents.middleware._redaction import detect_email

    assert [m["value"] for m in detect_email(f"{HERO}|701")] == [f"{HERO}|"]
    for sep in (",", '"', " ", ":"):
        assert [m["value"] for m in detect_email(f"{HERO}{sep}701")] == [HERO], sep
