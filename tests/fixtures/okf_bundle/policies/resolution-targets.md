---
type: Service Level Policy
title: Resolution targets by priority
title_id: Target penyelesaian berdasarkan prioritas
description: Working-time resolution targets for Bug and Incident tickets, by priority.
tags: [sla, targets, delivery, operations]
status: stable
sources:
  - id: itsm-charter-2026
    resource: https://openwiki.pertamina.ai/itsm/service-level-charter-2026
    title: IT Service Management Service Level Charter FY2026
    author: human:itsm-lead
    usage_count: 412
    last_modified: 2026-06-24T00:00:00Z
  - id: delivery-forum-minutes
    resource: https://openwiki.pertamina.ai/delivery/forum/2026-06-18
    title: Delivery Forum minutes, 18 June 2026
    author: human:delivery-forum
    usage_count: 37
    last_modified: 2026-06-18T00:00:00Z
usage_window: { from: 2026-01-01T00:00:00Z, to: 2026-09-01T00:00:00Z }
generated: { by: human:itsm-lead, at: 2026-06-24T09:15:00Z }
verified:
  - { by: human:itsm-lead, at: 2026-07-01T04:00:00Z }
  - { by: process:openwiki-policy-review, at: 2026-07-02T01:30:00Z }
stale_after: 2027-03-31T00:00:00Z
---

# Resolution targets

These are the resolution targets the delivery and operations teams are held
to for FY2026. They are **policy**, not data: they do not exist in
`sdlc_tickets` and cannot be derived from it.

## Measurement basis

Targets are measured on **working time** — the interval from `started_at` to
`closed_at`, which the `cycle_time_hours` column already holds.[^itsm-charter-2026]

They are **not** measured on elapsed time from `created_at`. Queue time before
a ticket is picked up is tracked separately and has no target in this charter;
see [duration basis](/definitions/duration-basis.md) for why the two are kept
apart.

## Bug tickets

| Priority | Target (working hours) |
|---|---|
| P1 | 48 |
| P2 | 80 |
| P3 | 120 |
| P4 | 160 |

## Incident tickets

| Priority | Target (working hours) |
|---|---|
| P1 | 8 |
| P2 | 16 |
| P3 | 24 |
| P4 | 48 |

## Work with no resolution target

`Story`, `Task`, and `Change` tickets have **no resolution target**. Planned
delivery work is committed and tracked per sprint, not against an elapsed
target, so an adherence figure for these types is not defined.[^delivery-forum-minutes]

A question about target adherence for planned work therefore has no answer
here, and none should be inferred from the Bug and Incident targets above.

[^itsm-charter-2026]: IT Service Management Service Level Charter FY2026, §4.2.
[^delivery-forum-minutes]: Delivery Forum minutes, 18 June 2026 — resolution on planned-work tracking.
