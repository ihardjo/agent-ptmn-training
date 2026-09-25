"""The skill-selection query set.

Answer quality and skill selection fail independently. An agent can reach the
right number after reading three skills that did not apply, and no answer-based
score notices. This set measures the reading.

Per the published standard, each skill carries 3-5 representative queries
spanning three kinds:

    trigger    the skill should be read
    avoid      the skill should not be read
    ambiguous  the description plausibly matches but another skill fits better,
               or nothing does

`expected` is the set of skills that *should* be read. An empty set means the
correct behaviour is to read nothing. `tolerated` names skills whose reading is
not counted against the agent -- used where a distractor's description is a
genuinely reasonable match and the recovery, not the initial choice, is what is
being measured.

This set is deliberately **separate from the Langfuse answer-quality dataset**.
Mixing them would change the denominator of every recorded score and break
comparison with the baseline, and the two measure different things.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CORE = [
    "computing-target-adherence",
    "auditing-data-quality",
    "splitting-planned-unplanned-work",
    "measuring-sprint-velocity",
    "escalating-breaches",
    "summarising-root-causes",
]

DISTRACTORS = [
    "checking-due-dates",
    "explaining-ticket-history",
    "ranking-squad-performance",
    "formatting-service-review",
]

MENU = CORE + DISTRACTORS


@dataclass(frozen=True)
class SelectionItem:
    id: str
    question: str
    kind: str  # trigger | avoid | ambiguous
    subject: str  # the skill this item was written for
    expected: frozenset[str] = frozenset()
    tolerated: frozenset[str] = field(default_factory=frozenset)
    note: str = ""


def _i(id, question, kind, subject, expected=(), tolerated=(), note=""):
    return SelectionItem(
        id=id,
        question=question,
        kind=kind,
        subject=subject,
        expected=frozenset(expected),
        tolerated=frozenset(tolerated),
        note=note,
    )


ADHERENCE = "computing-target-adherence"
DUE_DATES = "checking-due-dates"

ITEMS: list[SelectionItem] = [
    # -- computing-target-adherence ------------------------------------------
    _i("sel-adherence-trigger-1",
       "Apakah kita sudah memenuhi target penyelesaian untuk Bug prioritas P2?",
       "trigger", ADHERENCE, expected=[ADHERENCE]),
    _i("sel-adherence-trigger-2",
       "Berapa banyak tiket Incident yang melanggar target penyelesaian kuartal ini?",
       "trigger", ADHERENCE, expected=[ADHERENCE]),
    _i("sel-adherence-avoid",
       "Ada berapa tiket bertipe Bug di project ERP?",
       "avoid", ADHERENCE,
       note="a plain count; no target, no policy, nothing to read"),
    _i("sel-adherence-ambiguous",
       "Ada berapa tiket yang terlambat?",
       "ambiguous", ADHERENCE, expected=[ADHERENCE], tolerated=[DUE_DATES],
       note="'terlambat' matches both. Reading checking-due-dates is tolerated; "
            "ending on due_date as the basis is not"),

    # -- auditing-data-quality -----------------------------------------------
    _i("sel-quality-trigger-1",
       "Apakah data tiket ini bisa dipercaya? Adakah anomali?",
       "trigger", "auditing-data-quality", expected=["auditing-data-quality"]),
    _i("sel-quality-trigger-2",
       "Ada berapa tiket yang tanggal penutupannya lebih awal daripada tanggal pembuatannya?",
       "trigger", "auditing-data-quality", expected=["auditing-data-quality"]),
    _i("sel-quality-avoid",
       "Apa 3 root cause terbanyak untuk tiket bertipe Bug?",
       "avoid", "auditing-data-quality",
       note="a clean aggregation over a populated column"),
    _i("sel-quality-ambiguous",
       "Ada berapa assignee berbeda yang tercatat di tabel ini?",
       "ambiguous", "auditing-data-quality", expected=["auditing-data-quality"],
       note="looks like a plain count; the normalisation defect makes the naive "
            "answer wrong, so the audit skill genuinely applies"),

    # -- splitting-planned-unplanned-work ------------------------------------
    _i("sel-split-trigger-1",
       "Berapa porsi effort yang dipakai untuk pekerjaan tidak terencana?",
       "trigger", "splitting-planned-unplanned-work",
       expected=["splitting-planned-unplanned-work"]),
    _i("sel-split-trigger-2",
       "Bagaimana pembagian kapasitas tim antara delivery dan operasional?",
       "trigger", "splitting-planned-unplanned-work",
       expected=["splitting-planned-unplanned-work"]),
    _i("sel-split-avoid",
       "Ada berapa tiket bertipe Incident?",
       "avoid", "splitting-planned-unplanned-work",
       note="mentions an unplanned type but asks only for a count"),
    _i("sel-split-ambiguous",
       "Berapa banyak story points yang diselesaikan untuk pekerjaan terencana?",
       "ambiguous", "splitting-planned-unplanned-work",
       expected=["measuring-sprint-velocity"],
       tolerated=["splitting-planned-unplanned-work"],
       note="'terencana' pulls toward the split skill; story points make it a "
            "velocity question"),

    # -- measuring-sprint-velocity -------------------------------------------
    _i("sel-velocity-trigger-1",
       "Berapa velocity tim per sprint?",
       "trigger", "measuring-sprint-velocity", expected=["measuring-sprint-velocity"]),
    _i("sel-velocity-trigger-2",
       "Apakah jumlah story points yang selesai per sprint meningkat?",
       "trigger", "measuring-sprint-velocity", expected=["measuring-sprint-velocity"]),
    _i("sel-velocity-avoid",
       "Ada berapa sprint berbeda di tabel ini?",
       "avoid", "measuring-sprint-velocity",
       note="mentions sprint; asks for a distinct count, not a rate"),
    _i("sel-velocity-ambiguous",
       "Apakah story points bisa memprediksi lama pengerjaan sebuah Story?",
       "ambiguous", "measuring-sprint-velocity", expected=[],
       tolerated=["measuring-sprint-velocity"],
       note="a correlation question, not a velocity one; the null-coverage "
            "caveat is relevant but the procedure is not"),

    # -- escalating-breaches -------------------------------------------------
    _i("sel-escalation-trigger-1",
       "Siapa yang harus diberi tahu ketika tiket P1 melanggar target?",
       "trigger", "escalating-breaches", expected=["escalating-breaches"]),
    _i("sel-escalation-trigger-2",
       "Apa jalur eskalasi untuk tiket yang sudah melewati target penyelesaian?",
       "trigger", "escalating-breaches", expected=["escalating-breaches"],
       tolerated=[ADHERENCE],
       note="establishing the breach first is legitimate"),
    _i("sel-escalation-avoid",
       "Ada berapa tiket berstatus Blocked?",
       "avoid", "escalating-breaches",
       note="blocked is not breached; no policy involved"),
    _i("sel-escalation-ambiguous",
       "Apakah pelanggaran target semakin sering terjadi?",
       "ambiguous", "escalating-breaches", expected=[ADHERENCE],
       note="a trend question. The matrix routes individual breaches and "
            "explicitly does not handle trends"),

    # -- summarising-root-causes ---------------------------------------------
    _i("sel-rootcause-trigger-1",
       "Apa penyebab utama tiket-tiket di sistem ini?",
       "trigger", "summarising-root-causes",
       expected=["summarising-root-causes"],
       note="unscoped, so the population is the whole answer: the field applies "
            "to defect work only"),
    _i("sel-rootcause-trigger-2",
       "Masalah mendasar apa yang paling perlu kami perbaiki duluan?",
       "trigger", "summarising-root-causes",
       expected=["summarising-root-causes"],
       note="asks the leading row to carry a conclusion the flat distribution "
            "does not support"),
    _i("sel-rootcause-avoid",
       "Ada berapa tiket bertipe Incident yang ditutup bulan lalu?",
       "avoid", "summarising-root-causes",
       note="defect work, but a count -- the root-cause column is not involved"),
    _i("sel-rootcause-ambiguous",
       "Kenapa tiket INFRA-10501 bisa terjadi?",
       "ambiguous", "summarising-root-causes",
       expected=["explaining-ticket-history"],
       tolerated=["summarising-root-causes"],
       note="'kenapa' plus one ticket id: the classification is a label, not a "
            "reason, and one row has no distribution to summarise"),

    # -- checking-due-dates (distractor) -------------------------------------
    _i("sel-duedate-trigger",
       "Ada berapa tiket yang ditutup setelah due_date-nya?",
       "trigger", DUE_DATES, expected=[DUE_DATES],
       note="names the column outright, so this skill is the right read; its "
            "body must then say the figure is not target adherence"),
    _i("sel-duedate-avoid-1",
       "Apakah kita memenuhi target penyelesaian untuk Incident P1?",
       "avoid", DUE_DATES, expected=[ADHERENCE],
       note="the head-on collision: target adherence must not route to due_date"),
    _i("sel-duedate-avoid-2",
       "Berapa median waktu kerja untuk tiket Bug prioritas P2?",
       "avoid", DUE_DATES,
       note="a duration question with no deadline in it at all"),
    _i("sel-duedate-ambiguous",
       "Berapa persen tiket yang melewati batas waktu?",
       "ambiguous", DUE_DATES, expected=[ADHERENCE], tolerated=[DUE_DATES],
       note="'batas waktu' is ambiguous between due_date and the policy target; "
            "the answer must say which was used"),

    # -- explaining-ticket-history (distractor) ------------------------------
    _i("sel-history-trigger",
       "Jelaskan secara rinci kronologi apa yang terjadi pada tiket INFRA-10501.",
       "trigger", "explaining-ticket-history", expected=["explaining-ticket-history"],
       note="the per-ticket narrative trigger; the data has no change history, "
            "so the skill exists to say so"),
    _i("sel-history-avoid",
       "Apa 3 root cause terbanyak untuk tiket bertipe Bug?",
       "avoid", "explaining-ticket-history",
       note="root cause as classification is answerable and needs no skill"),
    _i("sel-history-ambiguous",
       "Apa penyebab utama tiket INFRA-10501?",
       "ambiguous", "explaining-ticket-history",
       tolerated=["explaining-ticket-history"],
       note="a single-ticket classification lookup is answerable; a narrative "
            "is not"),

    # -- ranking-squad-performance (distractor) ------------------------------
    _i("sel-squad-trigger",
       "Squad mana yang paling cepat menyelesaikan tiket?",
       "trigger", "ranking-squad-performance", expected=["ranking-squad-performance"],
       note="the table has no squad or team field; the skill exists to say so "
            "rather than substitute component or project"),
    _i("sel-squad-avoid",
       "Component mana yang paling banyak menghasilkan Bug?",
       "avoid", "ranking-squad-performance",
       note="component is answerable and is not a team; must not route here"),
    _i("sel-squad-ambiguous",
       "Tim mana yang paling banyak menangani Incident?",
       "ambiguous", "ranking-squad-performance", expected=["ranking-squad-performance"],
       note="'tim' has no field; the skill exists to say so rather than "
            "substitute component or project"),

    # -- formatting-service-review (distractor) ------------------------------
    _i("sel-format-trigger",
       "Siapkan ringkasan untuk service review mingguan.",
       "trigger", "formatting-service-review", expected=["formatting-service-review"]),
    _i("sel-format-avoid-1",
       "Buatkan tabel 10 assignee teratas beserta jumlah tiket yang mereka selesaikan.",
       "avoid", "formatting-service-review",
       note="'Buatkan tabel' invites this skill, but the constraint that "
            "applies is privacy, and the rank-not-name rule lives in the "
            "standing instructions"),
    _i("sel-format-avoid-2",
       "Ada berapa tiket berstatus Done tetapi tidak memiliki resolution?",
       "avoid", "formatting-service-review",
       note="a single figure; no formatting decision to make"),
    _i("sel-format-ambiguous",
       "Tampilkan 5 baris mentah dari tabel beserta semua kolomnya.",
       "ambiguous", "formatting-service-review",
       tolerated=["formatting-service-review"],
       note="a presentation request, but the constraint that applies is "
            "privacy, not formatting"),

    # -- restraint: matches nothing ------------------------------------------
    _i("sel-restraint-poem",
       "Tuliskan sebuah puisi delapan baris tentang kilang minyak.",
       "avoid", "(none)", note="out of scope entirely; any read is wasted"),
    _i("sel-restraint-release",
       "Berapa jumlah bug per rilis?",
       "avoid", "(none)",
       note="the control: a refusal with no skill competing for it"),
]


def by_skill() -> dict[str, list[SelectionItem]]:
    out: dict[str, list[SelectionItem]] = {name: [] for name in MENU}
    for item in ITEMS:
        if item.subject in out:
            out[item.subject].append(item)
    return out


def coverage_gaps() -> list[str]:
    """Skills missing any of the three required kinds, or fewer than 3 items."""
    gaps = []
    for name, items in by_skill().items():
        kinds = {i.kind for i in items}
        missing = {"trigger", "avoid", "ambiguous"} - kinds
        if missing:
            gaps.append(f"{name}: no {', '.join(sorted(missing))} item")
        if len(items) < 3:
            gaps.append(f"{name}: only {len(items)} item(s), standard asks for 3-5")
        if len(items) > 5:
            gaps.append(f"{name}: {len(items)} items, standard asks for 3-5")
    return gaps
