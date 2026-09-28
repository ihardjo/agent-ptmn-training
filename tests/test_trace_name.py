"""What a served run is called in Langfuse.

Every trace arrived as `LangGraph`, the compiled graph's own name, so eight
group instances tracing to one project were indistinguishable in the trace list
— and the name is the only field that list filters on without opening a trace.
The mechanism is LangChain's `run_name`, which the handler reads as the trace
name; there is no Langfuse-side setting for it.
"""

from __future__ import annotations

import pytest

from agent_server.routes import trace_config, trace_name

HOST = "https://langfuse.example.invalid"


@pytest.fixture(autouse=True)
def _traced(monkeypatch):
    """A host, so `trace_config` does not short-circuit to no tracing."""
    monkeypatch.setenv("LANGFUSE_HOST", HOST)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.delenv("WORKSHOP_GROUP", raising=False)


def test_the_name_is_derived_from_the_group(monkeypatch):
    """One value drives it, and in the app's own form: the trace name is exactly
    the app name, so a trace can be matched to the app that produced it."""
    monkeypatch.setenv("WORKSHOP_GROUP", "group-3")
    assert trace_name() == "agent-workshop-ai-group-3"


def test_it_follows_the_default_schema_when_unset():
    assert trace_name() == "agent-workshop-ai-default"


def test_the_name_is_passed_as_the_run_name(monkeypatch):
    """`run_name` is what Langfuse reads. Nothing else in the config carries it,
    so dropping the key silently restores `LangGraph`."""
    monkeypatch.setenv("WORKSHOP_GROUP", "group-5")
    assert trace_config()["run_name"] == "agent-workshop-ai-group-5"


def test_every_group_gets_a_distinguishable_name(monkeypatch):
    """The whole point: eight instances in one Langfuse project."""
    seen = set()
    for i in range(8):
        monkeypatch.setenv("WORKSHOP_GROUP", f"group-{i}")
        seen.add(trace_name())
    assert len(seen) == 8


def test_it_is_read_per_call_not_bound_at_import(monkeypatch):
    """A constant bound at import cannot be changed by a reload, and the
    deployed app sets the schema from the environment at startup."""
    monkeypatch.setenv("WORKSHOP_GROUP", "group-1")
    assert trace_name() == "agent-workshop-ai-group-1"
    monkeypatch.setenv("WORKSHOP_GROUP", "group-2")
    assert trace_name() == "agent-workshop-ai-group-2"


def test_naming_does_not_switch_tracing_on(monkeypatch):
    """The host is the gate and stays the gate: a run must not start shipping
    prompts to Langfuse cloud just because it has a name."""
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    assert trace_config() == {}


def test_the_session_id_still_travels_alongside_it(monkeypatch):
    monkeypatch.setenv("WORKSHOP_GROUP", "group-4")
    config = trace_config(session_id="chat-1")
    assert config["run_name"] == "agent-workshop-ai-group-4"
    assert config["metadata"] == {"langfuse_session_id": "chat-1"}


def test_whitespace_in_the_group_does_not_reach_the_trace_name(monkeypatch):
    """It arrives from a YAML value; a trailing newline would otherwise produce
    a name no trace-list filter matches."""
    monkeypatch.setenv("WORKSHOP_GROUP", " group-6\n")
    assert trace_name() == "agent-workshop-ai-group-6"
