# Verified magnitudes

Measured against `workshop_ai_platform.example.sdlc_tickets` after loading, not
against the generator's in-process output. Seed `20260917`, 4,000 rows,
`created_at` spanning 2025-03-01 to 2026-08-31, 4,000 distinct `ticket_id`.

This is the input the `add-langfuse-eval-dataset` change derives ground truth
from. Refresh it by re-running `scripts/sdlc_tickets_verify.sql` — do not hand-
edit the numbers.

## Findings

| | Finding | Target | Measured |
|---|---|---|---|
| F1a | median wait, created → started | ~19 d | **19.30 d** |
| F1b | median working time, started → closed | ~2 d | **1.99 d** |
| F2 | unplanned share of recorded effort | ~35 % | **33.9 %** |
| F3 | P2 Bug median working time (n=150) | ~6.5 d | **6.65 d** |
| F4 | Story median working time by points | no trend | **1pt 3.51 · 2pt 3.74 · 3pt 3.57 · 5pt 3.17 · 8pt 3.47 · 13pt 3.90** |
| F5 | SAP Integration share of Bugs (355 of 865) | ~40 % | **41.0 %** |
| F6 | Idul Fitri vs other working time | ~2× | **3.55 d vs 1.97 d = 1.80×** |
| F7 | concentration on one assignee, normalised | ~22 % | **23.3 % (701 closures)** |

F4 is non-monotonic and spans 3.17–3.90 d across six point values, which is the
intended result: points carry no signal, because working time is drawn
independently of them. A careful answer reports no meaningful relationship; the
spread is sampling noise, not a trend.

F6 came out at 1.80× rather than 2.0× because the Idul Fitri slice (n=125) has a
different work-type mix than the remainder. Left as measured.

## Defects

| | Defect | Target | Measured |
|---|---|---|---|
| D1 | `closed_at` < `created_at` | 8 | **8** |
| D2 | duration on work that has not closed | 12 | **12** |
| D3 | `status` = Done with no `resolution` | 15 | **15** |
| D4 | `status_category` disagrees with `status` | 5 | **5** |
| D5 | `assigned_to` spelling variants | ~315 | **315** |
| D6 | `story_points` on an Incident | 10 | **10** |

## The two failure modes these exist to produce

**F1 — working time alone misrepresents duration by 11.4×.**

| | days |
|---|---|
| naive answer, from `cycle_time_hours` | **2.00** |
| true answer, `created_at` → `closed_at` | **22.75** |

An agent asked "how long does work take?" and answering from the recorded
duration column reports two days. The real answer is twenty-three. Nothing
errors; the number is simply wrong by an order of magnitude, because the column
measures only the working interval and almost all elapsed time is waiting.

**D5 — careless aggregation understates F7 by 10.5 points, and the evidence is
visible only if you look.** The naive top five closers are *all the same
person*:

| `assigned_to` (raw) | closures | share |
|---|---|---|
| `Budi Santoso` | 386 | 12.8 % |
| `Budi Santoso ` | 80 | 2.7 % |
| `budi santoso` | 63 | 2.1 % |
| `Budi  Santoso` | 58 | 1.9 % |
| ` Budi Santoso` | 58 | 1.9 % |

Normalised with `initcap(trim(regexp_replace(assigned_to, '\s+', ' ')))` this is
one person with 701 closures and a 23.3 % share — where the next-highest
individual holds 1.8 %. The naive result is not merely imprecise; it reports a
different conclusion about how concentrated the team's work is.

## Absences confirmed

No column matching `target`, `sla`, `squad`, `team`, `release`, `version`,
`cost`, `description`, or `satisfaction` exists. Queries about resolution
targets, squad performance, per-release defect rates, cost, and narrative
root-cause detail therefore have no answer in the data — by design, and the
generator asserts it so a future edit cannot quietly reintroduce one.
