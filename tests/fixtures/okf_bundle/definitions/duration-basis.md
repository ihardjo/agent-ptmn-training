---
type: Definition
title: Waiting time versus working time
title_id: Waktu tunggu versus waktu kerja
description: The two durations a ticket carries, and which one policy targets are measured on.
tags: [definitions, method, duration]
status: stable
sources:
  - id: itsm-charter-2026
    resource: https://openwiki.pertamina.ai/itsm/service-level-charter-2026
    title: IT Service Management Service Level Charter FY2026
    author: human:itsm-lead
    last_modified: 2026-06-24T00:00:00Z
generated: { by: human:itsm-lead, at: 2026-06-24T09:40:00Z }
verified: { by: human:itsm-lead, at: 2026-07-01T04:00:00Z }
stale_after: 2027-03-31T00:00:00Z
---

# Two durations, not one

A ticket carries two distinct durations, and conflating them is the most
common way to misreport delivery performance.

| Interval | Meaning | Column |
|---|---|---|
| `created_at` → `started_at` | **Waiting.** Queued, nobody working on it. | *(derive)* |
| `started_at` → `closed_at` | **Working.** Actively being worked. | `cycle_time_hours` |

## Why they are kept apart

Waiting time and working time have different owners and different remedies.
Waiting is a function of intake, triage, and capacity allocation. Working time
is a function of the work itself. A single end-to-end number hides which of the
two is the problem, so the charter sets targets on working time only.

## What this means when reporting

- Total elapsed time from creation to closure is typically **much larger** than
  working time. Reporting working time as though it were end-to-end understates
  how long a requester actually waited.
- State which duration a figure is measured on. A resolution-target figure is
  always working time; see
  [resolution targets](/policies/resolution-targets.md).
- Elapsed time from `created_at` has **no target** in the current charter. There
  is no threshold to compare it against.
