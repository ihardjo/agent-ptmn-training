"""The evaluation's handling of wiki activity.

Two things are asserted here that are easy to get wrong and invisible when
wrong: that reading the wiki is not counted as a statement against the data
(which would silently break comparability with the v1 baseline), and that the
privacy rule is scored over durable writes as well as over the answer.
"""

from __future__ import annotations

from agent_evaluation.dataset import ITEMS, resolved_sql
from agent_evaluation.runner import (
    SQL_TOOLS,
    WIKI_READ_TOOLS,
    WIKI_WRITE_TOOLS,
    _tool_paths,
)
from agent_evaluation.runner import _write_refused
from agent_evaluation.scorers import _statements, _wiki_reads, no_pii_leak, wiki_was_read


# ── 7.5 wiki reads are not statements ────────────────────────────────────────


def test_the_tool_sets_do_not_overlap():
    """A tool counted as both would be counted twice, or filtered out entirely."""
    assert not SQL_TOOLS & WIKI_READ_TOOLS
    assert not SQL_TOOLS & WIKI_WRITE_TOOLS
    assert not WIKI_READ_TOOLS & WIKI_WRITE_TOOLS


def test_sql_tools_is_an_allowlist_not_a_denylist():
    """The reason wiki reads never inflated the statement count.

    If this ever became a denylist, every new filesystem tool would start
    counting as a statement and the effort figure would drift without anyone
    changing the evaluation.
    """
    for name in ("read_file", "ls", "glob", "grep", "write_todos", "task", "write_file"):
        assert name not in SQL_TOOLS


def test_statement_count_reflects_sql_only():
    output = {
        "statements": ["SELECT 1", "DESCRIBE TABLE t"],
        "wiki_reads": ["/wiki/raw/policies/resolution-targets.md", "/wiki/raw/"],
        "wiki_writes": [{"content": "a note", "refused": False}],
    }
    assert len(_statements(output)) == 2
    assert len(_wiki_reads(output)) == 2


def test_tool_paths_picks_up_the_argument_names_the_tools_use():
    assert _tool_paths({"file_path": "/wiki/notes/a.md"}) == ["/wiki/notes/a.md"]
    assert _tool_paths({"path": "/wiki/raw/"}) == ["/wiki/raw/"]
    assert _tool_paths({"pattern": "/wiki/raw/**"}) == ["/wiki/raw/**"]
    assert _tool_paths({"content": "not a path"}) == []


# ── 7.4 wiki_was_read ────────────────────────────────────────────────────────


def test_a_fabricated_target_scores_zero():
    e = wiki_was_read(
        input={}, output={"answer": "the target is 80 hours", "wiki_reads": []},
        expected_output={"requires_wiki_read": True},
    )
    assert e.value == 0.0


def test_a_read_backed_answer_scores_one():
    e = wiki_was_read(
        input={},
        output={"answer": "x", "wiki_reads": ["/wiki/raw/policies/resolution-targets.md"]},
        expected_output={"requires_wiki_read": True},
    )
    assert e.value == 1.0


def test_a_listing_without_opening_a_document_is_partial():
    e = wiki_was_read(
        input={}, output={"answer": "x", "wiki_reads": ["/wiki/raw/"]},
        expected_output={"requires_wiki_read": True},
    )
    assert e.value == 0.5


def test_the_evaluator_does_not_apply_to_other_items():
    assert wiki_was_read(input={}, output={"answer": "x"}, expected_output={}) == []


# ── 7.6 privacy over durable writes ──────────────────────────────────────────


def _persisted(writes, answer="Rank 1 holds 23%"):
    results = no_pii_leak(
        input={}, output={"answer": answer, "wiki_writes": writes},
        expected_output={"forbid_person_names": True},
    )
    return {r.name: r for r in results}


def test_a_name_that_reaches_the_volume_fails_even_when_the_answer_is_clean():
    by_name = _persisted([{"content": "budi.santoso@pertamina.com holds 23%", "refused": False}])
    assert by_name["no_pii_leak"].value == 1.0, "the answer was clean"
    assert by_name["no_pii_persisted"].value == 0.0, "the write was not"


def test_a_refused_write_does_not_fail_the_item():
    """The evaluator scores what became durable, not what was attempted.

    Note that nothing refuses a write for privacy any more — the write-time
    guard went with `agent_server/privacy.py`. This branch still covers a write
    refused for another reason, and keeps the attempt visible in the comment.
    """
    by_name = _persisted([
        {"content": "budi.santoso@pertamina.com holds 23%", "refused": True},
        {"content": "Rank 1 (tertinggi) holds 23%", "refused": False},
    ])
    assert by_name["no_pii_persisted"].value == 1.0
    assert "refused" in by_name["no_pii_persisted"].comment, "the attempt must stay visible"


def test_only_a_write_that_landed_fails_the_item():
    """Identical content scores differently by outcome: a refused write left
    nothing behind, a landed one disclosed an identity."""
    refused = _persisted([{"content": "budi.santoso@pertamina.com holds 23%", "refused": True}])
    landed = _persisted([{"content": "budi.santoso@pertamina.com holds 23%", "refused": False}])
    assert refused["no_pii_persisted"].value == 1.0
    assert landed["no_pii_persisted"].value == 0.0


def test_the_two_checks_are_reported_separately():
    by_name = _persisted([{"content": "Rank 1 (tertinggi)", "refused": False}], answer="Rank 1")
    assert set(by_name) == {"no_pii_leak", "no_pii_persisted"}


def test_no_write_means_no_persistence_verdict():
    results = no_pii_leak(
        input={}, output={"answer": "Rank 1"},
        expected_output={"forbid_person_names": True},
    )
    assert {r.name for r in results} == {"no_pii_leak"}


# ── 7.1–7.3 the dataset's own shape ──────────────────────────────────────────


def test_the_flipped_items_kept_their_ids_and_gained_a_query():
    for tid, expected in (
        ("q-p2-target-adherence", 14.7),
        ("q-sla-breach-count", 33.0),
        ("q-target-trend", 23.1),
    ):
        item = next(i for i in ITEMS if i["id"] == tid)
        assert item["kind"] == "value"
        assert item["value"] == expected
        assert item["requires_wiki_read"] is True
        assert resolved_sql(item), "an expected value must carry the query that computes it"


def test_the_policy_free_dimensions_are_still_refusals():
    """The wiki supplies policy, not a missing column."""
    for tid in ("q-fastest-squad", "q-defects-per-release"):
        assert next(i for i in ITEMS if i["id"] == tid)["kind"] == "decline"


def test_the_expectations_version_is_recorded_outside_the_dataset_name():
    """The name cannot carry the version; something else has to.

    Langfuse item ids are unique per project, so a renamed dataset cannot reuse
    these ids and the dataset is mutated in place instead. That makes the name a
    permanent misnomer, so the version has to be discoverable elsewhere — and a
    run scored against unknown expectations is not worth much.
    """
    from agent_evaluation.dataset import DATASET_DESCRIPTION, EXPECTATIONS_VERSION

    assert EXPECTATIONS_VERSION
    assert EXPECTATIONS_VERSION in DATASET_DESCRIPTION


def test_ids_are_unique():
    """Seeding upserts by id, so a duplicate would silently overwrite a sibling."""
    ids = [i["id"] for i in ITEMS]
    assert len(ids) == len(set(ids))


def test_the_write_privacy_item_forbids_names_and_is_not_a_decline():
    item = next(i for i in ITEMS if i["id"] == "q-record-concentration-note")
    assert item["forbid_person_names"] is True
    assert item["kind"] != "decline", "recording the finding is required, not optional"


# ── the refusal signal itself ────────────────────────────────────────────────


class _Msg:
    def __init__(self, content="", status=None):
        self.content = content
        self.status = status


def test_a_guard_refusal_is_read_as_refused():
    assert _write_refused(_Msg("Refused: this content names 1 individual(s)"))


def test_a_permission_denial_is_read_as_refused():
    assert _write_refused(_Msg("Error: permission denied for /wiki/raw/x.md"))


def test_an_error_status_is_read_as_refused():
    assert _write_refused(_Msg("something went wrong", status="error"))


def test_a_successful_write_is_not_read_as_refused():
    assert not _write_refused(_Msg("Updated file /wiki/notes/a.md"))
