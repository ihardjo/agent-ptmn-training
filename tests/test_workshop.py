"""One value points an instance at its group's data.

Eight instances run side by side, one per branch `group-0` … `group-7`, differing
by `WORKSHOP_GROUP` alone. An instance pointed at the wrong schema reads another
group's tickets and answers confidently from them — nothing errors.
"""

from __future__ import annotations

import logging

import pytest

from agent_server import env as env_module
from agent_server.env import TABLE_PLACEHOLDER, resolve, schema, table, volume


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("WORKSHOP_GROUP", raising=False)
    monkeypatch.setattr(env_module, "_GROUP_REPORTED", False)


def test_unset_resolves_to_default():
    """Today's behaviour, so `main` stays deployable and a local run needs no
    configuration."""
    assert schema() == "default"
    assert table("default") == "workshop_ai_platform.default.sdlc_tickets"


@pytest.mark.parametrize("group", [f"group_{i}" for i in range(8)])
def test_every_group_derives_its_own_table_and_volume(monkeypatch, group: str):
    monkeypatch.setenv("WORKSHOP_GROUP", group)
    assert schema() == group
    assert table(group) == f"workshop_ai_platform.{group}.sdlc_tickets"
    assert volume(group) == f"/Volumes/workshop_ai_platform/{group}/agent_wiki"


def test_the_resolution_is_logged(monkeypatch, caplog):
    """The log line is what makes a misconfiguration checkable, since pointing
    at the wrong schema is otherwise invisible."""
    monkeypatch.setenv("WORKSHOP_GROUP", "group-2")
    with caplog.at_level(logging.INFO, logger="agent_server.env"):
        schema()
        schema()
    assert len(caplog.records) == 1, "once per process, not once per call"
    assert "group_2" in caplog.text


def test_whitespace_in_the_variable_does_not_leak_into_a_table_name(monkeypatch):
    """It arrives from a secret scope or a YAML value; a trailing newline would
    otherwise produce `workshop_ai_platform.group_1\\n.sdlc_tickets`."""
    monkeypatch.setenv("WORKSHOP_GROUP", " group-1\n")
    assert schema() == "group_1"
    assert "\n" not in table(schema())


# ── the markdown substitution ────────────────────────────────────────────────


def test_the_placeholder_is_replaced(monkeypatch):
    monkeypatch.setenv("WORKSHOP_GROUP", "group-4")
    out = resolve(f"SELECT COUNT(*) FROM {TABLE_PLACEHOLDER}")
    assert out == "SELECT COUNT(*) FROM workshop_ai_platform.group_4.sdlc_tickets"


def test_text_without_a_placeholder_is_untouched():
    """`resolve` runs over every skill, including the ones that name no table."""
    body = "# A skill\n\nNo SQL here.\n"
    assert resolve(body) is body


def test_no_placeholder_reaches_the_model(monkeypatch):
    """The whole point. A skill on disk is not what the model sees, so a
    substitution that silently failed would put `{{TABLE}}` into SQL."""
    import agent_server.skills as sk

    monkeypatch.setenv("WORKSHOP_GROUP", "group-6")
    names = sorted(p.parent.name for p in sk.SKILLS_DIR.glob("*/SKILL.md"))
    monkeypatch.setattr(sk, "SELECTED_SKILLS", tuple(names))
    for path, data in sk.skill_files().items():
        body = data["content"]
        body = "".join(body) if isinstance(body, list) else body
        assert TABLE_PLACEHOLDER not in body, f"{path} still carries the placeholder"
        assert "workshop_ai_platform.default." not in body, f"{path} is pinned to default"


def test_the_system_prompt_is_substituted_too(monkeypatch):
    """The prompt names the table in SQL the model copies, exactly as a skill
    does, and is read through a different seam."""
    import importlib

    monkeypatch.setenv("WORKSHOP_GROUP", "group-7")
    import agent_server.agent as agent_mod

    reloaded = importlib.reload(agent_mod)
    assert TABLE_PLACEHOLDER not in reloaded.SYSTEM_PROMPT
    assert "workshop_ai_platform.group_7.sdlc_tickets" in reloaded.SYSTEM_PROMPT
    monkeypatch.delenv("WORKSHOP_GROUP")
    importlib.reload(agent_mod)


# ── the Volume ───────────────────────────────────────────────────────────────


def test_the_volume_derives_from_the_schema(monkeypatch):
    """No second variable to disagree with `WORKSHOP_GROUP`."""
    from agent_server.backends import wiki_routes

    monkeypatch.setenv("WORKSHOP_GROUP", "group-5")
    routes = wiki_routes(client=object())
    assert routes, "the tier should exist once a client is available"
    assert all("/group_5/agent_wiki" in repr(b) for b in routes.values()), routes


def test_the_upload_backend_derives_the_same_path(monkeypatch):
    """The upload route holds its own backend; it must land in the same group."""
    from agent_server.backends import uploads_backend

    monkeypatch.setenv("WORKSHOP_GROUP", "group-5")
    assert "/group_5/agent_wiki/raw" in repr(uploads_backend(client=object()))
