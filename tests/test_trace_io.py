"""What the Langfuse trace list shows as a run's input and output.

Both columns carried the whole LangGraph state — every message, plus every
skill file seeded into `files` — because Langfuse promotes the root chain
observation's input and output to the trace's. Setting trace-level input and
output directly does not survive: the root chain's overwrite it on ingest, so
the mask, which runs before anything is exported, is the only lever.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent_server import routes
from agent_server.routes import install_mask, trace_config, trim_graph_state

ANSWER = "Ada **121 tiket** berstatus `Blocked`."


def state(messages: list, **extra) -> dict:
    """A graph state: messages plus at least one of the keys that make it huge."""
    return {"messages": messages, "files": {"/skills/x/SKILL.md": "..."}, **extra}


@pytest.fixture(autouse=True)
def _uninstalled(monkeypatch):
    monkeypatch.setattr(routes, "_MASK_INSTALLED", False)


def test_a_graph_state_becomes_its_last_message():
    data = state([HumanMessage("Berapa?"), AIMessage(ANSWER)])
    assert trim_graph_state(data=data) == ANSWER


def test_the_input_side_yields_the_question():
    """One rule covers both columns: the last message on the way in is the turn
    the user just typed, and on the way out it is the answer."""
    assert trim_graph_state(data=state([HumanMessage("Berapa?")])) == "Berapa?"


def test_a_trailing_message_with_no_text_is_skipped():
    """A tool call carries `content=''`, and middleware can append after the
    answer. Neither is the model's last word."""
    data = state([AIMessage(ANSWER), AIMessage("", tool_calls=[])])
    assert trim_graph_state(data=data) == ANSWER


def test_content_blocks_are_flattened():
    """Reasoning models answer in blocks; only the text ones are the answer."""
    data = state([AIMessage([{"type": "reasoning", "reasoning": "hmm"},
                             {"type": "text", "text": ANSWER}])])
    assert trim_graph_state(data=data) == ANSWER


def test_serialized_messages_work_too():
    """The handler passes some payloads already turned into dicts."""
    data = state([{"type": "human", "content": "Berapa?"}, {"type": "ai", "content": ANSWER}])
    assert trim_graph_state(data=data) == ANSWER


def test_a_state_carrying_no_text_is_left_alone():
    """An empty string in the output column would read as an answer the model
    never gave; the payload it did produce is more use than that."""
    data = state([ToolMessage("", tool_call_id="1")])
    assert trim_graph_state(data=data) is data


# ── what the mask must not touch ──────────────────────────────────────────────
# It runs on every observation, not just the root one, so anything that is not
# a graph state has to pass through byte for byte.


@pytest.mark.parametrize(
    "data",
    [
        {"messages": [AIMessage(ANSWER)]},  # a node update: already small
        [HumanMessage("Berapa?"), AIMessage(ANSWER)],  # a generation's prompt
        {"query": "SELECT 1"},  # a tool call's arguments
        {"role": "assistant", "content": ANSWER},  # a generation's output
        "a plain string",
        None,
    ],
)
def test_everything_else_passes_through(data):
    assert trim_graph_state(data=data) is data


# ── installation ──────────────────────────────────────────────────────────────


def test_the_mask_is_bound_before_the_first_handler(monkeypatch):
    """The client is a singleton keyed on the public key and keeps whatever it
    was built with, so a handler constructed first leaves the process unmasked."""
    order: list[str] = []
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.invalid")
    monkeypatch.setattr(routes, "Langfuse", lambda **kw: order.append(f"client:{kw['mask'].__name__}"))
    monkeypatch.setattr(routes, "CallbackHandler", lambda **kw: order.append("handler"))

    trace_config()
    assert order == ["client:trim_graph_state", "handler"]


def test_it_is_bound_once_per_process(monkeypatch):
    """Rebuilding the client per request would warn about multiple instances."""
    calls: list[dict] = []
    monkeypatch.setattr(routes, "Langfuse", lambda **kw: calls.append(kw))
    install_mask()
    install_mask()
    assert len(calls) == 1


def test_no_client_is_built_when_tracing_is_off(monkeypatch):
    """The host gate stays the gate: an unset host must not construct a client
    that would default to Langfuse cloud."""
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.setattr(routes, "Langfuse", lambda **kw: pytest.fail("built a client"))
    assert trace_config() == {}
