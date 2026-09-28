"""Reading configuration out of the environment, tolerantly.

A Jakarta client secret was once rejected with `invalid_client`, which reads as a
revoked credential and sends you to inspect the service principal rather than the
bytes. It had a trailing newline.
"""

from __future__ import annotations

import logging

import pytest

from agent_server.env import env


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("PROBE", raising=False)
    # The "report once" set is module state and would leak between tests.
    from agent_server import env as env_module

    monkeypatch.setattr(env_module, "_REPORTED", set())


@pytest.mark.parametrize(
    "raw",
    ["secret\n", " secret", "secret ", "\tsecret\r\n", "\n secret \n"],
)
def test_surrounding_whitespace_is_stripped(monkeypatch, raw: str):
    """Every shape a hand-written secret arrives in."""
    monkeypatch.setenv("PROBE", raw)
    assert env("PROBE") == "secret"


def test_interior_whitespace_is_left_alone(monkeypatch):
    """Only the edges. A volume path or a name may legitimately contain a
    space, and collapsing it would corrupt a value that was correct."""
    monkeypatch.setenv("PROBE", "  two words  ")
    assert env("PROBE") == "two words"


def test_an_unset_variable_returns_the_default(monkeypatch):
    assert env("PROBE") is None
    assert env("PROBE", "fallback") == "fallback"


@pytest.mark.parametrize("blank", ["", " ", "\n", "\t  \n"])
def test_a_blank_variable_is_treated_as_unset(monkeypatch, blank: str):
    """`app.yaml` and `databricks.yml` can declare a variable with no value,
    which arrives as `""`. Every caller already treats empty as absent, so a
    blank and a single space must not behave differently."""
    monkeypatch.setenv("PROBE", blank)
    assert env("PROBE") is None
    assert env("PROBE", "fallback") == "fallback"


def test_a_stripped_value_is_reported_once(monkeypatch, caplog):
    """Sanitising fixes the run; the log line is what stops the bad value
    living in the secret scope forever."""
    monkeypatch.setenv("PROBE", "secret\n")
    with caplog.at_level(logging.WARNING, logger="agent_server.env"):
        env("PROBE")
        env("PROBE")
        env("PROBE")
    assert len(caplog.records) == 1, "one warning per variable per process"
    assert "PROBE" in caplog.text


def test_the_value_is_never_logged(monkeypatch, caplog):
    """Half of these are credentials. The name identifies the misconfiguration;
    the value would put a secret in the application log."""
    monkeypatch.setenv("PROBE", "  hunter2-do-not-log  ")
    with caplog.at_level(logging.WARNING, logger="agent_server.env"):
        env("PROBE")
    assert "hunter2" not in caplog.text


def test_a_clean_value_says_nothing(monkeypatch, caplog):
    monkeypatch.setenv("PROBE", "secret")
    with caplog.at_level(logging.WARNING, logger="agent_server.env"):
        assert env("PROBE") == "secret"
    assert caplog.records == []


def test_the_credential_path_uses_it(monkeypatch):
    """The end this exists for: a secret with a trailing newline must not reach
    the SDK, because the OAuth endpoint rejects it as a wrong password."""
    seen = {}

    class _Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr("agent_server.clients.WorkspaceClient", _Client)
    monkeypatch.delenv("DATABRICKS_JAKARTA_PROFILE", raising=False)
    monkeypatch.setenv("DATABRICKS_JAKARTA_HOST", "https://example.invalid\n")
    monkeypatch.setenv("DATABRICKS_JAKARTA_CLIENT_ID", " abc-123 ")
    monkeypatch.setenv("DATABRICKS_JAKARTA_CLIENT_SECRET", "s3cret\n")

    from agent_server.clients import jakarta_workspace_client

    jakarta_workspace_client()
    assert seen["host"] == "https://example.invalid"
    assert seen["client_id"] == "abc-123"
    assert seen["client_secret"] == "s3cret"


def test_a_blank_credential_still_means_unconfigured(monkeypatch):
    """A scope entry left empty must degrade to "no Jakarta client", not build
    one with an empty secret and fail at the first call."""
    monkeypatch.delenv("DATABRICKS_JAKARTA_PROFILE", raising=False)
    monkeypatch.setenv("DATABRICKS_JAKARTA_HOST", "https://example.invalid")
    monkeypatch.setenv("DATABRICKS_JAKARTA_CLIENT_ID", "   ")
    monkeypatch.setenv("DATABRICKS_JAKARTA_CLIENT_SECRET", "s3cret")

    from agent_server.clients import jakarta_workspace_client

    assert jakarta_workspace_client() is None
