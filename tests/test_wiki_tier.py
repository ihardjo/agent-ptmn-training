"""Wiring of the wiki tier into the agent's filesystem.

Read-only on `/wiki/openwiki/` is enforced by a middleware permission rule and
*not* by the Volume grant, which covers both subdirectories. That makes the
rule load-bearing, so it is tested here at the layer that enforces it rather
than inferred from the backend's own behaviour.
"""

from __future__ import annotations

import pytest
from deepagents.middleware.filesystem import _check_fs_permission

from agent_server.agent import (
    SKILLS_MOUNT,
    WIKI_NOTES_MOUNT,
    WIKI_SOURCE_MOUNT,
    build_backend,
    filesystem_permissions,
    wiki_routes,
)


@pytest.fixture
def rules():
    return filesystem_permissions()


# ── 4.2 the deny rule ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        f"{WIKI_SOURCE_MOUNT}index.md",
        f"{WIKI_SOURCE_MOUNT}policies/resolution-targets.md",
        f"{WIKI_SOURCE_MOUNT}deeply/nested/new-file.md",
    ],
)
def test_writes_to_the_synced_source_are_denied(rules, path):
    assert _check_fs_permission(rules, "write", path) == "deny"


def test_writes_to_the_notes_tier_are_allowed(rules):
    assert _check_fs_permission(rules, "write", f"{WIKI_NOTES_MOUNT}finding.md") == "allow"


def test_reads_of_the_synced_source_are_allowed(rules):
    """The tier is read-only, not unreadable."""
    assert _check_fs_permission(rules, "read", f"{WIKI_SOURCE_MOUNT}index.md") == "allow"


def test_the_skills_deny_still_holds(rules):
    """Extending the rule must not have cost the guarantee it already made."""
    assert _check_fs_permission(rules, "write", f"{SKILLS_MOUNT}load-path-probe/SKILL.md") == "deny"


def test_a_single_rule_covers_both_read_only_tiers(rules):
    assert len(rules) == 1
    assert sorted(rules[0].paths) == [f"{SKILLS_MOUNT}**", f"{WIKI_SOURCE_MOUNT}**"]


# ── 4.3 the tier is optional ─────────────────────────────────────────────────


def test_no_wiki_routes_without_the_volume_variable(monkeypatch):
    monkeypatch.delenv("DATABRICKS_WIKI_VOLUME", raising=False)
    assert wiki_routes() == {}


def test_no_wiki_routes_without_jakarta_credentials(monkeypatch):
    """The Volume is reached with the SQL tools' credential; absent it, no tier."""
    monkeypatch.setenv("DATABRICKS_WIKI_VOLUME", "/Volumes/c/s/v")
    for key in ("DATABRICKS_JAKARTA_HOST", "DATABRICKS_JAKARTA_CLIENT_ID", "DATABRICKS_JAKARTA_CLIENT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    assert wiki_routes() == {}


def test_a_client_that_cannot_be_built_degrades_to_no_tier(monkeypatch):
    """A failure here must cost the tier, not the process."""
    monkeypatch.setenv("DATABRICKS_WIKI_VOLUME", "/Volumes/c/s/v")
    monkeypatch.setattr(
        "agent_server.agent.jakarta_workspace_client",
        lambda: (_ for _ in ()).throw(RuntimeError("bad host")),
    )
    assert wiki_routes() == {}


def test_backend_still_builds_without_the_wiki(monkeypatch):
    monkeypatch.delenv("DATABRICKS_WIKI_VOLUME", raising=False)
    be = build_backend()
    assert WIKI_SOURCE_MOUNT not in be.routes
    assert WIKI_NOTES_MOUNT not in be.routes


# ── 4.4 routing ──────────────────────────────────────────────────────────────


def test_both_wiki_prefixes_are_routed_when_configured(monkeypatch, client):
    monkeypatch.setenv("DATABRICKS_WIKI_VOLUME", "/Volumes/c/s/v")
    assert sorted(wiki_routes(client)) == sorted([WIKI_SOURCE_MOUNT, WIKI_NOTES_MOUNT])


def test_the_guard_is_on_notes_and_off_on_source(monkeypatch, client):
    monkeypatch.setenv("DATABRICKS_WIKI_VOLUME", "/Volumes/c/s/v")
    routes = wiki_routes(client)


def test_bare_wiki_prefix_is_not_a_route(monkeypatch, client):
    """`/wiki/` itself must fall through to scratch.

    A file only becomes durable at a prefix that says which tier it is in, so a
    loose `/wiki/notes.md` is scratch and dies with the thread rather than
    quietly landing on the Volume.
    """
    monkeypatch.setenv("DATABRICKS_WIKI_VOLUME", "/Volumes/c/s/v")
    assert "/wiki/" not in build_backend(client).routes
