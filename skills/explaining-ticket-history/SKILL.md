---
name: explaining-ticket-history
description: Explains what happened on an individual ticket, reconstructing the sequence of events and the story behind it from its recorded fields. Use when asked to describe, explain, narrate, or give the chronology of a specific ticket by its identifier.
---

# Explaining ticket history

The narrative is not in the data. This skill exists to say so precisely, rather
than to assemble something that reads like one.

## What the table holds for a single ticket

Timestamps, a status, a priority, a component, an environment, a resolution,
and a short root-cause classification. That is a record of *state*, not of
events: there is no comment thread, no change history, no free-text
description, and no field recording what anyone did or decided.

## Why a chronology cannot be reconstructed

Three timestamps give an order — created, started, closed — and nothing about
what happened in between or why. `Custom Field (Root Cause)` is a **short
classification drawn from a fixed set**, not an explanation. Reading a cause
label and a few timestamps and producing a paragraph about what went wrong
invents the causal chain that makes it a story. That invention is not
detectable by the reader, which is what makes it worse than a refusal.

## What to answer

Say the data holds no narrative description or change history for an individual
ticket, and name that absence as the reason. Then give what is actually
recorded, if it helps: the ticket's status, its timestamps, its classification,
its component. Present them as fields, not as a sequence of events.

Aggregate questions about root cause **are** answerable — the top causes across
a set of tickets come straight from the classification. The gap is specific to
the story of one ticket, not to the column.

Do not substitute the component, the labels, or the resolution for a
description of what happened.
