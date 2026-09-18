## Context

See proposal.md — Why. The two facts that collide:

- `agent-evaluation` requires that a capability change which makes a question answerable also changes "the dataset version".
- Langfuse dataset item ids are unique per project **across** datasets and stay reserved after deletion. Seeding a second dataset that reuses them fails with a 409. This was established twice: once when held-out items were moved between datasets during `add-langfuse-eval-dataset`, and again when `add-volume-backed-wiki` flipped the resolution-target items.

`agent_evaluation/dataset.py` already documents the conflict and its resolution. This change makes the spec agree with it.

## Goals / Non-Goals

**Goals:**
- A requirement that is satisfiable on the platform the dataset actually lives on.
- The versioning *intent* preserved: a consumer of a score must be able to tell which expectations it was measured against.

**Non-Goals:**
- No code change. The implementation is already correct; the spec was wrong.
- Not weakening the obligation to version. The obligation moves from the name to the record; it is not dropped.
- Not solving re-runnability. That is a real loss and this change documents it rather than repairing it.

## Decisions

### 1. The obligation moves from the identity to the record

The original requirement fixed on a mechanism — change the dataset version — when what it wanted was a property: a score should be interpretable against known expectations. Naming the dataset was one way to carry that, and it is the one the platform forecloses.

So the requirement now asks that the version be *recorded and discoverable*, and explicitly declines to mandate where. The current implementation carries it in the dataset description and the run name, which satisfies it.

*Alternative considered.* Keeping the requirement and changing the implementation — new dataset per version, new ids each time. Rejected: it trades the thing the dataset exists for. Item-by-item comparability across runs is what makes a movement attributable to a question rather than to a total, and every measurement record in this project relies on it.

### 2. The immutability consequence is stated in the requirement, not left to the code comment

Mutating expectations in place means a superseded answer key is gone. A score recorded against it stays readable but is no longer reproducible, and is not comparable to a score measured against the current expectations.

That is a real limitation and the kind that quietly misleads — two numbers from the same dataset name, measured against different answer keys, look comparable. It belongs in the spec where someone quoting an old score will meet it, not only in a comment in the file that caused it.

### 3. The platform constraint gets its own scenario

A scenario stating that identifier stability outranks a versioned name, where the two conflict, so the reasoning is not re-derived. This is the third time in this project that Langfuse's per-project id uniqueness has shaped a design; writing it into the spec stops it being discovered a fourth time.

## Risks / Trade-offs

- **The amendment could read as weakening a requirement to fit an implementation** → the obligation is unchanged in substance and the trade is recorded: identifier stability is what buys item-level comparability, which every measurement record in this project depends on. The requirement is narrower about mechanism and no weaker about intent.
- **"Recorded where a consumer can discover it" is softer than a name** → accepted. A name is self-announcing and a description is not, which is why the immutability consequence is stated in the same requirement rather than filed elsewhere.
- **Superseded expectations stay unreproducible** → not addressed here. Fixing it needs versioned expectations inside each item, which is a dataset-shape change and its own piece of work.

## Migration Plan

1. Sync the delta into `openspec/specs/agent-evaluation/spec.md`.
2. Confirm the capability is self-consistent: the requirement is satisfiable by the implementation as it stands, with no code change.

**Rollback.** Revert the requirement text. No code or data depends on it.
