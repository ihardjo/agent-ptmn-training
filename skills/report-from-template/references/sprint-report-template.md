# Sprint Report — «sprint»

> **This is the approved layout, transcribed.** The signed template is a Word
> document; this file is its structure in markdown so the content can be
> produced against it. Section order, numbering and heading wording are the
> template's and are not to be changed. Placeholders are `«angle-quoted»`.
>
> Every section here is answerable from the ticket table alone. Reproduce every
> heading, in this order. Where a period has nothing to report under one, keep
> the heading and say so — a stated gap is an answer, a dropped section reads as
> an oversight, and the reader cannot tell which happened.

**Reporting period:** «start date» to «end date»
**Prepared:** «date prepared»
**Source:** `{{TABLE}}`, «row count» tickets

---

## 1. Summary

«Three sentences at most. What moved, what did not, and the one thing that
needs a decision. No figure appears here that is not also in a section below.»

## 2. Delivery

### 2.1 Throughput

| Measure | This sprint | Previous | Change |
|---|---|---|---|
| Tickets closed | «n» | «n» | «+/-n» |
| Tickets opened | «n» | «n» | «+/-n» |
| Open at period end | «n» | «n» | «+/-n» |

«Say whether "closed" was taken from `status` or from `status_category`. They
give different totals, because cancelled work carries the `Done` category.»

### 2.2 Velocity

«Story points completed, and the share of tickets carrying no story point at
all. State the basis — a velocity computed over only the pointed tickets
measures something different from one computed over all of them.»

## 3. Effort

«The planned versus unplanned split, with the effort basis stated. If effort is
recorded against work that never closed, say so — it moves this figure.»

## 4. Quality

### 4.1 Root causes

| Cause | Tickets | Share |
|---|---|---|
| «cause» | «n» | «pct» |

«Say which ticket types carry a root cause at all, and whether any cause
actually leads. A top row that is two points clear of the second is a maximum,
not a finding.»

### 4.2 Data quality caveats

«Defects in this period's data that bear on the figures above: impossible
timestamps, closures with no resolution, durations recorded against unclosed
work, status disagreeing with its category. Each one with the count it
affects.»

## 5. Appendix — method

«The queries behind each figure, and anything excluded from them. A reader who
disagrees with a number should be able to find out why without asking.»
