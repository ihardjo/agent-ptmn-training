"""The `it-agent-eval` dataset: item definitions and seeding.

Holds the **IT Agent scenario set**: five items covering multi-filter counting,
reasoning across the table and the SOP together, a comparison whose finding is
counter-intuitive, an aggregation with no dominant category, and a question the
data cannot answer.

Every expected value here was measured against the loaded table, not invented,
and each numeric item carries the query that recomputes it — so regenerating the
data refreshes the dataset rather than rotting it.

Three things to know before editing items:

- **Ids are stable and load-bearing.** Seeding upserts by id, so changing an id
  creates a second copy of the same question instead of updating it. Langfuse
  ids are also unique per project and stay reserved after deletion, so a retired
  id cannot be brought back — pick one you can live with.

- **Some questions are correctly answered by refusing.** Where the data cannot
  answer, a plausible number is the failure and a refusal naming the gap is the
  pass. Declining an *answerable* item is also scored wrong, so refusing
  broadly does not raise the score.

- **`required_claims` is documentation, not a scorer input.** It is written into
  `expected_output` and is visible to a human reviewing the item, but no scorer
  in `scorers.py` reads it — only `required_caveat` is judged, by
  `caveat_present`, and it takes a single string. So an assertion that must
  affect the score goes in `required_caveat`; `required_claims` carries the
  supporting detail beside it. Writing a load-bearing expectation into
  `required_claims` alone produces an item that looks scored and is not.

`ANSWER_KIND` values drive which evaluators apply to an item:
    value     -- a figure is expected, scored against ground truth
    decline   -- the correct answer names what is missing
    claim     -- the correct answer asserts something unquantified

Usage:
    uv run python -m agent_evaluation.dataset --seed
    uv run python -m agent_evaluation.dataset --show
    uv run python -m agent_evaluation.dataset --check
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re

TABLE = "workshop_ai_platform.default.sdlc_tickets"
DATASET = "it-agent-eval"
# The verifying queries live with the loader that also runs them: they describe
# the table, not the evaluation.
VERIFY_SQL = (pathlib.Path(__file__).resolve().parent.parent
              / "scripts" / "sdlc_tickets_verify.sql")

# Which answer key a run was scored against. Bump it whenever an expectation
# changes, so a recorded score stays interpretable after this file moves on.
EXPECTATIONS_VERSION = "v1"

DATASET_DESCRIPTION = (
    f"[expectations {EXPECTATIONS_VERSION}] Behaviour of the Pertamina "
    f"workshop IT agent over {TABLE} and the OKF wiki bundle on /wiki/. "
    "Five items, each carrying the query that recomputes its expected value: "
    "a multi-filter count; a figure from the table combined with an escalation "
    "rule that exists only in the SOP on /wiki/raw/; a grouped comparison whose "
    "finding is counter-intuitive (P2 is slower than P1); an aggregation whose "
    "honest answer is that no category dominates; and one question the data "
    "cannot answer, where a plausible figure is the failure and a refusal "
    "naming the gap is the pass. "
    "Runs are scored on the agent's own output, with the output redaction net "
    "disabled, so the score measures the model rather than the net."
)


def verify_query(label: str) -> str:
    """Pull a committed query out of sdlc_tickets_verify.sql by its `-- @@` label.

    Referencing rather than copying: a query that exists in two places drifts,
    and the copy in the eval would be the one nobody re-runs.
    """
    blocks = [b.strip() for b in VERIFY_SQL.read_text().split("-- @@") if b.strip()]
    for block in blocks:
        head, _, body = block.partition("\n")
        if head.strip().startswith(label):
            sql = "\n".join(
                line for line in body.splitlines()
                if not line.strip().startswith("--")
            ).strip()
            if sql:
                return sql.rstrip(";")
    raise KeyError(f"no verifying query labelled {label!r} in {VERIFY_SQL.name}")


# ── Items ─────────────────────────────────────────────────────────────────────
# The IT Agent scenario set. Each entry: id, question, and the expected outcome.
# `held_out` is a build-time flag, not stored metadata — it becomes an ARCHIVED
# status in Langfuse.
#
# Every figure below was re-measured against the live table on 2026-09-25; the
# query that recomputes it travels with the item, so `--check` reports drift
# rather than letting the answer key rot.
#
# **Put anything that must actually be scored in `required_caveat`.**
# `required_claims` reaches Langfuse and is read by a human reviewing an item,
# but no scorer consumes it — see the note in the module docstring. Each item
# below therefore carries its load-bearing assertion as the caveat and uses
# `required_claims` for the supporting detail.

ITEMS: list[dict] = [
    # ── 1.1 query and multi-filter ────────────────────────────────────────────
    {
        "id": "q-open-tickets-and-p1",
        "question": (
            "Ada berapa tiket yang masih terbuka (status_category bukan Done), "
            "dan berapa di antaranya berprioritas P1?"
        ),
        # Two filters over one table. Nothing in the menu adds anything, and a
        # read here is wasted work on the simplest question in the set.
        "expected_skills": [],
        "tolerated_skills": [],
        "kind": "value",
        # 751 In Progress + 246 To Do. status_category holds exactly three
        # values and no nulls, so `<> 'Done'` is the whole of "open".
        "value": 997.0,
        "tolerance": 0.0,
        "required_caveat": (
            "that 107 of those open tickets are priority P1"
        ),
        "required_claims": [
            "997 tiket terbuka",
            "751 In Progress dan 246 To Do",
            "107 di antaranya berprioritas P1",
        ],
        "sql": (
            "SELECT COUNT(*) AS open_total, "
            "SUM(CASE WHEN priority = 'P1' THEN 1 ELSE 0 END) AS p1 "
            f"FROM {TABLE} WHERE status_category <> 'Done'"
        ),
    },

    # ── 1.2 two sources: the table and the SOP ────────────────────────────────
    # The only item that cannot be answered from SQL alone. The escalation
    # target is in `/wiki/raw/policies/SOP-Layanan-IT.docx` §5 and nowhere else,
    # so `requires_wiki_read` asks the question the figure cannot: was the SOP
    # read, or was a plausible chain of command invented?
    {
        "id": "q-overdue-share-and-escalation",
        "question": (
            "Berapa persen tiket yang ditutup melewati due_date-nya, dan "
            "menurut SOP, tiket yang melewati SLA seharusnya dieskalasi ke siapa?"
        ),
        # The question asks two things and joins them in one sentence, which is
        # the point of the scenario but also a trap `checking-due-dates` exists
        # to flag: `due_date` is populated on under half the rows and does not
        # vary with priority, so a rate computed from it is not SLA compliance.
        # The rate is still the answer to what was asked — it is a description
        # of the column — and the skill's warning belongs beside it, which is
        # why it sits in `required_claims`. The caveat scores the SOP half,
        # because reading the SOP is the capability this item is here to test.
        "expected_skills": ["checking-due-dates"],
        "tolerated_skills": ["escalating-breaches", "auditing-data-quality"],
        "kind": "value",
        # 530 of 1,360 closed tickets that have a due_date, = 39.0%.
        "value": 39.0,
        # `due_date` is a DATE and `closed_at` a TIMESTAMP, so "melewati
        # due_date" has two honest readings and they differ: comparing the
        # timestamp against midnight counts a ticket closed at 14:00 on its due
        # date as late (530, 39.0%), comparing dates does not (515, 37.9%).
        # Both are accepted — the item scores the analysis, not a choice of
        # boundary nobody stated. The counts are accepted too, for an answer
        # that reports tickets rather than a percentage.
        "acceptable_values": [39.0, 37.9, 530.0, 515.0],
        "tolerance": 0.6,
        "requires_wiki_read": True,
        "required_caveat": (
            "that the SOP escalates a ticket past its SLA to the IT Manager, "
            "and escalates a Critical (P1) breach automatically to the Head of IT"
        ),
        "required_claims": [
            "1.360 tiket tertutup memiliki due_date",
            "530 di antaranya ditutup setelah due_date (~39%)",
            "hanya sebagian tiket yang memiliki due_date, jadi angka ini bukan "
            "kepatuhan SLA",
            "eskalasi ke IT Manager",
            "prioritas kritis yang melewati SLA dieskalasi otomatis ke Head of IT",
        ],
        "sql": (
            "SELECT ROUND(100.0 * SUM(CASE WHEN closed_at > due_date THEN 1 ELSE 0 END) "
            f"/ COUNT(*), 1) AS pct_late FROM {TABLE} "
            "WHERE closed_at IS NOT NULL AND due_date IS NOT NULL"
        ),
    },

    # ── 1.3 tiered analysis with a counter-intuitive finding ──────────────────
    {
        "id": "q-cycle-time-by-priority",
        "question": (
            "Bandingkan rata-rata cycle time antar prioritas. Apakah prioritas "
            "lebih tinggi selalu selesai lebih cepat?"
        ),
        # A grouped average. The trap is not the query, it is stopping at the
        # ranking and reporting the expected story instead of the one the
        # numbers tell.
        "expected_skills": [],
        "tolerated_skills": ["auditing-data-quality"],
        "kind": "value",
        # P1 54.7 · P2 89.0 · P3 68.3 · P4 68.8 hours. Scored on P2 — the
        # highest average, held by the second-highest priority, which is the
        # whole finding. Scoring P1 would pass an answer that never noticed.
        "value": 89.0,
        "tolerance": 0.5,
        "required_caveat": (
            "that the answer is no — P2 has the longest average at about 89 "
            "hours, longer than P1 at about 55 hours, so a higher priority does "
            "not always finish faster"
        ),
        "required_claims": [
            "tidak, prioritas lebih tinggi tidak selalu selesai lebih cepat",
            "P1 54,7 jam", "P2 89,0 jam", "P3 68,3 jam", "P4 68,8 jam",
        ],
        "sql": (
            "SELECT priority, ROUND(AVG(cycle_time_hours), 1) AS avg_hours "
            f"FROM {TABLE} WHERE cycle_time_hours IS NOT NULL "
            "GROUP BY priority ORDER BY priority"
        ),
    },

    # ── 1.4 aggregation, and refusing to force a winner ───────────────────────
    # Asked as "which is the dominant one", and the honest answer is that there
    # is not one: seven causes between 11.4% and 15.6%, with 5.6 points between
    # first and last. Naming Kesalahan Konfigurasi without that qualification is
    # the failure — it is true as a maximum and false as a finding.
    #
    # Scored as a claim rather than a decline: the agent should produce the
    # distribution and say what it shows, not refuse.
    {
        "id": "q-dominant-root-cause-bug",
        "question": "Apa akar masalah (root cause) paling dominan pada tiket bertipe Bug?",
        # `summarising-root-causes` is the skill for this question and says so in
        # its body — "the top row is reliably the most frequent and is not
        # reliably the cause". It is **not in `SELECTED_SKILLS`**, so the agent
        # cannot read it, and naming it as expected would score this item 0.0 on
        # `skill_selection` on every run: a scorer that cannot pass measures
        # nothing. Tolerated instead. Add it to `SELECTED_SKILLS` in
        # `agent_server/skills.py` and this becomes an expectation worth having.
        "expected_skills": [],
        "tolerated_skills": ["summarising-root-causes", "auditing-data-quality"],
        "kind": "claim",
        "required_caveat": (
            "that no single root cause dominates — the causes are spread almost "
            "evenly and the largest accounts for only about 16% of Bug tickets"
        ),
        "required_claims": [
            "tidak ada satu root cause yang dominan",
            "Kesalahan Konfigurasi teratas dengan 135 dari 865 tiket Bug (~15,6%)",
            "tujuh penyebab tersebar antara ~11% dan ~16%",
        ],
        # Cannot be answered without escaping this identifier.
        "requires_escaped": "Custom Field (Root Cause)",
        "sql": (
            "SELECT `Custom Field (Root Cause)` AS rc, COUNT(*) c, "
            "ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) pct "
            f"FROM {TABLE} WHERE ticket_type = 'Bug' GROUP BY rc ORDER BY c DESC"
        ),
    },

    # ── 1.5 the data cannot answer ────────────────────────────────────────────
    {
        "id": "q-ticket-cost-and-csat",
        "question": (
            "Berapa biaya penyelesaian tiap tiket dan berapa skor kepuasan "
            "(CSAT) pelapornya?"
        ),
        # Nothing in the menu supplies a column the table does not have. A read
        # here is wasted, and the wiki holds policy rather than a missing field.
        "expected_skills": [],
        "tolerated_skills": [],
        "kind": "decline",
        # Two absent facts, not one. An answer that declines the cost and then
        # invents a satisfaction score has still failed, so the gap is named as
        # a pair. `Time Spent (hours)` is the near miss: effort is recorded,
        # money never is, and converting one to the other needs a rate the
        # table does not hold either.
        "missing_fact": (
            "any cost or spend field and any CSAT or satisfaction score — the "
            "table records effort in hours but never money, and holds no "
            "feedback from the reporter at all"
        ),
    },
]


EXTRACT: dict[str, tuple[int, int, float]] = {
    # priority | avg_hours, one row per priority ordered P1..P4. The finding is
    # P2's average, so the second row's second column — not the first row, whose
    # first column is the priority label and cannot be a float.
    "q-cycle-time-by-priority": (1, 1, 1.0),
}
DEFAULT_EXTRACT = (0, 0, 1.0)


def resolved_sql(item: dict) -> str | None:
    """The query that recomputes this item's expected value, if it has one."""
    if item.get("sql"):
        return item["sql"]
    if item.get("sql_ref"):
        return verify_query(item["sql_ref"])
    return None


def to_langfuse(item: dict) -> tuple[dict, dict]:
    """Split an item definition into Langfuse `input` and `expected_output`."""
    expected: dict = {"answer_kind": item["kind"]}

    if item["kind"] == "value":
        expected["ground_truth_value"] = item["value"]
        expected["tolerance"] = item["tolerance"]
        if item.get("acceptable_values"):
            expected["acceptable_values"] = item["acceptable_values"]
    if item["kind"] == "decline":
        expected["must_decline"] = True
        expected["missing_fact"] = item["missing_fact"]

    # Only what a scorer reads, plus `required_claims`, which is documentation
    # for whoever opens the item in Langfuse. `forbid_person_names`,
    # `forbid_mutation`, `naive_values`, `duration_measure` and
    # `partial_decline` were forwarded until the scorers that read them were
    # removed; a key nothing consumes is a field that looks like an expectation.
    for key in ("required_claims", "required_caveat", "requires_escaped",
                "requires_wiki_read", "expected_skills", "tolerated_skills"):
        if item.get(key) is not None:
            expected[key] = item[key]

    if (sql := resolved_sql(item)) is not None:
        expected["ground_truth_sql"] = sql

    return {"question": item["question"]}, expected


def seed() -> None:
    from dotenv import load_dotenv
    from langfuse import Langfuse

    load_dotenv()
    client = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ["LANGFUSE_HOST"],
    )
    if not client.auth_check():
        raise RuntimeError("Langfuse credentials rejected")

    # create_dataset upserts by name, so this is safe to re-run.
    client.create_dataset(name=DATASET, description=DATASET_DESCRIPTION)
    print(f"dataset {DATASET} ready")

    for item in ITEMS:
        payload, expected = to_langfuse(item)
        client.create_dataset_item(
            dataset_name=DATASET,
            id=item["id"],                      # upsert key
            input=payload,
            expected_output=expected,
        )
    client.flush()
    print(f"upserted {len(ITEMS)} items")


def show() -> None:
    print(f"\n── {len(ITEMS)} items ──")
    for item in ITEMS:
        kind = item["kind"]
        extra = []
        if item.get("requires_escaped"):
            extra.append("escaping")
        if item.get("requires_wiki_read"):
            extra.append("wiki")
        if item.get("required_caveat"):
            extra.append("caveat")
        tag = f"  [{', '.join(extra)}]" if extra else ""
        print(f"  {item['id']:<32} {kind:<8}{tag}")
        if resolved_sql(item) is None and kind == "value":
            raise AssertionError(f"{item['id']} expects a value with no query to recompute it")


def check(refresh: bool = False) -> None:
    """Re-run every item's query and compare against its stored expected value."""
    from databricks.sdk import WorkspaceClient

    from scripts.load_sdlc_tickets import DEFAULT_PROFILE, DEFAULT_WAREHOUSE, run

    client = WorkspaceClient(profile=DEFAULT_PROFILE)
    drifted: list[tuple[str, float, float]] = []

    for item in ITEMS:
        if item["kind"] != "value":
            continue
        sql = resolved_sql(item)
        rows = run(client, DEFAULT_WAREHOUSE, sql)
        r, c, scale = EXTRACT.get(item["id"], DEFAULT_EXTRACT)
        actual = round(float(rows[r][c]) * scale, 2)
        stored = item["value"]
        ok = abs(actual - stored) <= max(item["tolerance"], 0.01)
        print(f"  {item['id']:<32} stored {stored:>9.2f}  actual {actual:>9.2f}  "
              f"{'ok' if ok else '** DRIFT **'}")
        if not ok:
            drifted.append((item["id"], stored, actual))

    if not drifted:
        print("\nall expected values match the live table")
        return
    print(f"\n{len(drifted)} item(s) drifted:")
    for ident, stored, actual in drifted:
        print(f"  {ident}: {stored} -> {actual}")
    if refresh:
        print("\nRefresh does not rewrite this file. Update ITEMS deliberately, "
              "so a change in the data is a reviewed edit rather than a silent one.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", action="store_true", help="create/upsert the dataset")
    ap.add_argument("--show", action="store_true", help="list items without touching Langfuse")
    ap.add_argument("--check", action="store_true",
                    help="re-derive every expected value from the table and report drift")
    ap.add_argument("--refresh", action="store_true",
                    help="alias for --check; reports what moved without rewriting")
    args = ap.parse_args()
    if args.show:
        show()
    if args.check or args.refresh:
        check(refresh=args.refresh)
    if args.seed:
        seed()
    if not (args.seed or args.show or args.check or args.refresh):
        ap.error("pass --seed, --show, --check, or --refresh")


if __name__ == "__main__":
    main()
