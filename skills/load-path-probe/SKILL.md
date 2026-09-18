---
name: load-path-probe
description: Internal load-path probe. Contains no procedure and is not relevant to any user question; do not read it to answer one.
---

# Load-path probe

This skill exists only so that skill discovery can be verified end to end: that
a directory under `skills/` is found, that its metadata reaches the agent's
instructions, and that its body is readable on demand but not read unless asked
for.

It deliberately carries no procedure. A probe that changed the agent's answers
would make the post-migration evaluation incomparable to the recorded baseline,
which is the one measurement this migration is judged against.

The real skill menu — with its deliberate distractors — arrives with the
wiring-exercise change. This file is replaced then.
