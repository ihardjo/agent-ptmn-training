"""The evaluation's handling of wiki activity.

What is asserted here is easy to get wrong and invisible when wrong: that
reading the wiki is not counted as a statement against the data, and that
opening a document is distinguished from merely listing the tier — including
when the document is the `.docx` SOP, which is where the one fact no SQL query
can supply actually lives.

The privacy-over-durable-writes checks that used to sit here went with
`no_pii_leak`, which no current dataset item exercises. `PIIMiddleware` is
tested directly in `test_output_redaction.py`.
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
from agent_evaluation.scorers import _statements, _wiki_reads, wiki_was_read


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
        "wiki_reads": ["/wiki/notes/policies/resolution-targets.md", "/wiki/raw/"],
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
        output={"answer": "x", "wiki_reads": ["/wiki/notes/policies/resolution-targets.md"]},
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


# ── 7.1–7.3 the dataset's own shape ──────────────────────────────────────────


def test_the_two_source_item_needs_both_sources():
    """The one item neither source answers alone.

    The percentage is in the table and the escalation chain is only in
    `/wiki/raw/policies/SOP-Layanan-IT.docx`, so the item has to demand both: a
    query that recomputes the figure, and `requires_wiki_read` to tell an agent
    that consulted the SOP from one that produced a plausible chain of command.
    """
    item = next(i for i in ITEMS if i["id"] == "q-overdue-share-and-escalation")
    assert item["kind"] == "value"
    assert item["value"] == 39.0
    assert item["requires_wiki_read"] is True
    assert resolved_sql(item), "an expected value must carry the query that computes it"


def test_the_sop_is_a_docx_and_still_counts_as_a_document_read():
    """`wiki_was_read` filtered to `.md`, which scored the correct behaviour 0.5.

    The escalation rule lives in a Word document because that is the format a
    person dropped it in, and `/wiki/raw/` keeps what it was given. An item
    whose fact is only in a `.docx` cannot be passed by a scorer that counts
    only `.md` as having been opened.
    """
    verdict = wiki_was_read(
        input={}, expected_output={"requires_wiki_read": True},
        output={"wiki_reads": ["/wiki/raw/policies/SOP-Layanan-IT.docx"]},
    )
    assert verdict.value == 1.0, verdict.comment


def test_listing_the_wiki_is_still_not_reading_it():
    """The half of that filter which was doing real work stays."""
    verdict = wiki_was_read(
        input={}, expected_output={"requires_wiki_read": True},
        output={"wiki_reads": ["/wiki/raw/policies/"]},
    )
    assert verdict.value == 0.5, verdict.comment


def test_the_unanswerable_item_is_a_refusal():
    """The table records effort in hours; it holds no money and no CSAT. A
    plausible figure is the failure here, and the refusal has to name both gaps
    — declining the cost and then inventing a satisfaction score still fails."""
    item = next(i for i in ITEMS if i["id"] == "q-ticket-cost-and-csat")
    assert item["kind"] == "decline"
    assert "cost" in item["missing_fact"] and "CSAT" in item["missing_fact"]


def test_the_expectations_version_travels_with_the_dataset():
    """A run scored against unknown expectations is not worth much.

    The dataset is mutated in place — ids are stable so that a run stays
    comparable to an earlier one item by item — so the answer key can move under
    a recorded score. The version is what makes that visible, and it has to be
    somewhere a reader of the dataset will find it.
    """
    from agent_evaluation.dataset import DATASET_DESCRIPTION, EXPECTATIONS_VERSION

    assert EXPECTATIONS_VERSION
    assert EXPECTATIONS_VERSION in DATASET_DESCRIPTION


def test_ids_are_unique():
    """Seeding upserts by id, so a duplicate would silently overwrite a sibling."""
    ids = [i["id"] for i in ITEMS]
    assert len(ids) == len(set(ids))


def test_every_load_bearing_expectation_is_scored():
    """`required_claims` reaches Langfuse and no scorer reads it; only
    `required_caveat` is judged. An item whose expectation is not a figure and
    not a refusal therefore needs a caveat, or it looks scored and is not."""
    for item in ITEMS:
        if item["kind"] in ("value", "decline"):
            continue
        assert item.get("required_caveat"), (
            f"{item['id']} is a claim with nothing that scores it: "
            f"required_claims is documentation, not a scorer input"
        )


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
