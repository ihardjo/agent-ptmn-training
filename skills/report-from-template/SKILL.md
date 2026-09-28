---
name: report-from-template
description: Produces a sprint report in the reply, laid out to the approved sprint report template — its sections, in its order, with its headings and numbering. Use when asked for a sprint report, a status report, or findings in the standard reporting format.
---

# Reporting to the standard template

The report is the reply. Nothing is attached and no file is produced — the
deliverable is the content itself, written out in the chat, in the layout the
approved template fixes.

## The layout

[`references/sprint-report-template.md`](references/sprint-report-template.md)
is that layout: section order, numbering and heading wording, with
`«angle-quoted»` placeholders marking what has to be filled in. Read it before
writing anything and follow it exactly. It is the approved document transcribed,
so when the signed version changes this file is what has to be re-transcribed —
it is a copy, and copies drift.

Reproduce every heading, in the template's order and wording. Where a period has
nothing to report under one, keep the heading and say so: a named gap is an
answer, a dropped section reads as an oversight, and the reader cannot tell the
two apart. Replace every placeholder — an `«angle-quoted»` string surviving into
the reply is a hole, not a value.

## Getting the figures

Three sections, and only two of them carry numbers.

**Throughput** is counts off the ticket table. Say which column the closed count
came from: `status` and `status_category` disagree, because cancelled work
carries the `Done` category, and the reader cannot tell which you used.

**Velocity** comes from `measuring-sprint-velocity`, with the coverage caveat it
attaches — roughly half the rows carry no `story_points`, so a velocity figure
describes pointed work rather than all delivery.

Report each figure together with its caveat. A number given without the
qualification the analysis attached to it has had the uncertainty laundered out
of it, which is the failure a template makes easiest: the heading asks for a
number and the layout leaves nowhere to say what it rests on. Section 3 is that
room, and the short form belongs next to the figure as well.

## The rules a formatting request does not relax

Presentation is not an exception. Staff are reported in aggregate and by rank,
never by name or address. No figure is invented to fill a cell, and the table
holds no resolution target, escalation route or risk owner — asked for one, say
the ticket data does not carry it rather than reaching for a proxy.
