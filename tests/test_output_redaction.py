"""The PII net: what it redacts, and that it is on where it should be.

`PIIMiddleware` pseudonymises identities before the model sees them. It is on by
default for serving and off for evaluation, so a scored run measures the model
rather than the net.
"""

from __future__ import annotations

import asyncio

import re

from langchain.agents.middleware import PIIMiddleware, TodoListMiddleware
from langchain.agents.middleware._redaction import detect_email
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain.messages import AIMessage, HumanMessage, ToolMessage

import agent_server.agent as agent_mod
import agent_server.middleware as middleware_mod


def identities_in(text: str) -> list[str]:
    """Addresses disclosed by `text`, detected by shape.

    Was `agent_server.privacy.identities_in`, a closed vocabulary covering both
    the name form and the address form. That module is gone, so this checks the
    address shape only — a name in the text is no longer detected.

    Uses the agent's own pattern, not langchain's. Checking with a different
    pattern from the one under test is how the pipe defect survived a green
    suite once already.
    """
    found = re.findall(middleware_mod.EMAIL_PATTERN, text)
    return sorted({m.casefold() for m in found})

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
    # A real chat model, not a bare object: the same instance is handed to
    # `SummarizationMiddleware`, which calls `with_retry()` on it.
    monkeypatch.setattr(
        agent_mod, "build_model",
        lambda *a, **kw: GenericFakeChatModel(messages=iter([AIMessage(content="ok")])),
    )
    monkeypatch.setattr(agent_mod, "build_backend", lambda *a, **kw: object())
    monkeypatch.setattr(agent_mod, "agent_tools", no_tools)
    asyncio.run(agent_mod.init_agent(**kwargs))
    return captured["middleware"]


def _net(monkeypatch, **kwargs):
    for m in _middleware(monkeypatch, **kwargs):
        if isinstance(m, PIIMiddleware):
            return m
    return None


def _rows(*pairs) -> str:
    """Grouped rows as the SQL tool returns them: a markdown table.

    `system.ai.dbsql` renders a successful result as markdown, not as the
    Statement Execution envelope the previous server returned. These fixtures
    were JSON until that migration, and the change is the whole point: a
    pipe-delimited row is what breaks langchain's built-in pattern, so testing
    against JSON would measure a format production no longer sees.
    """
    head = "|assigned_to|n|\n|-|-|"
    return "\n".join([head, *(f"|{who}|{n}|" for who, n in pairs)])


def _keys(content: str) -> set[str]:
    """The identity key of each row, however it was rewritten.

    The separator matters here: if a hash swallowed the `|` that follows it,
    the row splits into fewer cells and the key comes back glued to the count —
    which is exactly the corruption `EMAIL_PATTERN` exists to prevent.
    """
    keys = set()
    for line in content.splitlines():
        cells = [c for c in line.split("|") if c.strip()]
        if len(cells) == 2 and cells[1].strip().isdigit():
            keys.add(cells[0])
    return keys


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
    """With it on, the model reads pseudonymised tool results and the run scores
    it on data the served agent would not have shown it."""
    assert _net(monkeypatch, flag_pii=False) is None


def test_planning_survives_either_way(monkeypatch):
    for kwargs in ({}, {"flag_pii": False}):
        assert any(isinstance(m, TodoListMiddleware)
                   for m in _middleware(monkeypatch, **kwargs)), kwargs


# ── the configuration ────────────────────────────────────────────────────────


def test_detects_email(monkeypatch):
    assert _net(monkeypatch).pii_type == "email"


def test_strategy_is_redact(monkeypatch):
    """`redact` replaces every address with one constant token.

    It was `mask` until `9d10a75`, and the change is a privacy fix rather than a
    tuning choice: `mask` renders `budi.santoso@****.com`, leaving the local part
    intact. The system prompt forbids exactly that — "a local part alone" — so
    the previous setting leaked the identity it was meant to protect.
    """
    assert _net(monkeypatch).strategy == "redact"


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


def test_every_identity_collapses_to_one_token(monkeypatch):
    """What `redact` trades away: two people are indistinguishable to the model.

    Acceptable because the answer never needs the identity — only the shape of
    the distribution, which survives as separate rows (see the next test).
    """
    out = _net(monkeypatch).before_model(
        _tool_state(_rows((HERO, 701), (SECOND, 54))), None)
    assert len(_keys(out["messages"][-1].content)) == 1


def test_the_ranking_the_answer_needs_still_survives(monkeypatch):
    """The concentration finding is a rank and a share, not a name. Redaction
    rewrites the identity cell and leaves the counts alone, so the rows stay
    separate and ordered — which is all the answer is built from.
    """
    out = _net(monkeypatch).before_model(
        _tool_state(_rows((HERO, 701), (SECOND, 54))), None)["messages"][-1].content
    counts = [c.split("|")[2] for c in out.splitlines() if c.count("|") >= 3
              and c.split("|")[2].strip().isdigit()]
    assert counts == ["701", "54"]


def test_no_fragment_of_an_address_reaches_the_model(monkeypatch):
    """The property `mask` failed. A local part picks the person out as surely
    as the whole address does."""
    out = _net(monkeypatch).before_model(
        _tool_state(_rows((HERO, 701), (SECOND, 54))), None)["messages"][-1].content
    for fragment in ("budi", "santoso", "siti", "wijaya", "pertamina.com"):
        assert fragment not in out.lower(), fragment


def test_one_person_does_not_split_across_rows(monkeypatch):
    """Trivially true under `redact`, which collapses everything — but it was
    the point of `mask` and the assertion still guards the row shape: a match
    that swallowed the separator would leave two differently-mangled cells."""
    out = _net(monkeypatch).before_model(_tool_state(_rows((HERO, 1), (HERO, 2))), None)
    assert len(_keys(out["messages"][-1].content)) == 1, "one person must not split"


def test_the_d5_defect_is_no_longer_visible_downstream(monkeypatch):
    """Under `mask` the three spellings stayed distinct, so a reader of the tool
    output could see the planted duplicate. Under `redact` they collapse.

    Not a regression in the lesson: the defect is meant to be handled in SQL
    with `lower(trim(...))` *before* aggregating, which happens server-side and
    upstream of any redaction. Detecting it by eye in a result the middleware
    has already rewritten was never the mechanism.
    """
    out = _net(monkeypatch).before_model(_tool_state(_rows(
        (HERO, 1), (HERO.upper(), 1), ("Budi.Santoso@pertamina.com", 1))), None)
    assert len(_keys(out["messages"][-1].content)) == 1


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
    digest, corrupting the row.

    This was filed as harmless "while results are JSON". They are not: the
    migration to `system.ai.dbsql` made every successful result a markdown
    table, and the trap sprang. `agent_server.middleware.EMAIL_PATTERN` is the
    answer; the test below is its guard.
    """
    from langchain.agents.middleware._redaction import detect_email

    assert [m["value"] for m in detect_email(f"{HERO}|701")] == [f"{HERO}|"]
    for sep in (",", '"', " ", ":"):
        assert [m["value"] for m in detect_email(f"{HERO}{sep}701")] == [HERO], sep


def test_our_pattern_stops_at_the_pipe():
    """The one difference from upstream, and the reason for the whole file.

    A separator eaten by the match takes the next cell with it. Under `redact`
    the cost is the count rather than the grouping: the row loses a cell, the
    figure the answer was built from disappears into the replacement token, and
    nothing about the output looks wrong.
    """
    assert re.findall(middleware_mod.EMAIL_PATTERN, f"{HERO}|701") == [HERO]
    for sep in ("|", ",", '"', " ", ":"):
        assert re.findall(middleware_mod.EMAIL_PATTERN, f"{HERO}{sep}701") == [HERO], sep
