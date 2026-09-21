---
name: splitting-planned-unplanned-work
description: Computes the split of effort between planned delivery work and unplanned operational work, using ticket type and the absence of a sprint. Use when asked about capacity allocation, how much effort went to unplanned or reactive work, or the balance between delivery and operations.
---

# Splitting planned from unplanned work

Classify on `ticket_type` using the planned and unplanned groupings given in
the standing instructions. Use `sprint IS NULL` as a *check* on that
classification, never as the classification itself — a planned ticket carrying
no sprint is a data-quality observation worth a footnote, not a reason to
reclassify it as unplanned.

The classification is the easy half. The basis is what decides the answer.

## Choosing the effort basis

"Effort" is not one column, and the two candidates answer different questions.
State which one the figure uses.

| Basis | Column | Means | Missing on |
|---|---|---|---|
| Recorded effort | `` `Time Spent (hours)` `` | what people logged | rows where nobody logged |
| Working time | `cycle_time_hours` | elapsed while in progress | unclosed and unstarted work |

Prefer `` `Time Spent (hours)` `` when the question is about effort or
capacity, because that is what it measures. Use `cycle_time_hours` only when
the question is about duration, and say so.

A count of tickets is a third basis and a weaker one: an incident and a
multi-sprint story count the same. If ticket counts are what the question
wants, give them, but do not present a count as an effort share.

## Procedure

1. Classify every row by `ticket_type` into the two classes above.
2. Choose the basis, and say which.
3. Sum the basis per class, and divide by the total **over the rows the basis
   exists on** — not over all rows.
4. Report how many rows were excluded because the basis was null, per class.
   This matters: if the two classes have different null rates, an unstated
   denominator silently biases the split.
5. Cross-check the classification against `sprint IS NULL` and report any
   disagreement as a footnote.

## Shape of the answer

> Unplanned work accounts for **«P»%** of recorded effort.
>
> | Class | Effort («basis») | Share | Rows | Excluded, basis null |
> |---|---|---|---|---|
> | Planned | «E1» | «P1»% | «N1» | «X1» |
> | Unplanned | «E2» | «P2»% | «N2» | «X2» |
>
> - Basis: «column», chosen because «reason».
> - Denominator is rows carrying that basis, not all rows.
> - «K» planned tickets carry no sprint, against the expected pattern.

Compute every number.
