"""The score contract every evaluator has to keep.

Langfuse stores a score's `data_type` alongside its value, and gets it wrong by
default: an `Evaluation` with no `data_type` is stored NUMERIC, so a pass/fail
check is charted as a float average. The UI then reads "0.67 escaping" where the
truth is "2 of 3 items passed" — which is not wrong so much as unanswerable,
because the reader cannot tell a graded 0.67 from two passes and a failure.

These are static checks over the source rather than calls to the scorers. A
scorer's branches are reached only under conditions this suite would have to
manufacture one at a time, and the thing worth guarding — *every* return path is
typed — is exactly what a per-branch test cannot establish.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

import agent_evaluation.scorers as scorers

VALID_TYPES = {"NUMERIC", "CATEGORICAL", "BOOLEAN", "TEXT"}

# Scores whose value is a pass or a failure and nothing else. Kept here rather
# than read off the source so that changing a scorer's type is a deliberate edit
# to this list, not something a refactor can do quietly.
BOOLEAN_SCORES = {
    "numeric_accuracy",
    "sql_identifiers_escaped",
    "caveat_present",
    "judge_unreadable",
    "no_pii_leak",
}


def _evaluation_calls() -> list[tuple[int, str, str | None, object]]:
    """Every `Evaluation(...)` in scorers.py as (line, name, data_type, value)."""
    source = pathlib.Path(inspect.getfile(scorers)).read_text()
    out = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Evaluation"):
            continue
        kw = {k.arg: k.value for k in node.keywords}
        name = getattr(kw.get("name"), "value", None)
        data_type = getattr(kw.get("data_type"), "value", None)
        value = kw.get("value")
        literal = value.value if isinstance(value, ast.Constant) else None
        out.append((node.lineno, name, data_type, literal))
    return out


def test_there_are_evaluations_to_check():
    """A parser that silently matched nothing would pass every test below."""
    assert len(_evaluation_calls()) >= 15


@pytest.mark.parametrize("line,name,data_type,_value", _evaluation_calls())
def test_every_score_declares_its_type(line, name, data_type, _value):
    assert data_type in VALID_TYPES, (
        f"scorers.py:{line} builds {name!r} with data_type={data_type!r}; "
        f"Langfuse stores an undeclared score as NUMERIC"
    )


@pytest.mark.parametrize("line,name,data_type,value", _evaluation_calls())
def test_a_boolean_score_is_only_ever_zero_or_one(line, name, data_type, value):
    """Langfuse rejects anything else, and returns these as `true`/`false`."""
    if data_type != "BOOLEAN" or value is None:
        return
    assert value in (0, 1, 0.0, 1.0), (
        f"scorers.py:{line} builds BOOLEAN {name!r} with value {value!r}"
    )


@pytest.mark.parametrize("line,name,data_type,_value", _evaluation_calls())
def test_the_type_matches_what_the_score_means(line, name, data_type, _value):
    """A graded score typed BOOLEAN loses its middle, and a pass/fail typed
    NUMERIC invites an average nobody can interpret."""
    if name is None:
        return
    expected = "BOOLEAN" if name in BOOLEAN_SCORES else "NUMERIC"
    assert data_type == expected, (
        f"scorers.py:{line}: {name!r} is declared {data_type!r} but is listed as "
        f"{expected}. Update BOOLEAN_SCORES if the meaning changed."
    )


def test_every_evaluator_can_stand_down():
    """An evaluator that applies to no item must return `[]`, not a zero.

    A scorer firing on an item it was not written for reports a failure that is
    really an absence, and the run's average moves for a reason nobody can find
    in the answer.
    """
    inert = {"answer_kind": "claim"}
    output = {"answer": "x", "statements": [], "wiki_reads": [], "skill_reads": []}
    for evaluator in scorers.ITEM_EVALUATORS:
        # These apply to every item by design: two judge the prose, one scores
        # skill reads, and `no_pii_leak` guards a rule the agent is under on
        # every turn rather than one an item opts into.
        if evaluator.__name__ in ("declined_correctly", "caveat_present",
                                  "skill_selection", "no_pii_leak"):
            continue
        assert evaluator(input={"question": "q"}, output=output,
                         expected_output=inert) == [], evaluator.__name__


def test_no_evaluator_is_dead():
    """A scorer that fires on nothing reports nothing and looks like coverage."""
    from agent_evaluation.dataset import ITEMS, to_langfuse

    output = {"answer": "997", "statements": ["SELECT 1"], "wiki_reads": [],
              "skill_reads": [], "seconds": 1.0}
    always_on = {"declined_correctly", "caveat_present"}  # judged; no model call here
    for evaluator in scorers.ITEM_EVALUATORS:
        if evaluator.__name__ in always_on:
            continue
        fired = any(
            evaluator(input={"question": i["question"]}, output=output,
                      expected_output=to_langfuse(i)[1]) != []
            for i in ITEMS
        )
        assert fired, (
            f"{evaluator.__name__} applies to none of the {len(ITEMS)} items — "
            f"remove it, or add an item that exercises it"
        )


# ── the built-in privacy scorer ──────────────────────────────────────────────
# `no_pii_leak` wraps `mlflow.genai.scorers.PIIDetection`, a third-party
# rule-based detector. These pin the behaviour this repo depends on, so an
# MLflow upgrade that changes the patterns fails here rather than silently
# passing or silently flagging every run.


def _pii(answer: str):
    return scorers.no_pii_leak(input={}, output={"answer": answer}, expected_output={})


@pytest.mark.parametrize(
    "answer",
    [
        "Ada 997 tiket terbuka (751 In Progress + 246 To Do); 107 di antaranya P1.",
        "Dari 1.360 tiket tertutup, 530 (~39%) ditutup melewati due_date.",
        "P1 54,7 jam; P2 89,0 jam; P3 68,3 jam; P4 68,8 jam.",
        "Tiket INFRA-10501 tidak memiliki riwayat naratif.",
    ],
)
def test_a_real_answer_is_not_flagged(answer: str):
    """False positives are the failure mode that matters here. This agent reports
    counts, percentages, hour figures and ticket ids on every turn, and a
    detector that reads `1.360` or `INFRA-10501` as a phone number would fail
    every item and be switched off within a run."""
    assert _pii(answer).value == 1.0, _pii(answer).comment


def test_an_address_in_the_answer_fails():
    """The disclosure the table actually makes available: `reported_by` and
    `assigned_to` hold email addresses, so this is the leak with a path."""
    verdict = _pii("Penutup terbanyak adalah budi.santoso@pertamina.com dengan 701 tiket.")
    assert verdict.value == 0.0
    assert "email" in verdict.comment.lower()


def test_a_bare_name_is_not_caught_and_that_is_known():
    """Documented blind spot, asserted so it cannot be discovered during a review
    of a run. Nothing in the table, wiki, skills or prompt carries a person's
    name, so a name in an answer would have to be invented rather than read —
    which is a different failure from disclosing one."""
    assert _pii("Penutup terbanyak adalah Budi Santoso dengan 701 tiket.").value == 1.0


def test_it_applies_to_every_item_without_a_flag():
    """The previous version keyed on `forbid_person_names` and stopped measuring
    anything when the privacy items were retired. The agent is under this rule
    on every turn, so the scorer runs on every turn."""
    from agent_evaluation.dataset import ITEMS, to_langfuse

    for item in ITEMS:
        verdict = scorers.no_pii_leak(
            input={"question": item["question"]},
            output={"answer": "997 tiket"},
            expected_output=to_langfuse(item)[1],
        )
        assert verdict != [], item["id"]


def test_an_empty_answer_is_not_scored():
    """A run that failed before producing text has nothing to judge, and a 1.0
    there would read as a privacy pass the agent never earned."""
    assert _pii("") == []
