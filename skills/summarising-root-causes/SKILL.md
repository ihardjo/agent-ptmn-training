---
name: summarising-root-causes
description: Summarises the distribution of `Custom Field (Root Cause)`, establishing which ticket types carry the field at all and whether any cause stands above an even split. Use when asked for the main, dominant, or most common cause of tickets, for a breakdown of why tickets were raised, or which underlying problem to fix first.
---

# Summarising root causes

Two things decide this answer, and neither is the `GROUP BY`. The first is
which rows carry the field. The second is whether the leading share is a
finding or a coin toss.

## The field is conditional, not sparse

`Custom Field (Root Cause)` is populated on defect work — `Bug` and `Incident`
— and null everywhere else. That is not missing data. It is a field that does
not apply to a Story or a Service Request, and treating its nulls as a
data-quality problem misreads the schema.

Establish the population before grouping, every time:

```sql
SELECT ticket_type,
       COUNT(*)                           AS rows,
       COUNT(`Custom Field (Root Cause)`) AS with_cause
FROM workshop_ai_platform.example.sdlc_tickets
GROUP BY ticket_type
ORDER BY rows DESC
```

A bare `GROUP BY` over the whole table silently answers a different question
from the one asked: it reports the causes of defect work while appearing to
report the causes of all tickets. Name the population the figures cover and
give its size against the table total.

Where the question already names a type — "Bug tickets" — the field is fully
populated within it and there is no null caveat to make. Do not import one the
filtered population does not have.

## Decide whether there is a leading cause at all

The causes are drawn from a short fixed list and are close to evenly spread, so
the top row is reliably the *most frequent* and is not reliably *the cause*.
The gap between first and second can be a handful of tickets out of hundreds.

```sql
SELECT `Custom Field (Root Cause)` AS cause,
       COUNT(*)                    AS tickets,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM workshop_ai_platform.example.sdlc_tickets
WHERE `Custom Field (Root Cause)` IS NOT NULL
GROUP BY `Custom Field (Root Cause)`
ORDER BY tickets DESC
```

Compute the even split — 100 divided by the number of distinct causes the query
returns — and compare the leading share against it. Do not carry a remembered
number of causes into this; count what came back.

Where every cause sits near that line, say the distribution is flat and name no
winner. Where one stands clearly above it, name it and give the gap.

**Reporting the first row as "the main cause" without that comparison is the
failure this skill exists to prevent.** It is a real number attached to a
conclusion the data does not support, and it sends people to fix the wrong
thing. Listing the top three *by frequency* is a different and answerable
question — answer that one as asked, without promoting the first row to a
cause.

## Shape of the answer

> No single cause dominates. Across «N» «types» tickets the «K» recorded causes
> each account for «low»–«high»%, against «even»% for an even split.
>
> | Cause | Tickets | Share |
> |---|---|---|
> | «cause» | «n» | «p»% |
>
> - Population: `ticket_type` in «types», «N» of «total» rows. The field does
>   not apply to the other types.
> - No cause is far enough above an even split to be called the main one.

Where one cause does stand out, replace the first line with it and say how far
above the even split it sits.
