---
name: escalating-breaches
description: Applies the escalation matrix to tickets that have breached a resolution target, and reports the matrix's own review status alongside its routing. Use when asked who should be notified about a breach, what the escalation path or timeframe is, or which breaches require escalation.
---

# Escalating breaches

Escalation routing is policy. It lives in the wiki, it changes without this
skill changing, and it is currently **past its review horizon** — which is part
of the answer, not a footnote to it.

## Read the routing; do not carry it

Read `/wiki/openwiki/policies/escalation-matrix.md`. It gives, per breach
severity, who is notified and within what time.

No routing is reproduced in this skill. That is deliberate: a role written down
here would be a second copy that goes stale independently of the wiki, and the
wiki is the system of record. If the matrix cannot be read, say the routing is
unavailable — do not supply a plausible one.

## Establish the breach first

Escalation applies to breached tickets, so a breach must be established before
routing means anything. Use `computing-target-adherence` for that: it holds the
basis, the scope, and the exclusions. Do not determine a breach from `due_date`.

Severity for routing purposes is the ticket's `priority`. The matrix is keyed
on the priority of the breach, not on the size of the overrun.

## Report the trust state, and still answer

The escalation matrix carries a `stale_after` that has passed, and its source
is a prior-year charter. The document says so itself.

So:

- **Apply it.** An expired policy is the best available statement of routing,
  and withholding the answer serves nobody.
- **Say it is expired**, give the review horizon from the frontmatter, and name
  the charter it derives from.
- **Say what to do about it**: confirm against the current charter before
  acting.

Reporting a stale policy as though it were current, and refusing to report it
at all, are both wrong. The first is misleading and the second is unhelpful.

## Escalation is triggered by the breach, not the trend

The matrix routes on individual breaches. A question about whether breaches are
rising is a trend question, which the matrix does not route and which is
handled in periodic review rather than by escalation.

## Shape of the answer

> «N» breached tickets require escalation.
>
> | Priority | Breaches | Notify | Within |
> |---|---|---|---|
> | «p» | «n» | «from the matrix» | «from the matrix» |
>
> - Breach determined on working time against `/wiki/openwiki/policies/resolution-targets.md`.
> - Routing from `/wiki/openwiki/policies/escalation-matrix.md`. **This page is past its review horizon of «date» and derives from the «year» charter — confirm the routing against the current charter before acting on it.**
> - «X» tickets excluded as not closed, so no working time exists for them yet.
