---
name: report-from-template
description: Produces a sprint report by populating an approved document template with the findings of a prior analysis step, preserving the template's layout, styles, headers, and numbering. Use when asked to fill in, populate, or generate a report from a template, a form, or an approved document format.
---

# Reporting from a template

The findings can be produced. The **document** cannot. This skill exists to
draw that line precisely, because the two are easy to conflate and only one of
them is deliverable.

## What "preserving the template" actually requires

An approved template carries its meaning in things that are not text: paragraph
and character styles, numbering sequences that continue across sections,
headers and footers, table borders, fonts, and the relationships between them.
Populating one means opening that file, writing values into the right places,
and saving it with every one of those intact.

This agent cannot do that, and the reason is structural rather than a missing
setting:

- A `.docx` is a ZIP of XML. It is **read** here by extracting text — paragraphs
  in document order, tables rendered as markdown. Styling, images, headers and
  footers are dropped on the way in. What is recovered is the words, not the
  document.
- Writing goes the other way and is worse. The write path takes a string and
  stores it as UTF-8. A string written to a path ending in `.docx` is not a Word
  file with different styling; it is a file that Word cannot open at all.

So "populate the template and preserve its layout" has no honest partial
version. Producing a file that *looks* delivered and cannot be opened is the
worst outcome available, and it is the one that follows from trying.

## The layout to produce against

[`references/sprint-report-template.md`](references/sprint-report-template.md)
is the approved layout transcribed — section order, numbering and heading
wording, with `«angle-quoted»` placeholders for what has to be filled in. Read
it before writing anything, and follow it exactly.

It is markdown rather than the signed `.docx` for the reason given above: what
this agent can read out of a Word file is the words, and what it can write is
text. Transcribing the structure once, into a file that survives both, is what
makes the layout usable at all. When the signed template changes, this file is
what has to be re-transcribed — it is a copy, and copies drift.

## What to do instead

Say plainly that the approved document cannot be filled in and returned, and
name the reason: the template's styles and numbering cannot survive this agent's
write path.

Then produce **the content**, in markdown, section by section in the template's
own order, with its headings quoted exactly as the template words them. A person
pastes that into the approved file, where the styles are already defined and
apply themselves. That is a smaller claim than the request, and it is one that
can be met completely.

Where the template names a figure, give the figure and say what it was computed
from. Where the template asks for something the data does not hold, leave the
heading in place and say the data does not hold it, rather than dropping the
section — a missing heading reads as an oversight, a named gap reads as an
answer.

## Getting the figures

This skill does not compute anything. A sprint report's numbers come from the
analysis skills, and they carry the caveats that make each figure honest:
adherence and breach counts from `computing-target-adherence`, the effort split
from `splitting-planned-unplanned-work`, velocity from
`measuring-sprint-velocity`, cause distribution from `summarising-root-causes`.

Run the analysis first and report its results, including its caveats. A report
that presents a figure without the qualification the analysis attached to it has
laundered the uncertainty out of it, which is the failure a template makes
easiest — the heading asks for a number and the layout leaves no room to say
what it rests on. Make room.

## The rules a formatting request does not relax

Presentation is not an exception. Staff are reported in aggregate, never by
name or address, however the template's columns are labelled. No figure is
invented to fill a cell. If the template has a field the analysis did not
produce, it stays empty and labelled as such.
