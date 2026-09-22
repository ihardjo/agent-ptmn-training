---
name: auditing-data-quality
description: Detects data-quality defects in the ticket table — closure before creation, closed tickets with no resolution, durations recorded against unclosed work, status disagreeing with its status category, and assignee names differing only by case or whitespace. Use when asked whether the data can be trusted, when a figure looks implausible, or before reporting a total that a defect class would distort.
---

# Auditing data quality

Five defect classes are present in this table. Each is detectable, each has a
different consequence, and one of them silently corrupts an answer rather than
producing an obvious error.

## The defect classes

Run the check that bears on the question. Running all five for a question that
touches none of them is wasted effort.

### 1. Closure before creation

Chronologically impossible rows.

```sql
SELECT COUNT(*) FROM workshop_ai_platform.example.sdlc_tickets
WHERE closed_at < created_at
```

Consequence: negative durations. Exclude these rows from any elapsed-time
figure and say how many.

### 2. Closed with no resolution

```sql
SELECT COUNT(*) FROM workshop_ai_platform.example.sdlc_tickets
WHERE status_category = 'Done' AND (resolution IS NULL OR trim(resolution) = '')
```

Consequence: a resolution breakdown that does not sum to the closed count.

### 3. Duration recorded against unclosed work

```sql
SELECT COUNT(*) FROM workshop_ai_platform.example.sdlc_tickets
WHERE closed_at IS NULL AND cycle_time_hours IS NOT NULL
```

Consequence: a working-time average that includes work which never finished.

### 4. Status disagreeing with its category

`status_category` should follow `status`. Where it does not, grouping by one
gives a different total from grouping by the other.

```sql
SELECT status, status_category, COUNT(*) AS rows
FROM workshop_ai_platform.example.sdlc_tickets
GROUP BY status, status_category
ORDER BY status, status_category
```

Read the result for a `status` appearing under more than one `status_category`.

### 5. Identity split by formatting

**This is the one that corrupts silently** — it produces no error, only a
wrong number. The standing instructions require normalising before aggregating
by person; this is how to measure how much it matters here:

```sql
SELECT COUNT(DISTINCT assigned_to)              AS raw,
       COUNT(DISTINCT lower(trim(assigned_to))) AS normalised
FROM workshop_ai_platform.example.sdlc_tickets
```

`assigned_to` holds email addresses, and both halves of an address are
case-insensitive in practice — so `lower(trim(...))` is the whole normalisation
here, with no internal whitespace left to collapse.

The gap between the two columns is the size of the defect. Report it when the
question turns on per-person aggregation, because it quantifies how far an
unnormalised answer would have been off.

## Reporting

Report defects as counts against the total, and say what each one does to the
figure that was asked for. A defect that does not affect the question is worth
a line, not a section.

Where a defect materially changes the answer, give the figure both ways — with
and without the affected rows — and say which one the headline number uses.
