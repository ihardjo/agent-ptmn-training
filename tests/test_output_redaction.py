"""Pseudonymising staff addresses before the model sees them.

**Read this before changing the configuration.** An earlier version of this
middleware ran on the way *out* (`apply_to_output` with `strategy="redact"`).
Every test here passed, it worked under `ainvoke`, and it protected no served
request at all: both routes stream with
`astream(stream_mode=["updates", "messages"])`, and the answer is emitted token
by token on the `messages` channel *before* `after_model` rewrites state.
langchain's stream transformer would cover that, but it reads langgraph v3
protocol events and never sees legacy `AIMessageChunk` tuples.

The lesson is that a synthetic `AIMessage` cannot tell you whether this works.
`before_model` is the only hook genuinely upstream of token generation, so
`apply_to_tool_results` is what actually holds — if the model never receives an
address it cannot emit one, whatever the transport does next.
"""

from __future__ import annotations

from langchain.messages import AIMessage, HumanMessage, ToolMessage

from agent_server.agent import output_redaction
from agent_server.privacy import identities_in

HERO = "budi.santoso@pertamina.com"
SECOND = "siti.wijaya@pertamina.com"


def _rows(*pairs) -> str:
    """Grouped rows as the SQL tool returns them: JSON, one array per row."""
    return "\n".join(f'["{who}", {n}]' for who, n in pairs)


def _keys(content: str) -> set[str]:
    """The identity key of each row, however it was rewritten."""
    return {line.split('", ')[0].split('["')[-1] if '["' in line else line
            for line in content.splitlines() if line.strip()}


# Rows are shaped like the MCP SQL tool's JSON payload. Not pipe-delimited on
# purpose: langchain's built-in email pattern ends `[A-Z|a-z]{2,}`, a character
# class that literally contains a pipe, so a `|` immediately after the TLD is
# swallowed into the match. Harmless here because real results are JSON, but it
# will quietly mangle a row if anyone switches the separator. See
# `test_a_pipe_separator_is_swallowed_upstream`.
def _tool_state(rows: str):
    return {
        "messages": [
            AIMessage(content="", tool_calls=[{"name": "sql", "args": {}, "id": "1"}]),
            ToolMessage(content=rows, tool_call_id="1"),
        ]
    }


# ── the configuration ────────────────────────────────────────────────────────


def test_detects_email():
    assert output_redaction().pii_type == "email"


def test_strategy_is_hash_not_redact():
    """`redact` collapses every identity to one token, which would destroy the
    grouping the concentration finding depends on. A hash keeps people
    distinct while identifying none of them."""
    assert output_redaction().strategy == "hash"


def test_tool_results_are_scrubbed():
    """The load-bearing setting. This is the only one that protects a served
    request; see the module docstring."""
    assert output_redaction().apply_to_tool_results is True


def test_input_is_scrubbed():
    assert output_redaction().apply_to_input is True


def test_output_is_still_scrubbed_as_a_backstop():
    """Reaches non-streaming `ainvoke` callers, where `after_model` does apply."""
    assert output_redaction().apply_to_output is True


# ── what the model receives ──────────────────────────────────────────────────


def test_an_address_never_reaches_the_model():
    state = _tool_state(_rows((HERO, 701), (SECOND, 54)))
    out = output_redaction().before_model(state, None)
    assert out is not None, "tool results must be rewritten before the model call"
    scrubbed = out["messages"][-1].content
    assert identities_in(scrubbed) == []
    assert "@pertamina.com" not in scrubbed


def test_distinct_people_stay_distinct():
    """The property `hash` buys over `redact`: grouping survives."""
    out = output_redaction().before_model(_tool_state(_rows((HERO, 701), (SECOND, 54))), None)
    keys = _keys(out["messages"][-1].content)
    assert len(keys) == 2, "two people must not collapse into one group"


def test_the_same_person_hashes_the_same_way():
    out = output_redaction().before_model(_tool_state(_rows((HERO, 1), (HERO, 2))), None)
    assert len(_keys(out["messages"][-1].content)) == 1, "one person must not split"


def test_the_d5_lesson_survives():
    """The digest is over the raw value, so an un-normalised aggregation still
    splits the hero across spellings and still understates the concentration —
    the planted defect is not quietly repaired by the middleware."""
    out = output_redaction().before_model(_tool_state(_rows(
        (HERO, 1), (HERO.upper(), 1), (HERO.strip(), 1),
        ("Budi.Santoso@pertamina.com", 1))), None)
    assert len(_keys(out["messages"][-1].content)) > 1, \
        "normalising for the agent would delete the D5 lesson"


def test_an_address_in_the_question_is_scrubbed():
    state = {"messages": [HumanMessage(content=f"Berapa tiket ditutup {HERO}?")]}
    out = output_redaction().before_model(state, None)
    assert out is not None
    assert identities_in(out["messages"][-1].content) == []


# ── the answer, for non-streaming callers ────────────────────────────────────


def test_an_address_in_the_answer_is_scrubbed_under_ainvoke():
    out = output_redaction().after_model(
        {"messages": [AIMessage(content=f"{HERO} closed 701 tickets.")]}, None)
    assert identities_in(out["messages"][-1].content) == []
    assert "701" in out["messages"][-1].content


def test_a_ranked_answer_is_returned_unchanged():
    ranked = "Peringkat 1 (tertinggi) menutup 701 tiket (23,3 %)."
    assert output_redaction().after_model({"messages": [AIMessage(content=ranked)]}, None) is None


# ── what must never be configured ────────────────────────────────────────────


def test_url_detection_is_not_enabled():
    """The OKF `sources:` URLs are the citations the format rule requires.

    A regression guard, not a preference: it fails the moment url detection is
    added.
    """
    assert output_redaction().pii_type != "url"


def test_a_cited_source_url_survives():
    cited = (
        "Target diambil dari `resolution-targets.md` "
        "(https://openwiki.pertamina.ai/itsm/service-level-charter-2026)."
    )
    assert output_redaction().after_model({"messages": [AIMessage(content=cited)]}, None) is None


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
    # The separators actually in use are unaffected.
    for sep in (",", '"', " ", ":"):
        assert [m["value"] for m in detect_email(f"{HERO}{sep}701")] == [HERO], sep
