"""Wiring of the wiki tier into the agent's filesystem.

Read-only on `/wiki/raw/` is enforced by a middleware permission rule and
*not* by the Volume grant, which covers both subdirectories. That makes the
rule load-bearing, so it is tested here at the layer that enforces it rather
than inferred from the backend's own behaviour.
"""

from __future__ import annotations

import pytest
from deepagents.middleware.filesystem import _check_fs_permission

from agent_server.backends import (
    WIKI_MOUNT,
    WIKI_SOURCE_MOUNT,
    build_backend,
    filesystem_permissions,
    wiki_routes,
)
from agent_server.skills import SKILLS_MOUNT


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
    assert _check_fs_permission(rules, "write", f"{WIKI_MOUNT}finding.md") == "allow"


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


def test_no_wiki_routes_without_jakarta_credentials(monkeypatch):
    """The credential is now the only gate. The Volume lives in another
    workspace, so without it there is no tier however the path is spelled."""
    for key in (
        "DATABRICKS_JAKARTA_HOST",
        "DATABRICKS_JAKARTA_CLIENT_ID",
        "DATABRICKS_JAKARTA_CLIENT_SECRET",
        # The local-only profile fallback is a credential too.
        "DATABRICKS_JAKARTA_PROFILE",
    ):
        monkeypatch.delenv(key, raising=False)
    assert wiki_routes() == {}


def test_a_client_that_cannot_be_built_degrades_to_no_tier(monkeypatch):
    """A failure here must cost the tier, not the process."""
    monkeypatch.setattr(
        "agent_server.backends.jakarta_workspace_client",
        lambda: (_ for _ in ()).throw(RuntimeError("bad host")),
    )
    assert wiki_routes() == {}


def test_backend_still_builds_without_the_wiki(monkeypatch):
    for key in ("DATABRICKS_JAKARTA_HOST", "DATABRICKS_JAKARTA_CLIENT_ID",
                "DATABRICKS_JAKARTA_CLIENT_SECRET", "DATABRICKS_JAKARTA_PROFILE"):
        monkeypatch.delenv(key, raising=False)
    be = build_backend()
    assert WIKI_SOURCE_MOUNT not in be.routes
    assert WIKI_MOUNT not in be.routes


# ── 4.4 routing ──────────────────────────────────────────────────────────────


def test_both_wiki_prefixes_are_routed_when_configured(monkeypatch, client):
    assert sorted(wiki_routes(client)) == sorted([WIKI_SOURCE_MOUNT, WIKI_MOUNT])


def test_the_guard_is_on_notes_and_off_on_source(monkeypatch, client):
    routes = wiki_routes(client)


def test_the_bare_wiki_prefix_is_now_the_bundle(monkeypatch, client):
    """`/wiki/` is a route, which reverses what this file used to assert.

    `/wiki/` was left unmounted so a loose `/wiki/x.md` fell through to scratch;
    collapsing that level makes anything written there durable. Kept and
    inverted, so the change is visible rather than silently absent.
    """
    assert "/wiki/" in build_backend(wiki_client=client).routes


def test_a_raw_path_still_reaches_the_landing_tree(monkeypatch, client):
    """The property the whole layout rests on: longest-prefix routing.

    Only the longer match keeps the read-only tier read-only. Shortest-first
    would resolve `/wiki/raw/x.md` into the writable bundle, leaving the deny
    rule guarding a path nothing routes to.
    """
    be = build_backend(wiki_client=client)
    routes = be.routes
    match = max((p for p in routes if "/wiki/raw/x.md".startswith(p)), key=len)
    assert match == WIKI_SOURCE_MOUNT, f"/wiki/raw/x.md routed to {match!r}"
    assert max((p for p in routes if "/wiki/x.md".startswith(p)), key=len) == WIKI_MOUNT
