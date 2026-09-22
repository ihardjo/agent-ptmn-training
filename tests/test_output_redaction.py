"""The redaction net on the answer path, and the three places it must not reach.

The net is the layer *under* rule 1, not a replacement for it. Rule 1 requires
identities to be replaced by their rank, which is an aggregation over the whole
result set; substituting a placeholder per occurrence cannot produce it. So a
redaction firing means the agent failed to follow its instructions — which is
why the evaluation runs with the net off and these tests carry it instead.

Every one of the four constructor settings is asserted individually. Three of
them are load-bearing in a way a future reader would not guess, and a silent
flip of any one either breaks the product (`apply_to_tool_results`) or turns a
degraded answer into a failed request (`strategy`).
"""

from __future__ import annotations

from langchain.messages import AIMessage, HumanMessage, ToolMessage

from agent_server.agent import output_redaction

HERO = "budi.santoso@pertamina.com"


def _run_after_model(middleware, messages):
    """Apply the state-level output hook and return the resulting messages."""
    result = middleware.after_model({"messages": messages}, None)
    return result["messages"] if result else messages


# ── 4.1 the configuration itself ─────────────────────────────────────────────


def test_detects_email():
    assert output_redaction().pii_type == "email"


def test_strategy_is_redact_not_block():
    """`block` raises and fails the run; the durable-write guard is recoverable
    by design and this must not be stricter than it."""
    assert output_redaction().strategy == "redact"


def test_input_is_not_scrubbed():
    assert output_redaction().apply_to_input is False


def test_output_is_scrubbed():
    assert output_redaction().apply_to_output is True


def test_tool_results_are_not_scrubbed():
    """Load-bearing: the agent must group by identity to find the distribution."""
    assert output_redaction().apply_to_tool_results is False


# ── 4.2 the answer path ──────────────────────────────────────────────────────


def test_an_address_in_the_answer_is_removed():
    out = _run_after_model(
        output_redaction(), [AIMessage(content=f"{HERO} closed 701 tickets.")]
    )
    assert HERO not in out[-1].content
    assert "701" in out[-1].content


def test_a_ranked_answer_is_returned_unchanged():
    ranked = "Peringkat 1 (tertinggi) menutup 701 tiket (23,3 %)."
    out = _run_after_model(output_redaction(), [AIMessage(content=ranked)])
    assert out[-1].content == ranked


def test_every_case_variant_is_removed():
    for spelling in (
        "BUDI.SANTOSO@PERTAMINA.COM",
        "Budi.Santoso@pertamina.com",
        "budi.santoso@PERTAMINA.COM",
    ):
        out = _run_after_model(
            output_redaction(), [AIMessage(content=f"{spelling} closed 701.")]
        )
        assert spelling not in out[-1].content, spelling


# ── 4.3 what the net must not touch ──────────────────────────────────────────


def test_tool_results_keep_their_identities():
    """Redacting here would collapse every GROUP BY key into one token."""
    rows = "budi.santoso@pertamina.com|701\nsiti.wijaya@pertamina.com|54"
    messages = [
        AIMessage(content="", tool_calls=[{"name": "sql", "args": {}, "id": "1"}]),
        ToolMessage(content=rows, tool_call_id="1"),
    ]
    out = output_redaction().before_model({"messages": messages}, None)
    assert out is None, "before_model must not rewrite tool results"


def test_the_question_is_not_scrubbed():
    messages = [HumanMessage(content=f"Berapa tiket ditutup {HERO}?")]
    assert output_redaction().before_model({"messages": messages}, None) is None


def test_grouping_survives_two_distinct_identities():
    """The property `apply_to_tool_results=False` exists to protect."""
    rows = "budi.santoso@pertamina.com|701\nsiti.wijaya@pertamina.com|54"
    messages = [
        AIMessage(content="", tool_calls=[{"name": "sql", "args": {}, "id": "1"}]),
        ToolMessage(content=rows, tool_call_id="1"),
    ]
    output_redaction().before_model({"messages": messages}, None)
    assert messages[-1].content.count("@") == 2
    assert len({line.split("|")[0] for line in messages[-1].content.splitlines()}) == 2


# ── 4.4 what must never be configured ────────────────────────────────────────


def test_url_detection_is_not_enabled():
    """The OKF `sources:` URLs are the citations the format rule requires.

    Redacting them would break traceability, so this is a regression guard
    rather than a preference: it fails the moment url detection is added.
    """
    assert output_redaction().pii_type != "url"


def test_a_cited_source_url_survives_the_answer():
    cited = (
        "Target diambil dari `resolution-targets.md` "
        "(https://openwiki.pertamina.ai/itsm/service-level-charter-2026)."
    )
    out = _run_after_model(output_redaction(), [AIMessage(content=cited)])
    assert out[-1].content == cited
