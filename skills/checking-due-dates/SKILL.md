---
name: checking-due-dates
description: Checks tickets against the due_date column to find work closed after its due date or now past due. Use when asked about overdue tickets, late work, missed deadlines, tickets past their due date, or SLA breaches.
---

# Checking due dates

Read this before computing anything from `due_date`.

## `due_date` carries no policy and no priority signal

The column is real and it looks like a deadline. It is not one.

- It is populated on **under half** the rows, and the gap is spread evenly
  across every ticket type rather than marking a subset that has deadlines.
- Its distance from `created_at` has a median of roughly a month, and that
  median is **the same for P1, P2, P3 and P4** — the four differ by about a
  day. A P1 incident is given no less time than a P4 task.

A field that does not vary with priority is not encoding a commitment. Any
"overdue rate" computed from it is a real-looking percentage that measures
nothing anyone agreed to.

## What to do instead

**If the question is about resolution targets, SLAs, or whether commitments
were met** — that is `computing-target-adherence`. The targets are policy and
live in the wiki, keyed on ticket type and priority, and are measured on
working time rather than against a per-ticket date. Use that skill and do not
compute a figure here.

**If the question is genuinely about the `due_date` column itself** — someone
asks how many tickets closed after the date recorded in that field — then the
question is answerable and this is the right place. Report it as a property of
the column, and say plainly that it is not a measure of target adherence and
that the column carries no priority signal. Report how many rows carry no
`due_date` at all, because they are excluded and they are the majority.

Never present a `due_date` figure as an SLA or target result. The two answer
different questions and only one of them corresponds to a policy.
