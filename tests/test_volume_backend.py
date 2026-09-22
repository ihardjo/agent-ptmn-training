"""The VolumeBackend's contract with deepagents' BackendProtocol."""

from __future__ import annotations

import pytest

from agent_server.backends import VolumeBackend


# ── 3.1 path resolution and confinement ──────────────────────────────────────


def test_same_relative_path_resolves_into_two_distinct_tiers(client, source, notes, volume_root):
    """One Volume, two subdirectories, two tiers — the whole basis of the split."""
    a, b = source, notes
    assert a._resolve("/notes.md") == f"{volume_root}/openwiki/notes.md"
    assert b._resolve("/notes.md") == f"{volume_root}/notes/notes.md"
    assert a._resolve("/notes.md") != b._resolve("/notes.md")


@pytest.mark.parametrize(
    "escape",
    ["../notes/stolen.md", "/../notes/stolen.md", "/a/../../notes/stolen.md", "/../../../etc/passwd"],
)
def test_traversal_out_of_the_subdirectory_is_refused(client, escape, source):
    with pytest.raises(Exception) as exc:
        source._resolve(escape)
    assert "outside" in str(exc.value)


def test_traversal_inside_the_subdirectory_is_allowed(client, source, volume_root):
    assert source._resolve("/policies/../index.md") == f"{volume_root}/openwiki/index.md"


def test_escape_arrives_as_an_error_result_not_a_raise(client, source, notes):
    """Every public method maps the refusal to a result the agent can read."""
    b = source
    assert "outside" in (b.read("../notes/x.md").error or "")
    assert "outside" in (b.write("../notes/x.md", "x").error or "")
    assert "outside" in (b.delete("../notes/x.md").error or "")
    assert "outside" in (b.ls("../notes").error or "")


# ── 3.2 read window contract ─────────────────────────────────────────────────


def test_read_returns_content_and_sets_start_line(client, source):
    r = source.read("/policies/targets.md")
    assert r.error is None
    assert "Service Level Policy" in r.file_data["content"]
    assert r.start_line == 1
    assert r.end_line == r.total_lines


def test_negative_offset_reads_from_the_first_line(client, source):
    r = source.read("/policies/targets.md", offset=-5)
    assert r.error is None
    assert r.start_line == 1


def test_non_positive_limit_returns_an_uninspected_window(client, source):
    r = source.read("/policies/targets.md", limit=0)
    assert r.error is None
    assert r.no_lines_requested is True
    assert r.start_line is None


def test_offset_past_the_end_is_an_error_result(client, source):
    r = source.read("/policies/targets.md", offset=9999)
    assert r.error is not None and "exceeds file length" in r.error


def test_a_window_in_the_middle_numbers_its_own_gutter(client, source):
    r = source.read("/policies/targets.md", offset=2, limit=2)
    assert (r.start_line, r.end_line) == (3, 4)
    assert r.next_offset == 4


# ── 3.3 writes ───────────────────────────────────────────────────────────────


def test_written_file_reads_back(client, notes):
    b = notes
    assert b.write("/fresh.md", "---\ntype: Observation\n---\n\nbody\n").error is None
    assert "body" in b.read("/fresh.md").file_data["content"]


def test_write_lands_on_the_volume_under_the_right_subdirectory(client, notes, volume_root):
    notes.write("/fresh.md", "x")
    assert f"{volume_root}/notes/fresh.md" in client.files.contents


def test_edit_replaces_and_counts(client, notes):
    b = notes
    r = b.edit("/existing.md", "prior note", "revised note")
    assert r.error is None and r.occurrences == 1
    assert "revised note" in b.read("/existing.md").file_data["content"]


def test_edit_of_a_missing_string_is_an_error_and_changes_nothing(client, notes):
    b = notes
    before = dict(client.files.contents)
    assert b.edit("/existing.md", "absent", "x").error is not None
    assert client.files.contents == before


def test_delete_removes_the_file(client, notes, volume_root):
    b = notes
    assert b.delete("/existing.md").error is None
    assert f"{volume_root}/notes/existing.md" not in client.files.contents


# ── 3.4 search ───────────────────────────────────────────────────────────────


def test_grep_finds_a_string_and_keeps_the_tier_relative_path(client, source):
    r = source.grep("Service Level Policy")
    assert r.error is None
    assert [m["path"] for m in r.matches] == ["/policies/targets.md"]


def test_grep_respects_max_count(client, source):
    r = source.grep("|", max_count=1)
    assert len(r.matches) == 1 and r.truncated is True


def test_glob_matches_at_depth(client, source):
    r = source.glob("*.md")
    paths = sorted(m["path"] for m in r.matches)
    assert paths == ["/index.md", "/policies/targets.md"]


def test_glob_does_not_reach_the_other_tier(client, source):
    """Confinement holds for search, not only for direct addressing."""
    assert all("existing" not in m["path"] for m in source.glob("*.md").matches)


def test_ls_lists_files_and_subdirectories(client, source):
    r = source.ls("/")
    assert r.error is None
    assert {e["path"]: e["is_dir"] for e in r.entries} == {
        "/index.md": False,
        "/policies/": True,
    }


# ── 3.5 failure mapping ──────────────────────────────────────────────────────


def test_missing_file_is_an_error_result(client, source):
    r = source.read("/nope.md")
    assert r.error is not None and "not found" in r.error


def test_unreachable_volume_is_an_error_result_on_every_operation(broken_client, volume_root):
    b = VolumeBackend(broken_client, volume_root, "openwiki")
    assert b.read("/a.md").error is not None
    assert b.write("/a.md", "x").error is not None
    assert b.ls("/").error is not None
    assert b.delete("/a.md").error is not None
    assert b.grep("x").error is not None
    assert b.glob("*.md").error is not None


def test_non_utf8_content_is_reported_not_raised(client, source, volume_root):
    client.files.contents[f"{volume_root}/openwiki/blob.md"] = b"\xff\xfe\x00binary"
    r = source.read("/blob.md")
    assert r.error is not None and "UTF-8" in r.error


# ── 5.3 the notes tier writes conformant OKF ─────────────────────────────────


def test_a_note_written_without_frontmatter_lands_conformant(notes, client, volume_root):
    from agent_server.okf import conformance_errors, parse

    assert notes.write("/finding.md", "Rank 1 holds 23.3% of closures.\n").error is None
    landed = client.files.contents[f"{volume_root}/notes/finding.md"].decode()
    fm, body = parse(landed)
    assert fm["type"], "the write path must supply a type"
    assert fm["generated"]["by"], "the write path must record what produced it"
    assert "23.3%" in body
    assert conformance_errors({"notes/finding.md": landed}) == []


def test_the_actor_recorded_is_the_one_configured(notes, client, volume_root):
    from agent_server.okf import parse

    notes.write("/finding.md", "a finding\n")
    landed = client.files.contents[f"{volume_root}/notes/finding.md"].decode()
    assert parse(landed)[0]["generated"]["by"] == notes._okf_actor


def test_an_edit_keeps_the_document_conformant(notes, client, volume_root):
    from agent_server.okf import conformance_errors

    notes.write("/finding.md", "first version\n")
    assert notes.edit("/finding.md", "first", "second").error is None
    landed = client.files.contents[f"{volume_root}/notes/finding.md"].decode()
    assert conformance_errors({"notes/finding.md": landed}) == []


def test_reserved_filenames_are_not_given_frontmatter(notes, client, volume_root):
    """§8/§9 — an index and a log carry none, so adding it would break the bundle."""
    from agent_server.okf import conformance_errors

    notes.write("/index.md", "# Notes\n\n* [A finding](/notes/finding.md) - a finding\n")
    notes.write("/log.md", "# Log\n\n## 2026-09-18\n* **Creation**: a note.\n")
    docs = {
        "notes/index.md": client.files.contents[f"{volume_root}/notes/index.md"].decode(),
        "notes/log.md": client.files.contents[f"{volume_root}/notes/log.md"].decode(),
    }
    assert not docs["notes/log.md"].startswith("---")
    assert conformance_errors(docs) == []


def test_non_markdown_writes_are_left_alone(notes, client, volume_root):
    notes.write("/data.json", '{"a": 1}\n')
    assert client.files.contents[f"{volume_root}/notes/data.json"].decode() == '{"a": 1}\n'


def test_the_source_tier_does_not_rewrite_content(source):
    """Only the notes tier is a producer; the source tier is a mirror."""
    assert source._okf_actor is None
def test_a_truncated_scan_says_so(client, volume_root, monkeypatch):
    """Otherwise "I stopped looking" is indistinguishable from "nothing there"."""
    import agent_server.backends as backends

    monkeypatch.setattr(backends, "MAX_SCAN_FILES", 1)
    for i in range(4):
        client.files.contents[f"{volume_root}/openwiki/doc{i}.md"] = b"---\ntype: R\n---\n\nneedle\n"
    b = backends.VolumeBackend(client, volume_root, "openwiki")
    assert b.grep("needle").truncated is True
    assert b.glob("*.md").truncated is True


def test_an_untruncated_scan_does_not_claim_truncation(source):
    assert source.grep("Service Level Policy").truncated is False
    assert source.glob("*.md").truncated is False
