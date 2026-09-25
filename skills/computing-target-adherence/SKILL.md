---
name: computing-target-adherence
description: Computes resolution-target adherence and breach counts for Bug and Incident tickets by combining ticket data with the resolution targets held in the wiki. Use when asked whether resolution targets or SLAs were met, for a breach count or adherence rate, or whether target compliance is improving or worsening over a period.
---

# Computing target adherence

The target is not in the table. It is policy, and it lives in the wiki. Half of
this procedure is arithmetic; the other half is reading the right document and
saying which one it was.

## Procedure

```
- [ ] 1. Read the targets from the wiki — never from memory
- [ ] 2. Use working time as the basis
- [ ] 3. Restrict scope to Bug and Incident
- [ ] 4. Exclude unclosed and unstarted work, and count what was excluded
- [ ] 5. Attribute each ticket to the period its closure falls in
- [ ] 6. Report the figure, the documents, and their trust state
```

### 1. Read the targets from the wiki

Read `/wiki/notes/policies/resolution-targets.md`. It holds a target per
`ticket_type` and `priority`. Read the counting rules from
`/wiki/notes/policies/breach-counting.md`.

Do not reproduce target values from this skill or from memory — there are none
here on purpose. A target that changes in the wiki must change in the answer,
and that only works if the answer was read from the wiki this time.

### 2. Use working time as the basis

Working time — `cycle_time_hours` — is the basis, per
`/wiki/notes/definitions/duration-basis.md`. Confirm it there rather than
assuming it; the charter could change it and this skill would not.

**`due_date` is not the target, and this is the trap specific to adherence.**
The column exists and looks like a deadline. It is populated on under half the
rows, and its distance from `created_at` is statistically indistinguishable
across all four priorities — a P1 carries the same typical due date as a P4. It
encodes no policy and no priority signal. An "overdue rate" computed from it is
a real-looking number that measures nothing. If the question is about overdue
work rather than target adherence, say the two are different and answer this
one.

### 3. Restrict scope to Bug and Incident

Only `Bug` and `Incident` carry a target; `breach-counting.md` puts everything
else out of scope, to be counted as neither met nor breached. Note this puts
`Service Request` out of scope too — it is unplanned operational work, so it is
easy to sweep in alongside `Incident`.

### 4. Apply the exclusions the counting rules define

`breach-counting.md` excludes unclosed work and work never started: neither has
a working interval, so neither is met or breached. Report how many rows each
exclusion removed — an adherence rate that silently drops open work overstates
performance, and the two exclusions have different causes worth separating.

### 5. Attribute by closure date

A ticket belongs to the period its `closed_at` falls in, not the period it was
created in. A breach is a fact about a resolution, and a resolution has one
date.

### 6. Report the figure and the trust state

Name both documents the figure rests on. Report each one's trust state as the
frontmatter gives it: whether it is verified, and whether it is past its
`stale_after`. `breach-counting.md` carries `status: draft` and has not been
ratified, so an adherence figure computed under its rules is provisional and
should be reported as such — not withheld.

## Shape of the answer

Lead with the adherence figure, then the evidence:

> **«P»%** of «type» tickets at «priority» met the target.
>
> | Measure | Value |
> |---|---|
> | In scope, closed | «N» |
> | Met | «M» |
> | Breached | «B» |
> | Excluded — not closed | «X» |
> | Excluded — not started | «Y» |
>
> - Target from `/wiki/notes/policies/resolution-targets.md` («state whether verified and current»).
> - Counting rules from `/wiki/notes/policies/breach-counting.md` (draft, unratified).
> - Measured on working time (`cycle_time_hours`), which is the basis the charter defines. Elapsed time from `created_at` has no target.

Compute every number. The placeholders above are shape, not data.
