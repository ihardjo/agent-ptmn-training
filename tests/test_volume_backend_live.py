"""The VolumeBackend against the real Volume.

The fake in `conftest.py` encodes assumptions about the Files API — what a
missing file raises, what a directory entry carries — and a fake that has
drifted from the API tests nothing. These run only when the Jakarta credentials
and the Volume path are configured, which is also the condition under which the
tier exists at all.

    uv run pytest tests/test_volume_backend_live.py -q
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv

from agent_server.backends import VolumeBackend

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)

REQUIRED = (
    "DATABRICKS_JAKARTA_HOST",
    "DATABRICKS_JAKARTA_CLIENT_ID",
    "DATABRICKS_JAKARTA_CLIENT_SECRET",
    "DATABRICKS_WIKI_VOLUME",
)

pytestmark = pytest.mark.skipif(
    not all(os.environ.get(k) for k in REQUIRED),
    reason="Jakarta credentials or DATABRICKS_WIKI_VOLUME not configured",
)


@pytest.fixture(scope="module")
def live_client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(
        host=os.environ["DATABRICKS_JAKARTA_HOST"],
        client_id=os.environ["DATABRICKS_JAKARTA_CLIENT_ID"],
        client_secret=os.environ["DATABRICKS_JAKARTA_CLIENT_SECRET"],
        auth_type="oauth-m2m",
    )


@pytest.fixture(scope="module")
def live_source(live_client):
    return VolumeBackend(live_client, os.environ["DATABRICKS_WIKI_VOLUME"], "raw")


@pytest.fixture
def live_notes(live_client):
    return VolumeBackend(
        live_client,
        os.environ["DATABRICKS_WIKI_VOLUME"],
        "notes",
    )


def test_ls_reports_files_and_directories(live_source):
    r = live_source.ls("/")
    assert r.error is None, r.error
    by_path = {e["path"]: e for e in r.entries}
    assert by_path["/index.md"]["is_dir"] is False
    assert by_path["/policies/"]["is_dir"] is True
    # `size` and `modified_at` are best-effort in the protocol; assert the
    # attribute names the fake relies on actually arrive from the API.
    assert by_path["/index.md"]["size"] > 0
    assert by_path["/index.md"]["modified_at"]


def test_read_returns_the_seeded_target(live_source):
    r = live_source.read("/policies/resolution-targets.md")
    assert r.error is None, r.error
    body = r.file_data["content"]
    assert "type: Service Level Policy" in body
    assert "| P2 | 80 |" in body
    assert r.start_line == 1


def test_missing_file_maps_to_a_not_found_result(live_source):
    """Guards `_describe`'s substring match against the real message."""
    r = live_source.read("/definitely-absent.md")
    assert r.error is not None
    assert "not found" in r.error, f"unmapped API error: {r.error}"


def test_grep_finds_the_target_across_the_bundle(live_source):
    r = live_source.grep("Target (working hours)")
    assert r.error is None, r.error
    # Two matches, one file: the concept carries a Bug table and an Incident
    # table, each with its own header row.
    assert {m["path"] for m in r.matches} == {"/policies/resolution-targets.md"}
    assert len(r.matches) == 2


def test_glob_walks_subdirectories(live_source):
    r = live_source.glob("*.md")
    assert r.error is None, r.error
    paths = {m["path"] for m in r.matches}
    assert "/policies/resolution-targets.md" in paths
    assert "/definitions/duration-basis.md" in paths


def test_source_tier_cannot_see_the_notes_tier(live_source):
    assert all("canary" not in m["path"] for m in live_source.glob("*.md").matches)


def test_write_read_and_delete_round_trip(live_notes):
    path = f"/live-test-{uuid.uuid4().hex[:8]}.md"
    body = "---\ntype: Observation\n---\n\nRank 1 (tertinggi) holds 23.3% of closures.\n"
    try:
        assert live_notes.write(path, body).error is None
        assert "23.3%" in live_notes.read(path).file_data["content"]
        assert live_notes.edit(path, "23.3%", "23.4%").occurrences == 1
        assert "23.4%" in live_notes.read(path).file_data["content"]
    finally:
        assert live_notes.delete(path).error is None
    assert live_notes.read(path).error is not None
