"""Deterministic generator for `workshop_ai_platform.default.sdlc_tickets`.

The workshop's training table is not sample data. Its interesting properties are
designed and recorded, because downstream evaluation derives ground truth from
them — so "what is true in this table" has to be a contract, not an accident of
whatever the random number generator produced.

Two consequences shape this file:

- **Determinism.** One seeded `random.Random`, never the module-level functions,
  and a committed name list rather than a locale library whose output drifts
  between releases. The same seed must reproduce the same 4,000 rows forever.
- **Hand-specified distributions.** Sampling freely washes out every planted
  finding. The constants below are tuned so F1-F7 land at the magnitudes in
  design Decision 7; `--verify` prints what was actually achieved.

Findings (F*) and defects (D*) refer to design Decisions 7 and 8 of the
`replace-ticket-table-with-sdlc-schema` change.

Usage:
    uv run python scripts/generate_sdlc_tickets.py --verify
    uv run python scripts/generate_sdlc_tickets.py --out rows.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from datetime import date, datetime, timedelta

SEED = 20260917
ROWS = 4000
WINDOW_START = date(2025, 3, 1)
WINDOW_END = date(2026, 8, 31)

# The 24 columns of design Decision 3, in order, with their Databricks types.
# The last three are the deliberate "hostile minority": a space, parentheses,
# and a slash, so escaping must be learned by inspecting a schema rather than
# applied reflexively to everything.
COLUMNS: list[tuple[str, str]] = [
    ("ticket_id", "STRING"),
    ("ticket_type", "STRING"),
    ("title", "STRING"),
    ("project", "STRING"),
    ("status", "STRING"),
    ("status_category", "STRING"),
    ("priority", "STRING"),
    ("severity", "STRING"),
    ("resolution", "STRING"),
    ("reported_by", "STRING"),
    ("assigned_to", "STRING"),
    ("sprint", "STRING"),
    ("story_points", "DOUBLE"),
    ("component", "STRING"),
    ("labels", "STRING"),
    ("created_at", "TIMESTAMP"),
    ("updated_at", "TIMESTAMP"),
    ("started_at", "TIMESTAMP"),
    ("closed_at", "TIMESTAMP"),
    ("due_date", "DATE"),
    ("cycle_time_hours", "DOUBLE"),
    ("Custom Field (Root Cause)", "STRING"),
    ("Time Spent (hours)", "DOUBLE"),
    ("Env/Region", "STRING"),
]

# Deliberate absences (design Decision: "The dataset maintains deliberate gaps").
# Asserted against the emitted columns so a well-meaning future edit that adds
# one of these fails loudly instead of quietly voiding the unanswerable questions.
FORBIDDEN_SUBSTRINGS = (
    "target", "sla", "breach", "squad", "team", "release", "version",
    "cost", "budget", "description", "satisfaction", "csat",
)

# ── Vocabulary ────────────────────────────────────────────────────────────────
# Tool-generated fields are English, human-entered fields are Bahasa Indonesia
# (design Decision 5) — what an English-configured tracker used by an Indonesian
# team actually produces.

PLANNED_TYPES = ("Story", "Task", "Bug")
UNPLANNED_TYPES = ("Incident", "Service Request", "Change")
TYPE_WEIGHTS = {
    "Story": 30, "Task": 22, "Bug": 20,
    "Incident": 12, "Service Request": 12, "Change": 4,
}

PROJECTS = ("ITSD", "ERP", "INFRA")
COMPONENTS = (
    "SAP Integration", "Network", "Endpoint", "Email & Collaboration",
    "Access Management", "Internal Apps", "Database",
)
DEFECT_HEAVY_COMPONENT = "SAP Integration"  # F5

STATUS_CATEGORY = {
    "New": "To Do",
    "In Progress": "In Progress",
    "Blocked": "In Progress",
    "In Review": "In Progress",
    "Done": "Done",
    "Cancelled": "Done",
}
CLOSED_STATUSES = ("Done", "Cancelled")
STATUS_WEIGHTS = {
    "Done": 72, "In Progress": 10, "New": 8,
    "Blocked": 4, "In Review": 4, "Cancelled": 2,
}

SEVERITIES = ("Critical", "Major", "Minor", "Trivial")
ENV_REGIONS = ("PROD-JKT", "PROD-SBY", "STG", "DEV")

# Bahasa — a person typed these.
ROOT_CAUSES_ID = (
    "Kesalahan Konfigurasi", "Bug Kode", "Kapasitas Tidak Memadai",
    "Kesalahan Pengguna", "Integrasi Pihak Ketiga", "Perangkat Keras",
    "Gangguan Jaringan",
)
LABEL_POOL = (
    "regresi", "prioritas-tinggi", "tunggu-vendor", "butuh-approval",
    "audit", "berulang", "quick-win",
)

TITLE_TEMPLATES_ID = (
    "Tidak dapat login ke {app}",
    "Permintaan akses {app} untuk pengguna baru",
    "{app} lambat saat jam sibuk",
    "Gagal mengunduh laporan dari {app}",
    "Error saat menyimpan data di {app}",
    "Permintaan reset kata sandi {app}",
    "Sinkronisasi {app} tidak berjalan",
    "Penambahan modul baru pada {app}",
    "Perbaikan tampilan dashboard {app}",
    "Notifikasi {app} tidak terkirim",
    "Data duplikat muncul di {app}",
    "Peningkatan kapasitas penyimpanan {app}",
    "Integrasi {app} dengan sistem pihak ketiga",
    "Penyesuaian hak akses pada {app}",
    "Laporan bulanan {app} tidak sesuai",
)
APPS_ID = (
    "SAP", "portal karyawan", "sistem persediaan", "aplikasi absensi",
    "email korporat", "VPN", "sistem pengadaan", "basis data pelanggan",
    "aplikasi keuangan", "sistem tiket",
)

# Committed rather than generated (design Decision 9). Indonesian given names
# and surnames combined at build time; the hero is fixed so F7 is stable.
FIRST_NAMES = (
    "Budi", "Siti", "Agus", "Dewi", "Rudi", "Rina", "Joko", "Sri",
    "Bambang", "Ayu", "Hendra", "Lestari", "Wahyu", "Indah", "Dedi",
    "Fitri", "Eko", "Ratna", "Yusuf", "Maya", "Andi", "Nur",
)
LAST_NAMES = (
    "Santoso", "Wijaya", "Nugroho", "Pratama", "Hartono", "Susanto",
    "Kusuma", "Halim", "Saputra", "Wibowo", "Permana", "Gunawan",
)
HERO = "Budi Santoso"  # F7: closures concentrate here

# Staff appear in the table as corporate addresses, never as names. The address
# is *derived* from the name rather than drawn independently, so the set of
# people who exist is still stated once, by the two name tuples above —
# The rule is reversible — see `address_for` — though nothing reverses it
# today: the identity vocabulary that did was removed with
# `agent_server/privacy.py`.
MAIL_DOMAIN = "pertamina.com"


def address_for(name: str) -> str:
    """The corporate address for a person's name.

    Total over `FIRST_NAMES x LAST_NAMES`, and single-valued in reverse: the
    local part carries exactly one dot, so splitting on it names one person.
    Initials would not have that property — `Budi` and `Bambang` both reduce to
    `b.santoso` — which is why the full given name is spelled out.
    """
    return f"{name.replace(' ', '.').lower()}@{MAIL_DOMAIN}"


HERO_ADDRESS = address_for(HERO)

# Idul Fitri fortnights inside the window — volume spikes, throughput dips (F6).
IDUL_FITRI_WINDOWS = (
    (date(2025, 3, 24), date(2025, 4, 7)),
    (date(2026, 3, 14), date(2026, 3, 28)),
)

# Wait time (created -> started) medians in days, by type. Planned work queues
# for weeks; unplanned work starts within hours. The overall median is dragged
# up by the planned majority, which is what makes F1 true.
WAIT_MEDIAN_DAYS = {
    "Story": 37.0, "Task": 32.0, "Bug": 20.0,
    "Change": 9.0, "Service Request": 1.2, "Incident": 0.18,
}
# Working time (started -> closed) medians in hours.
CYCLE_MEDIAN_HOURS = {
    "Story": 86.0, "Task": 52.0, "Bug": 43.0,
    "Change": 100.0, "Service Request": 11.0, "Incident": 6.0,
}
CYCLE_MEDIAN_HOURS_P2_BUG = 147.0  # F3: ~6.5 days against a 5-day target
# Effort recorded per hour of working time. Incidents are worked intensively,
# planned work is interleaved with everything else — this is what lifts
# unplanned work's share of effort above its share of rows (F2).
EFFORT_FACTOR = {
    "Story": 0.16, "Task": 0.16, "Bug": 0.22,
    "Change": 0.46, "Service Request": 0.86, "Incident": 1.45,
}


def _lognormal_about(rng: random.Random, median: float, sigma: float) -> float:
    """A positive draw whose median is `median`.

    For a lognormal, the median is exp(mu), so mu = ln(median) puts the centre
    exactly where we want it and sigma controls only the spread.
    """
    import math
    return math.exp(math.log(median) + rng.gauss(0.0, sigma))


def _in_idul_fitri(d: date) -> bool:
    return any(start <= d <= end for start, end in IDUL_FITRI_WINDOWS)


def _day_weight(d: date) -> float:
    """Volume shape: quiet weekends, busy month ends, busier at Idul Fitri."""
    w = 1.0
    if d.weekday() >= 5:
        w *= 0.25
    next_day = d + timedelta(days=1)
    if next_day.month != d.month or (next_day + timedelta(days=1)).month != d.month:
        w *= 1.8  # last two days of the month
    if _in_idul_fitri(d):
        w *= 1.5
    return w


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def _sprint_for(d: date) -> str:
    """Two-week sprints numbered from the window start."""
    return f"Sprint {((d - WINDOW_START).days // 14) + 1}"


def generate(seed: int = SEED, rows: int = ROWS) -> list[dict]:
    rng = random.Random(seed)

    # Shuffled and sliced as names, then addressed. Drawing the sixty people as
    # names keeps this draw identical to the one that produced the recorded
    # magnitudes — the rng sees the same sequence either way, so only the string
    # each person is written as changes.
    names = [f"{f} {l}" for f in FIRST_NAMES for l in LAST_NAMES]
    rng.shuffle(names)
    people = [address_for(n) for n in names[:60]]
    if HERO_ADDRESS not in people:
        people[0] = HERO_ADDRESS

    # Pre-compute the day distribution once so volume shape is exact.
    days = [WINDOW_START + timedelta(days=i)
            for i in range((WINDOW_END - WINDOW_START).days + 1)]
    day_weights = [_day_weight(d) for d in days]

    counters = {p: 0 for p in PROJECTS}
    out: list[dict] = []

    for _ in range(rows):
        ttype = _weighted_choice(rng, TYPE_WEIGHTS)
        unplanned = ttype in UNPLANNED_TYPES

        created_day = rng.choices(days, weights=day_weights, k=1)[0]
        created = datetime.combine(created_day, datetime.min.time()) + timedelta(
            hours=rng.randint(7, 19), minutes=rng.randint(0, 59))

        project = "ITSD" if unplanned else _weighted_choice(
            rng, {"ERP": 40, "INFRA": 30, "ITSD": 30})
        counters[project] += 1
        ticket_id = f"{project}-{10000 + counters[project]}"

        status = _weighted_choice(rng, STATUS_WEIGHTS)
        # Unplanned work closes more reliably than planned work carries on.
        if unplanned and status in ("New", "Blocked"):
            status = "Done" if rng.random() < 0.7 else status

        priority = _weighted_choice(
            rng, {"P1": 8, "P2": 24, "P3": 46, "P4": 22} if not unplanned
            else {"P1": 18, "P2": 30, "P3": 38, "P4": 14})

        if ttype == "Bug":
            # Drawing the fallback from all components would let it re-pick the
            # defect-heavy one and overshoot the planted share.
            component = (DEFECT_HEAVY_COMPONENT if rng.random() < 0.40  # F5
                         else rng.choice([c for c in COMPONENTS
                                          if c != DEFECT_HEAVY_COMPONENT]))
        else:
            component = rng.choice(COMPONENTS)

        # ── timestamps ────────────────────────────────────────────────────────
        started = closed = None
        cycle_hours = None
        if status != "New":
            wait_days = _lognormal_about(rng, WAIT_MEDIAN_DAYS[ttype], 0.85)
            started = created + timedelta(days=wait_days)
        if status in CLOSED_STATUSES and started is not None:
            median = (CYCLE_MEDIAN_HOURS_P2_BUG
                      if ttype == "Bug" and priority == "P2"      # F3
                      else CYCLE_MEDIAN_HOURS[ttype])
            if _in_idul_fitri(started.date()):
                median *= 2.15                                    # F6
            cycle_hours = round(_lognormal_about(rng, median, 0.7), 2)
            closed = started + timedelta(hours=cycle_hours)

        updated = closed or started or created
        updated = updated + timedelta(hours=rng.uniform(0.5, 72))

        # ── people ────────────────────────────────────────────────────────────
        reported_by = rng.choice(people)
        if status == "New" and rng.random() < 0.6:
            assigned_to = None
        elif closed is not None and rng.random() < 0.22:           # F7
            assigned_to = HERO_ADDRESS
        else:
            assigned_to = rng.choice([p for p in people if p != HERO_ADDRESS])

        # ── planning ──────────────────────────────────────────────────────────
        sprint = None if unplanned else _sprint_for(created_day)
        # Points only where a team would actually estimate. Deliberately carries
        # no signal about duration (F4) — drawn independently of cycle time.
        story_points = (float(rng.choice([1, 2, 3, 5, 8, 13]))
                        if ttype in ("Story", "Task") else None)

        n_labels = rng.choices([0, 1, 2], weights=[45, 40, 15], k=1)[0]
        labels = ",".join(rng.sample(LABEL_POOL, n_labels)) if n_labels else None

        resolution = None
        if status == "Done":
            resolution = rng.choices(["Done", "Fixed"], weights=[60, 40], k=1)[0]
        elif status == "Cancelled":
            resolution = rng.choices(
                ["Won't Do", "Duplicate", "Cannot Reproduce"],
                weights=[55, 30, 15], k=1)[0]

        out.append({
            "ticket_id": ticket_id,
            "ticket_type": ttype,
            "title": rng.choice(TITLE_TEMPLATES_ID).format(app=rng.choice(APPS_ID)),
            "project": project,
            "status": status,
            "status_category": STATUS_CATEGORY[status],
            "priority": priority,
            "severity": rng.choice(SEVERITIES) if ttype in ("Bug", "Incident") else None,
            "resolution": resolution,
            "reported_by": reported_by,
            "assigned_to": assigned_to,
            "sprint": sprint,
            "story_points": story_points,
            "component": component,
            "labels": labels,
            "created_at": created,
            "updated_at": updated,
            "started_at": started,
            "closed_at": closed,
            "due_date": (created_day + timedelta(days=rng.randint(7, 60))
                         if rng.random() < 0.45 else None),
            "cycle_time_hours": cycle_hours,
            "Custom Field (Root Cause)": (rng.choice(ROOT_CAUSES_ID)
                                          if ttype in ("Bug", "Incident") else None),
            "Time Spent (hours)": (round(cycle_hours * EFFORT_FACTOR[ttype]
                                         * rng.uniform(0.7, 1.4), 2)
                                   if cycle_hours is not None else None),
            "Env/Region": rng.choice(ENV_REGIONS),
        })

    _inject_defects(rng, out)
    return out


def _inject_defects(rng: random.Random, rows: list[dict]) -> None:
    """Break exactly the documented number of rows, per design Decision 8.

    Injected after clean generation so the counts are exact rather than
    emergent: every one of these is a question the evaluation set will ask, and
    an approximate count makes an approximate answer.
    """
    n = len(rows)

    def pick(pred, count: int, used: set[int]) -> list[int]:
        candidates = [i for i in range(n) if i not in used and pred(rows[i])]
        chosen = rng.sample(candidates, count)
        used.update(chosen)
        return chosen

    used: set[int] = set()

    # D1 — closed before created (8 rows). Chronologically impossible.
    for i in pick(lambda r: r["closed_at"] is not None, 8, used):
        rows[i]["closed_at"] = rows[i]["created_at"] - timedelta(
            hours=rng.uniform(2, 96))

    # D2 — a duration recorded against work that has not closed (12 rows).
    for i in pick(lambda r: r["status"] not in CLOSED_STATUSES
                  and r["started_at"] is not None
                  and r["cycle_time_hours"] is None, 12, used):
        rows[i]["cycle_time_hours"] = round(rng.uniform(3, 200), 2)

    # D3 — closed with no resolution (15 rows).
    for i in pick(lambda r: r["status"] == "Done"
                  and r["resolution"] is not None, 15, used):
        rows[i]["resolution"] = None

    # D4 — status_category disagreeing with status (5 rows).
    for i in pick(lambda r: True, 5, used):
        correct = STATUS_CATEGORY[rows[i]["status"]]
        rows[i]["status_category"] = rng.choice(
            [c for c in ("To Do", "In Progress", "Done") if c != correct])

    # D5 — the hero's address spelled inconsistently. The only defect that
    # produces a *silently wrong* answer rather than a detectable one: a naive
    # GROUP BY splits them out and understates F7.
    #
    # Five variants, as before, but an address admits no internal-whitespace
    # form — so the one that was `Budi  Santoso` becomes a domain-case form
    # instead. Both halves of an address are case-insensitive in practice,
    # which is what makes every one of these the same mailbox.
    _hero_local, _hero_domain = HERO_ADDRESS.split("@")
    variants = (HERO_ADDRESS.upper(),
                f" {HERO_ADDRESS}",
                f"{HERO_ADDRESS} ",
                f"{_hero_local.title()}@{_hero_domain}",
                f"{_hero_local}@{_hero_domain.upper()}")
    hero_rows = [i for i in range(n) if rows[i]["assigned_to"] == HERO_ADDRESS]
    for i in rng.sample(hero_rows, int(round(len(hero_rows) * 0.45))):
        rows[i]["assigned_to"] = rng.choice(variants)
        used.add(i)

    # D6 — points on an Incident, which no team estimates (10 rows).
    for i in pick(lambda r: r["ticket_type"] == "Incident"
                  and r["story_points"] is None, 10, used):
        rows[i]["story_points"] = float(rng.choice([1, 2, 3, 5]))


# ── verification ──────────────────────────────────────────────────────────────


def _norm(name: str | None) -> str | None:
    """Normalise an identity the way D5 requires you to before aggregating.

    Lower-cased rather than title-cased: identities are addresses now, and both
    halves of an address are case-insensitive in practice. This is the same
    normalisation `lower(trim(...))` performs in SQL.
    """
    if name is None:
        return None
    return " ".join(name.split()).lower()


def verify(rows: list[dict]) -> None:
    emitted = list(rows[0].keys())
    expected = [c for c, _ in COLUMNS]
    assert emitted == expected, f"column drift:\n{emitted}\n{expected}"
    for col in emitted:
        low = col.lower()
        for bad in FORBIDDEN_SUBSTRINGS:
            assert bad not in low, f"column {col!r} reintroduces absent field {bad!r}"
    print(f"columns: {len(emitted)} — matches design Decision 3, no absent field present")

    closed = [r for r in rows if r["closed_at"] is not None]
    waits = [(r["started_at"] - r["created_at"]).total_seconds() / 86400
             for r in rows if r["started_at"] is not None]
    cycles = [r["cycle_time_hours"] for r in rows
              if r["cycle_time_hours"] is not None and r["closed_at"] is not None]

    print("\n── findings ──")
    print(f"F1  median wait {statistics.median(waits):.1f} d "
          f"(target ~19) | median cycle {statistics.median(cycles) / 24:.1f} d (target ~2)")

    eff_all = sum(r["Time Spent (hours)"] or 0 for r in rows)
    eff_unplanned = sum(r["Time Spent (hours)"] or 0 for r in rows
                        if r["ticket_type"] in UNPLANNED_TYPES)
    print(f"F2  unplanned share of effort {eff_unplanned / eff_all:.1%} (target ~35%)")

    p2bug = [r["cycle_time_hours"] for r in rows
             if r["ticket_type"] == "Bug" and r["priority"] == "P2"
             and r["cycle_time_hours"] is not None]
    print(f"F3  P2 Bug median cycle {statistics.median(p2bug) / 24:.1f} d (target ~6.5)")

    for pts in (3.0, 5.0):
        c = [r["cycle_time_hours"] for r in rows
             if r["ticket_type"] == "Story" and r["story_points"] == pts
             and r["cycle_time_hours"] is not None]
        print(f"F4  Story {pts:.0f}-point median cycle {statistics.median(c) / 24:.2f} d "
              f"(n={len(c)}) — should match the other")

    bugs = [r for r in rows if r["ticket_type"] == "Bug"]
    share = sum(1 for r in bugs if r["component"] == DEFECT_HEAVY_COMPONENT) / len(bugs)
    print(f"F5  {DEFECT_HEAVY_COMPONENT} share of Bugs {share:.1%} (target ~40%)")

    inside = [r["cycle_time_hours"] for r in rows
              if r["cycle_time_hours"] and r["started_at"]
              and _in_idul_fitri(r["started_at"].date())]
    outside = [r["cycle_time_hours"] for r in rows
               if r["cycle_time_hours"] and r["started_at"]
               and not _in_idul_fitri(r["started_at"].date())]
    print(f"F6  Idul Fitri cycle {statistics.median(inside) / 24:.1f} d vs "
          f"{statistics.median(outside) / 24:.1f} d elsewhere (target ~2x)")

    hero_true = sum(1 for r in closed if _norm(r["assigned_to"]) == HERO_ADDRESS)
    hero_naive = sum(1 for r in closed if r["assigned_to"] == HERO_ADDRESS)
    print(f"F7  hero share of closures {hero_true / len(closed):.1%} normalised "
          f"(target ~22%) vs {hero_naive / len(closed):.1%} naive  ← D5 at work")

    print("\n── defects ──")
    d1 = sum(1 for r in rows if r["closed_at"] and r["closed_at"] < r["created_at"])
    d2 = sum(1 for r in rows if r["cycle_time_hours"] is not None
             and r["status"] not in CLOSED_STATUSES)
    d3 = sum(1 for r in rows if r["status"] == "Done" and r["resolution"] is None)
    d4 = sum(1 for r in rows if r["status_category"] != STATUS_CATEGORY[r["status"]])
    d5 = sum(1 for r in rows if r["assigned_to"] not in (None, HERO_ADDRESS)
             and _norm(r["assigned_to"]) == HERO_ADDRESS)
    d6 = sum(1 for r in rows if r["ticket_type"] == "Incident"
             and r["story_points"] is not None)
    for label, got, want in (("D1 closed<created", d1, 8), ("D2 duration unclosed", d2, 12),
                             ("D3 done no resolution", d3, 15), ("D4 category mismatch", d4, 5),
                             ("D6 points on incident", d6, 10)):
        print(f"{label:<26} {got:>4}  (target {want})" + ("" if got == want else "  ** OFF **"))
    understatement = (hero_true - hero_naive) / len(closed)
    print(f"{'D5 name variants':<26} {d5:>4}  (~45% of the hero's rows; "
          f"understates F7 by {understatement:.1%})")
    assert understatement >= 0.08, (
        "D5 must materially understate F7, not merely be present: a naive "
        "aggregation that lands within a point of the truth teaches nothing")

    print("\n── invariants ──")
    assert not [r for r in rows if r["cycle_time_hours"] is not None
                and r["started_at"] is None], "duration without a start"
    bad_closed = [r for r in rows if r["closed_at"] is not None and r["started_at"] is None]
    assert not bad_closed, "closed without a start"
    assert not [r for r in rows if r["status"] == "New" and r["started_at"] is not None]
    print("no duration derived from an absent timestamp; New rows never started")


def _sql_literal(value, sql_type: str) -> str:
    if value is None:
        return "NULL"
    if sql_type == "TIMESTAMP":
        return f"TIMESTAMP'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
    if sql_type == "DATE":
        return f"DATE'{value.isoformat()}'"
    if sql_type == "DOUBLE":
        return repr(float(value))
    return "'" + str(value).replace("'", "''") + "'"


def insert_batches(rows: list[dict], table: str, size: int = 200):
    """Yield multi-row INSERT statements — no Volume or cluster needed to load."""
    cols = ", ".join(f"`{c}`" for c, _ in COLUMNS)
    for start in range(0, len(rows), size):
        chunk = rows[start:start + size]
        values = ",\n".join(
            "(" + ", ".join(_sql_literal(r[c], t) for c, t in COLUMNS) + ")"
            for r in chunk)
        yield f"INSERT INTO {table} ({cols}) VALUES\n{values}"


def create_table_sql(table: str, *, replace: bool = False) -> str:
    """DDL for the table.

    Column mapping is not optional here. Delta rejects ' ,;{}()\\n\\t=' in
    column names unless name-based column mapping is enabled, and three of our
    columns carry a space, parentheses, and a slash by design. The existing
    `data_tiket_it` is configured the same way, for the same reason.

    `replace=True` emits `CREATE OR REPLACE TABLE`, which is how the table is
    regenerated in place. It is one atomic statement rather than a drop
    followed by a create, so the table is never absent partway through — and
    Delta keeps the prior version, so the old contents remain readable by time
    travel (`VERSION AS OF`) rather than being destroyed outright.
    """
    verb = "CREATE OR REPLACE TABLE" if replace else "CREATE TABLE"
    body = ",\n  ".join(f"`{c}` {t}" for c, t in COLUMNS)
    return (f"{verb} {table} (\n  {body}\n) USING DELTA\n"
            "TBLPROPERTIES ('delta.columnMapping.mode' = 'name')")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--rows", type=int, default=ROWS)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--out", help="write rows as JSONL")
    ap.add_argument("--print-ddl", action="store_true")
    ap.add_argument("--table",
                    default="workshop_ai_platform.default.sdlc_tickets")
    args = ap.parse_args()

    if args.print_ddl:
        print(create_table_sql(args.table))
        return

    rows = generate(args.seed, args.rows)
    if args.verify:
        verify(rows)
    if args.out:
        with open(args.out, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
        print(f"\nwrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
