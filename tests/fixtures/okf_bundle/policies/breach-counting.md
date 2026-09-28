---
type: Reference
title: How a target breach is counted
title_id: Cara menghitung pelanggaran target
description: Counting rules for target breaches — which tickets are in scope and which are excluded.
tags: [sla, targets, method]
status: draft
sources:
  - id: itsm-charter-2026
    resource: https://openwiki.pertamina.ai/itsm/service-level-charter-2026
    title: IT Service Management Service Level Charter FY2026
    author: human:itsm-lead
    last_modified: 2026-06-24T00:00:00Z
generated: { by: human:service-desk-analyst, at: 2026-08-11T06:40:00Z }
---

# Counting a breach

A ticket has **breached** when its working time exceeds the target for its
type and priority in [resolution targets](/policies/resolution-targets.md).

    breach  ⟺  cycle_time_hours > target for (ticket_type, priority)

## Scope

Only `Bug` and `Incident` tickets are in scope, because only those have a
target. `Story`, `Task`, `Change`, and `Service Request` tickets are **out of
scope** and must not be counted as either met or breached.

## Exclusions

- **Unclosed work is excluded.** A ticket with no `closed_at` has no working
  time yet, so it is neither met nor breached. Report how many were excluded
  on this basis — open work is not compliant work.
- **Work never started is excluded** on the same grounds: no `started_at`
  means no working interval exists.

## Which period a ticket falls in

A ticket is counted in the period its **`closed_at`** falls in, not the period
it was created in. A breach is a fact about a resolution, and a resolution has
one date.

> **Draft.** This page records the counting rules as the service desk currently
> applies them. It has not been ratified by the Delivery Forum, so the scope
> and exclusion rules above may change.
