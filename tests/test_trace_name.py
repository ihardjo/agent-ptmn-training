"""What a served run is called in Langfuse.

Every trace this app produced was named `LangGraph`, the compiled graph's own
name. A workspace tracing more than one agent cannot tell them apart in the
trace list from that, and the name is the only field the list filters on
without opening a trace.

The mechanism is LangChain's `run_name`, not a Langfuse setting: the handler
takes the root run's name as the trace name. That was verified against a live
Langfuse trace before it was written into `routes.py`; these tests pin the
wiring so it cannot be dropped in a refactor.
"""

from __future__ import annotations

import pytest

from agent_server.routes import DEFAULT_TRACE_NAME, trace_config

HOST = "https://langfuse.example.invalid"


@pytest.fixture(autouse=True)
def _traced(monkeypatch):
    """A host, so `trace_config` does not short-circuit to no tracing."""
    monkeypatch.setenv("LANGFUSE_HOST", HOST)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.delenv("LANGFUSE_TRACE_NAME", raising=False)


def test_the_trace_name_is_passed_as_the_run_name():
    """`run_name` is what Langfuse reads as the trace name. Nothing else in the
    config carries it, so dropping this key silently restores `LangGraph`."""
    assert trace_config()["run_name"] == DEFAULT_TRACE_NAME


def test_the_env_var_overrides_it(monkeypatch):
    monkeypatch.setenv("LANGFUSE_TRACE_NAME", "agent-workshop-ai-default")
    assert trace_config()["run_name"] == "agent-workshop-ai-default"


def test_an_empty_env_var_falls_back_rather_than_naming_traces_nothing(monkeypatch):
    """`app.yaml` can declare a var with no value, which arrives as `""`. A
    default argument would take that literally and name every trace the empty
    string — which is worse than the name it replaced, because it cannot even
    be searched for."""
    monkeypatch.setenv("LANGFUSE_TRACE_NAME", "")
    assert trace_config()["run_name"] == DEFAULT_TRACE_NAME


def test_it_is_read_per_call_not_bound_at_import(monkeypatch):
    """A constant bound at import time cannot be changed by a reload, and the
    deployed app sets this from the environment at startup."""
    monkeypatch.setenv("LANGFUSE_TRACE_NAME", "first")
    assert trace_config()["run_name"] == "first"
    monkeypatch.setenv("LANGFUSE_TRACE_NAME", "second")
    assert trace_config()["run_name"] == "second"


def test_naming_does_not_switch_tracing_on(monkeypatch):
    """The host is the gate and stays the gate. A trace name set without a host
    must not start shipping prompts to Langfuse cloud."""
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.setenv("LANGFUSE_TRACE_NAME", "anything")
    assert trace_config() == {}


def test_the_session_id_still_travels_alongside_it(monkeypatch):
    monkeypatch.setenv("LANGFUSE_TRACE_NAME", "named")
    config = trace_config(session_id="chat-1")
    assert config["run_name"] == "named"
    assert config["metadata"] == {"langfuse_session_id": "chat-1"}
