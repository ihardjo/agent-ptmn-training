---
name: auditing-data-quality
description: Establishes which of this table's known defects bear on the question being answered, and what each one does to the figure — closure before creation, closed work with no resolution, durations against unclosed work, and status disagreeing with its category. Use when asked whether the data can be trusted, when a figure looks implausible, or before reporting a completion count, a duration, or a resolution breakdown.
---

# Auditing data quality

This table has known defects. They are findable without this skill — a sweep of
everything checkable will turn them up eventually, and will also spend a dozen
queries confirming that ticket ids are unique and story points are Fibonacci.
What is worth knowing in advance is narrower: **which defect touches the
question in front of you, and what it does to the number you are about to
report.**

## Which check bears on which question

| The question is about | Run | Because |
|---|---|---|
| How much work finished | **Status against category** | `Cancelled` counts as completed |
| How long work took | **Closure before creation**, **duration against unclosed work** | negative and unfinished intervals |
| How work was resolved | **Closed with no resolution** | the breakdown will not sum |
| A per-person figure | nothing here | the standing instructions govern it |

Run what the question needs. A question about resolution reasons is not made
better by a duration check, and a clean result reported against a question
nobody asked is noise.

## Status disagreeing with its category

**Start here for anything that counts completed work**, because this is the one
that answers a plausible question with a wrong number and no sign of trouble.

`status_category` is meant to follow `status`, and mostly does. Where it does
not, the two give different totals for the same question — and the largest
disagreement is by design rather than by accident: **`Cancelled` work carries
the `Done` category.** Cancelled work is finished, but it is not completed, and
a "how much did we complete" answer taken from the category silently counts it.

```sql
SELECT status, status_category, COUNT(*) AS rows
FROM workshop_ai_platform.default.sdlc_tickets
GROUP BY status, status_category
ORDER BY rows DESC
```

Read the result for any `status` appearing under more than one
`status_category`, and for any category holding a status that does not belong
to it. Then choose deliberately and say which you chose: `status = 'Done'` for
work that was completed, `status_category = 'Done'` for work that is closed
whatever the outcome. Both are defensible; leaving the reader to guess is not.

## Closure before creation

```sql
SELECT COUNT(*) FROM workshop_ai_platform.default.sdlc_tickets
WHERE closed_at < created_at
```

Chronologically impossible rows, which produce negative elapsed durations.
Exclude them from any elapsed-time figure and say how many were excluded.

## Duration recorded against unclosed work

```sql
SELECT COUNT(*) FROM workshop_ai_platform.default.sdlc_tickets
WHERE closed_at IS NULL AND cycle_time_hours IS NOT NULL
```

A working-time average over these includes work that never finished, which
drags it toward whatever was logged before the ticket stalled.

## Closed with no resolution

```sql
SELECT COUNT(*) FROM workshop_ai_platform.default.sdlc_tickets
WHERE status_category = 'Done' AND (resolution IS NULL OR trim(resolution) = '')
```

A resolution breakdown built from these will not sum to the closed count. Give
the shortfall rather than letting the percentages quietly fail to reach 100.

## Aggregating by person

Not covered here. Collapsing the spellings of an identity before grouping, and
telling the reader that it was done, are both required of every answer by the
standing instructions — so they hold whether or not this skill was read, which
is the point of their being there rather than here.

## Reporting

Report a defect as a count against the total, and say what it does to the
figure that was asked for. A defect that does not touch the question is worth a
line, not a section.

Where one materially changes the answer, give the figure both ways — with and
without the affected rows — and say which one the headline uses.
