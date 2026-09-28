"""The VolumeBackend against the real Volume.

The fake in `conftest.py` encodes assumptions about the Files API, and a fake
that has drifted tests nothing. These run only when the Jakarta credentials and
the Volume path are configured.

    uv run pytest tests/test_volume_backend_live.py -q
"""

from __future__ import annotations

import os

from agent_server.env import schema as _schema
from agent_server.env import volume as _workshop_volume


def _volume() -> str:
    return _workshop_volume(_schema())
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv

from agent_server.backends import VolumeBackend

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)

SERVICE_PRINCIPAL = (
    "DATABRICKS_JAKARTA_HOST",
    "DATABRICKS_JAKARTA_CLIENT_ID",
    "DATABRICKS_JAKARTA_CLIENT_SECRET",
)

_configured = (
    os.environ.get("DATABRICKS_JAKARTA_PROFILE")
    or all(os.environ.get(k) for k in SERVICE_PRINCIPAL)
)

pytestmark = pytest.mark.skipif(
    not _configured,
    reason="Jakarta credentials not configured",
)


@pytest.fixture(scope="module")
def live_client():
    """Built the way the agent builds it, so the profile fallback applies."""
    from agent_server.clients import jakarta_workspace_client

    return jakarta_workspace_client()


@pytest.fixture(scope="module")
def live_raw(live_client):
    """The landing tree: what people dropped, in whatever format."""
    return VolumeBackend(live_client, _volume(), "raw")


@pytest.fixture(scope="module")
def live_wiki(live_client):
    """The wiki itself — the OKF bundle the seed populates."""
    return VolumeBackend(live_client, _volume(), "wiki")


@pytest.fixture
def live_notes(live_client):
    return VolumeBackend(
        live_client,
        _volume(),
        "wiki",
    )


# The tier is greenfield and the agent writes to it, so these tests provision
# what they read. Depending on a seeded bundle made them assert files that a
# reset removed, and depending on whatever the agent last wrote would make them
# fail for reasons unrelated to the API.

def _docx_bytes(text: str) -> bytes:
    """A minimal but genuine Word document."""
    import io

    from docx import Document

    doc, buf = Document(), io.BytesIO()
    doc.add_paragraph(text)
    doc.save(buf)
    return buf.getvalue()


TARGETS = """---
type: Service Level Policy
---

# Targets

| Priority | Target (working hours) |
|---|---|
| P2 | 80 |

| Incident | Target (working hours) |
|---|---|
| P1 | 8 |
"""


@pytest.fixture(scope="module")
def fixture_tree(live_wiki, live_raw):
    """A throwaway subtree in both tiers, removed afterwards.

    Module-scoped: one setup and teardown for the whole file, since each write
    is a round trip to another region.
    """
    root = f"/_livetest-{uuid.uuid4().hex[:8]}"
    written = {
        "index": f"{root}/index.md",
        "targets": f"{root}/policies/resolution-targets.md",
        "basis": f"{root}/definitions/duration-basis.md",
    }
    live_wiki.write(written["index"], "# Index\n\n* [Targets](/policies/x.md) - t\n")
    live_wiki.write(written["targets"], TARGETS)
    live_wiki.write(written["basis"], "---\ntype: Definition\n---\n\nworking versus waiting\n")
    raw_docx = f"{root}/policies/SOP-Layanan-IT.docx"
    # A real `.docx`, not a stub with the right extension: `glob` scans by
    # decoding, and `documents.decode()` sends a `.docx` through python-docx —
    # so a file that only looks like one is skipped and never matches.
    live_raw.upload_bytes(raw_docx, _docx_bytes("SOP Layanan IT"))
    written["raw_docx"] = raw_docx
    written["root"] = root
    try:
        yield written
    finally:
        for path in (written["index"], written["targets"], written["basis"]):
            live_wiki.delete(path)
        live_raw.delete(raw_docx)


def test_ls_reports_files_and_directories(live_wiki, fixture_tree):
    root = fixture_tree["root"]
    r = live_wiki.ls(root + "/")
    assert r.error is None, r.error
    by_path = {e["path"]: e for e in r.entries}
    assert by_path[f"{root}/index.md"]["is_dir"] is False
    assert by_path[f"{root}/policies/"]["is_dir"] is True
    # `size` and `modified_at` are best-effort in the protocol; assert the
    # attribute names the fake relies on actually arrive from the API.
    assert by_path[f"{root}/index.md"]["size"] > 0
    assert by_path[f"{root}/index.md"]["modified_at"]


def test_read_returns_the_written_document(live_wiki, fixture_tree):
    r = live_wiki.read(fixture_tree["targets"])
    assert r.error is None, r.error
    body = r.file_data["content"]
    assert "type: Service Level Policy" in body
    assert "| P2 | 80 |" in body
    assert r.start_line == 1


def test_missing_file_maps_to_a_not_found_result(live_wiki):
    """Guards `_describe`'s substring match against the real message."""
    r = live_wiki.read("/definitely-absent.md")
    assert r.error is not None
    assert "not found" in r.error, f"unmapped API error: {r.error}"


def test_grep_finds_the_target_across_the_bundle(live_wiki, fixture_tree):
    r = live_wiki.grep("Target (working hours)")
    assert r.error is None, r.error
    # Two matches in the one file: it carries two tables, each with a header.
    ours = [m for m in r.matches if m["path"] == fixture_tree["targets"]]
    assert len(ours) == 2, r.matches


def test_glob_walks_subdirectories(live_wiki, fixture_tree):
    r = live_wiki.glob("*.md")
    assert r.error is None, r.error
    paths = {m["path"] for m in r.matches}
    assert fixture_tree["targets"] in paths
    assert fixture_tree["basis"] in paths


def test_the_landing_tree_holds_the_non_markdown_source(live_raw, fixture_tree):
    """`raw/` is where a file lands in the format it arrived in."""
    paths = {m["path"] for m in live_raw.glob("*.docx").matches}
    assert fixture_tree["raw_docx"] in paths


def test_the_landing_tree_cannot_see_the_wiki(live_raw, fixture_tree):
    """Each prefix is its own bundle root: a wiki concept is not reachable
    from the tier mounted beside it."""
    paths = {m["path"] for m in live_raw.glob("*.md").matches}
    assert fixture_tree["targets"] not in paths


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
