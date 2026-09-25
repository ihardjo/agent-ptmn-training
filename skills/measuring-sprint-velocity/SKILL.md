---
name: measuring-sprint-velocity
description: Computes sprint velocity from story points completed per sprint, handling the large share of tickets that carry no story-point value. Use when asked about velocity, throughput per sprint, story points delivered, or whether delivery pace is changing.
---

# Measuring sprint velocity

Velocity is story points completed per sprint. The arithmetic is trivial. The
answer is decided almost entirely by what you do about the missing values, so
that is what this covers.

## The denominator problem

`story_points` is null on roughly half the rows. Three treatments are
available and they give materially different answers:

| Treatment | Effect | When it is right |
|---|---|---|
| Exclude null rows | Velocity of *pointed* work | Default. Say how many were excluded. |
| Treat null as zero | Understates velocity | Never. It asserts the work was free. |
| Impute a value | Invents data | Never here. |

Use exclusion. **Never treat a null as a zero** — a null means nobody
estimated the ticket, not that it took no effort, and zero-filling drags every
sprint average toward zero by an amount that varies with how well that sprint
was groomed.

## Procedure

1. Restrict to completed work: `status_category = 'Done'`. Velocity counts what
   finished, not what was started.
2. Restrict to rows carrying a sprint. Unplanned work has none and is out of
   scope for velocity by construction — see
   `splitting-planned-unplanned-work` if the question is about that split.
3. Exclude rows where `story_points` is null, and **count them per sprint**.
4. Sum `story_points` per `sprint`.
5. Report the per-sprint series and its central tendency, with the coverage
   figure beside it.

```sql
SELECT sprint,
       SUM(story_points)                                     AS points,
       COUNT(*)                                              AS tickets,
       COUNT(story_points)                                   AS pointed,
       SUM(CASE WHEN story_points IS NULL THEN 1 ELSE 0 END) AS unpointed
FROM workshop_ai_platform.default.sdlc_tickets
WHERE status_category = 'Done' AND sprint IS NOT NULL
GROUP BY sprint
ORDER BY sprint
```

Do **not** add `story_points IS NOT NULL` to the `WHERE` clause. Exclusion has
to happen inside the aggregates, not in the filter, or the unpointed rows
vanish before they can be counted and coverage becomes unreportable. `SUM` and
`COUNT(story_points)` already ignore nulls, so `points` and `pointed` are
correct as written while `tickets` still sees everything.

Note `tickets` is every completed sprinted ticket, not the pointed subset —
`pointed` is that. Reading one for the other overstates coverage.

## Reporting coverage is not optional

A velocity figure computed over half the tickets is a statement about that half.
Say what share of completed, sprinted tickets carried a point value, and lead
with the caveat if coverage is low or uneven across sprints.

Sprint labels are strings, not dates. They sort lexically, so `Sprint 31` sorts
before `Sprint 4`. Order numerically before presenting a trend, and do not read
a trend from a lexical ordering.

## Shape of the answer

> Median velocity is **«V» points per sprint** across «N» sprints.
>
> | Sprint | Points | Pointed tickets | Coverage |
> |---|---|---|---|
> | «s» | «p» | «n» | «c»% |
>
> - Completed work only (`status_category = 'Done'`) carrying a sprint.
> - «X» completed tickets had no `story_points` and were excluded; nulls were not treated as zero.
> - Coverage is «c»% overall, so this describes pointed work rather than all delivery.
