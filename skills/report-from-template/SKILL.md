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

Reproduce every heading, in the template's order, with its wording and numbering
unchanged. The headings are what make one sprint's report comparable to the
last one's, and a renamed or reordered section breaks that comparison silently.

Where the data does not hold what a section asks for, keep the heading and say
so beneath it. A named gap is an answer; a dropped section reads as an
oversight, and the reader cannot tell the two apart.

Replace every placeholder. An `«angle-quoted»` string surviving into the reply
is a hole, not a value.

## Getting the figures

This skill computes nothing. Every section is answerable from the ticket table,
and the numbers come from the analysis skills, which carry the caveats that make
each figure honest: the effort split from `splitting-planned-unplanned-work`,
velocity from `measuring-sprint-velocity`, cause distribution from
`summarising-root-causes`, and the caveats themselves from
`auditing-data-quality`.

Run the analysis first, then report its result together with its caveat. A
figure given without the qualification the analysis attached to it has had the
uncertainty laundered out of it — the failure a template makes easiest, because
a heading asks for a number and the layout leaves nowhere to say what it rests
on. Section 5 is that room; use it, and keep the short form next to the figure
rather than only in the appendix.

Nothing in the layout asks for a resolution target, an escalation route, or a
risk owner. The table holds none of those, so a section needing one would have
no honest filling — if a request wants them, say the ticket data does not carry
them rather than reaching for a proxy.

## The rules a formatting request does not relax

Presentation is not an exception. Staff are reported in aggregate and by rank,
never by name or address, however the template's columns are labelled. No figure
is invented to fill a cell.
