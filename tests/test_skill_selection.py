"""The selection scorer, and the query set it scores.

The scorer's one real hazard is the tool/prefix confusion: `read_file` serves
both `/wiki/` and `/skills/`, so a scorer keyed to the tool name would count
every wiki read as a skill read. That would penalise adherence questions for
doing exactly what they are supposed to do, so it gets its own test.
"""

from __future__ import annotations

from agent_evaluation.scorers import _skills_read, skill_selection
from agent_evaluation.skill_selection import ITEMS, MENU, by_skill, coverage_gaps


def score(read_paths, expected=(), tolerated=()):
    return skill_selection(
        input={},
        output={"skill_reads": list(read_paths)},
        expected_output={
            "expected_skills": list(expected),
            "tolerated_skills": list(tolerated),
        },
    )


SKILL_A = "/skills/computing-target-adherence/SKILL.md"
SKILL_B = "/skills/checking-due-dates/SKILL.md"
WIKI = "/wiki/raw/policies/resolution-targets.md"


def test_reads_the_right_skill():
    assert score([SKILL_A], expected=["computing-target-adherence"]).value == 1.0


def test_reads_nothing_when_nothing_applies():
    result = score([], expected=[])
    assert result.value == 1.0
    assert "correctly" in result.comment


def test_missing_a_skill_that_applied_scores_zero():
    result = score([], expected=["computing-target-adherence"])
    assert result.value == 0.0
    assert "did not read" in result.comment


def test_reading_a_surplus_skill_scores_half():
    """A wasted read costs turns; it is not the same failure as not reading."""
    result = score([SKILL_A, SKILL_B], expected=["computing-target-adherence"])
    assert result.value == 0.5
    assert "checking-due-dates" in result.comment
    assert "did not apply" in result.comment


def test_both_directions_at_once_scores_zero():
    result = score([SKILL_B], expected=["computing-target-adherence"])
    assert result.value == 0.0
    assert "did not read" in result.comment
    assert "did not apply" in result.comment


def test_tolerated_skill_is_not_penalised():
    result = score(
        [SKILL_A, SKILL_B],
        expected=["computing-target-adherence"],
        tolerated=["checking-due-dates"],
    )
    assert result.value == 1.0


def test_wiki_reads_are_not_counted_as_skill_reads():
    """The regression this scorer was rebuilt to avoid.

    A wiki read is correct behaviour on an adherence question. Counting it as
    a surplus skill read would fail the item for being right.
    """
    assert _skills_read({"skill_reads": []}) == set()
    result = skill_selection(
        input={},
        output={"skill_reads": [], "wiki_reads": [WIKI]},
        expected_output={"expected_skills": []},
    )
    assert result.value == 1.0


def test_skill_name_recovered_from_path_not_body():
    assert _skills_read({"skill_reads": [SKILL_A, SKILL_B]}) == {
        "computing-target-adherence",
        "checking-due-dates",
    }


def test_repeated_reads_of_one_skill_count_once():
    assert score([SKILL_A, SKILL_A], expected=["computing-target-adherence"]).value == 1.0


# -- the query set itself ---------------------------------------------------


def test_every_skill_has_the_three_required_kinds():
    assert coverage_gaps() == []


def test_item_ids_are_unique():
    ids = [i.id for i in ITEMS]
    assert len(ids) == len(set(ids))


def test_expected_and_tolerated_name_real_skills():
    for item in ITEMS:
        for name in item.expected | item.tolerated:
            assert name in MENU, f"{item.id} names unknown skill {name}"


def test_avoid_items_never_expect_their_own_subject():
    """An 'avoid' item that expects its subject would be testing the opposite."""
    for item in ITEMS:
        if item.kind == "avoid":
            assert item.subject not in item.expected, item.id


def test_menu_is_ten_skills():
    assert len(MENU) == 10
    assert len(set(MENU)) == 10


def test_every_menu_skill_is_someones_subject():
    assert all(items for items in by_skill().values())
