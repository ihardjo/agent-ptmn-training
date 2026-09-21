---
name: ranking-squad-performance
description: Ranks squads, teams, and delivery groups by resolution speed and throughput. Use when asked which team or squad performs best or worst, or for a comparison of delivery performance across teams.
---

# Ranking squad performance

The table has no team. This skill exists to keep that from being papered over.

## There is no team or squad field

The columns describe tickets, not organisational units. There is no squad, no
team, no delivery group, and no reporting line. A ranking of teams cannot be
produced because there is nothing to group by.

## What must not be substituted

`component` and `project` are the tempting proxies and both are wrong:

- `component` is a **part of the system** — a subsystem the work touched. Two
  teams routinely work on one component, and one team works across several.
- `project` is a **portfolio or product line**, not a group of people.

Presenting either as a team produces a ranking that looks authoritative and
attributes performance to groups that do not exist. `assigned_to` is an
individual rather than a team, and individuals are reported in aggregate only —
see the standing instructions.

## What to answer

Say the data holds no team or squad field, and name that as the missing field.
Do not offer a ranking by component or project as though it answered the
question.

Where a breakdown by component or project is genuinely useful, it may be
offered — but labelled as what it is, a breakdown by subsystem or by portfolio,
and only alongside the statement that it is not a team comparison.
