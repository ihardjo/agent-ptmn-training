## Context

See `proposal.md` — Why. The constraints that shape the approach:

- **The write guard and the answer net cannot be the same mechanism.** `PIIMiddleware.after_model` reads `last_ai_msg.content`. A `/wiki/notes/` write is a tool call, so its payload lives on `.tool_calls`, which the middleware never inspects. Two layers are required by the transport, not by preference.
- **The agent must see identities to do its job.** The concentration finding (F7, 23.3 % of closures) is only discoverable by grouping on the identity column. Any removal upstream of the model destroys the product.
- **The required output form is a rank, not a placeholder.** Per-span substitution cannot produce `1 (tertinggi)` from a result set; that is an aggregation over all rows.
- **`agent-evaluation` already forbids model-judged privacy checks** — the check is an exact string test, which means it depends entirely on the enumerated set being complete.
- `PIIMiddleware` is in the already-pinned `langchain>=1.4.1`, and `agent.py:237` already passes a `middleware` list.

## Goals / Non-Goals

**Goals:**

- One derivation rule, one identity vocabulary, derived from the existing `FIRST_NAMES`/`LAST_NAMES` constants — so the guard, the scorer, and the generator cannot disagree about who exists.
- Hold every documented magnitude constant across the representation change: row counts, the hero's share, distinct-identity counts, defect counts.
- Keep the evaluation measuring the agent, not the net.

**Non-Goals:**

- Scrubbing the `updates` stream channel. Documented as uncovered (see Decision 7).
- Detecting identities in free text (ticket titles, root causes). Titles are Bahasa Indonesia work descriptions and contain no identities by construction.
- Any change to the `/wiki/openwiki/` read-only tier or the OKF write path.

## Decisions

### 1. Derivation rule: `{first}.{last}@pertamina.com`, lowercased

`Budi Santoso` → `budi.santoso@pertamina.com`. One rule, total, reversible by splitting the local part on `.`.

*Alternatives considered.* **Initials** (`b.santoso@`) collide — 22 first names over 12 surnames means `Budi`/`Bambang` both yield `b.santoso`, so reversal stops being single-valued and the spec's "resolves to one identity" scenario fails. **Independent addresses** (a lookup table) would make the email unrecoverable from the name, which defeats the purpose of building one vocabulary from one pair of constants and hands us two sources of truth to keep in sync. Derivable was the user's decision and it is also the only option that keeps the vocabulary derived rather than duplicated.

### 2. `privacy.py` holds *both* forms; `normalise()` is left alone

`person_names()` becomes `identities()`, returning the name form **and** the derived address form for every `first × last` pair. `names_in()` becomes `identities_in()` over that union.

*Alternative considered:* teach `normalise()` to fold `.`, `_` and `@` to spaces, so `budi.santoso@…` would normalise to `budi santoso …` and match the existing name vocabulary. Rejected — it makes the matcher lossy in a way that is hard to reason about (any dotted token becomes two words, so unrelated text acquires spurious word boundaries), and it quietly widens what the guard matches without that widening being visible in the vocabulary. Enumerating both forms keeps the closed set honest: what the guard catches is exactly what is listed.

**Deliberate consequence:** the vocabulary still cannot catch an address form nobody enumerated. That is precisely the gap the shape-based net in Decision 4 covers, and the two layers are kept distinct for that reason rather than merged.

### 3. `privacy.py` stays; its docstring claim is removed

Its docstring asserts the guard and the scorer "are derived, not duplicated, so they cannot drift apart." `scorers.py:35` builds `PERSON_NAMES` with its own comprehension and its own case-folding and does **not** import `privacy.py`. They are two code paths over shared constants and can drift freely — which is exactly how a single missing form would land in both at once.

Fix: `scorers.py` imports the identity set from `agent_server.privacy` instead of rebuilding it. The claim then becomes true rather than aspirational. The evaluation package already imports from `scripts.generate_sdlc_tickets`, so importing from `agent_server` introduces no new coupling direction.

### 4. Middleware configuration

```python
PIIMiddleware(
    "email",
    strategy="redact",
    apply_to_input=False,
    apply_to_output=True,
    apply_to_tool_results=False,
)
```

| Setting | Why not otherwise |
|---|---|
| `apply_to_input=False` | Nothing to scrub. No item among the 13 `forbid_person_names` cases names a person in the question; they ask *"Siapa yang paling banyak menutup tiket?"*. Scrubbing the question would also break `declined_correctly`, which requires the agent to read what it is declining. |
| `apply_to_tool_results=False` | `redact` collapses every `GROUP BY` key to one token and destroys the distribution. |
| `strategy="redact"` | `block` raises `PIIDetectionError` and fails the run. `backends.py:324` states the house rule explicitly: the guard returns a recoverable error *"so the agent can rewrite the note and continue — the constraint must not be satisfiable by declining."* A run-fatal guard is the opposite. |

*Alternative seriously considered and rejected: `apply_to_tool_results` with `strategy="hash"`.* Pseudonymous hashing preserves groupability, so the agent could still find the distribution with identities already gone — the strongest possible containment. It fails on this data: `_redaction.py:300` hashes `match["value"]`, the **raw** matched text. The planted variants differ by case, so `Budi.Santoso@…` and `budi.santoso@…` hash to different digests, splitting one person across groups and **understating the concentration** — the exact failure the dataset's variant defect exists to teach. A normalising detector could repair it, but doing so would perform the normalisation the agent is supposed to demonstrate, deleting the lesson to save a turn.

### 5. The evaluation builds the agent without the net

`init_agent()` gains `redact_output: bool = True`. `agent_evaluation` passes `False`.

The net cannot be scored around after the fact: `after_model` *replaces* the message in graph state, so the pre-redaction text is not recoverable from the run. Rather than thread an original-output channel through the graph, the two things are tested where each is cheap:

- **the agent's compliance** — the eval, with the net off, so `no_pii_leak` keeps measuring what it has always measured
- **the net itself** — a unit test asserting an identity in an `AIMessage` is removed, and that the configuration matches Decision 4

*Alternative considered:* score post-redaction and add a "was anything redacted" signal as the real privacy metric. Rejected — it changes the meaning of a metric with recorded history, and `agent-evaluation`'s versioning requirement would force the whole series to be treated as superseded.

The separate "did the net fire" observation the spec requires is satisfied by the unit test plus the middleware's own log, not by a second eval run.

### 6. Variants move into email space, magnitudes held

`generate_sdlc_tickets.py:397-399` currently plants the hero under case/whitespace variants. Under addresses the variants become `Budi.Santoso@pertamina.com`, `budi.santoso@pertamina.com`, ` budi.santoso@pertamina.com ` — realistic, since mail local parts are treated case-insensitively in practice. The **number** of variants and the rows they cover are unchanged, so F7's 23.3 % and D5's counts carry over and the existing detecting queries still work after swapping the column's stated contents.

`skills/auditing-data-quality/SKILL.md:69` uses `COUNT(DISTINCT lower(trim(assigned_to)))` — which is already correct for addresses. Only its stated counts need re-verification against the regenerated table.

### 7. The `updates` channel is documented, not fixed

`routes.py:55` streams `stream_mode=["updates", "messages"]`. `_PIIStreamTransformer.process()` handles `messages`, `tools` and `values` and returns unmodified for anything else; `UpdatesTransformer` is its own protocol channel (`transformers.py:135`), not a projection of `values`.

Answer prose reaches the caller over `messages` and is covered. `utils.py:119` reads only **tool calls** off `updates`, so the uncovered payload is SQL text — which can carry an identity only in a `WHERE` clause the agent chose to write. Covering it means registering a custom `StreamTransformer`, which is a larger change to the streaming contract than this one should carry. Recorded as an uncovered surface per the spec, with the coverage claim scoped to the answer path.

### 8. `url` detection is not enabled

Five OKF `sources:` URLs in `wiki_seed/` are the citations the format rule requires the agent to reproduce. Redacting them would break traceability. Captured as a requirement rather than a comment so a later "turn on all the detectors" change is rejected on review.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Regenerating the table invalidates every expected value recorded in the Langfuse dataset. `agent-evaluation` states superseded expectations are not re-runnable. | Re-derive all expected values from the recorded verifying queries before the run; bump the version carried alongside the dataset. Hold magnitudes constant (Decision 6) so most expectations survive numerically even though they must be re-confirmed. |
| `volume-backed-wiki` is in-flight at 36/37 and its durable-write requirement still says *"personal name"*. Landing this first leaves that spec describing a guard that no longer matches the data. | Sequence: finish and archive `volume-backed-wiki` first, then land this. If that is not possible, update its requirement text in place as part of this change's task list. |
| The net silently rewrites an answer, so a model regression on rule 1 becomes invisible in production. | The eval runs with the net off and remains the regression signal. The middleware logs each redaction, making the rate observable in Langfuse. |
| `redact` produces `[REDACTED_EMAIL] closed 701 tickets` — private, and still a wrong answer per the format rule. | Stated as a requirement (`pii-redaction`: "a redacted answer is still a defective answer") so it is scored as a failure rather than accepted as compliance. |
| Two enforcement layers with different matching rules could disagree, e.g. an address the shape detector catches but the vocabulary does not. | Intended, and now explicit: Decision 2 records that the vocabulary is closed and the net is open, and each covers the other's blind spot. |

## Migration Plan

1. Land the derivation rule and regenerate `sdlc_tickets`; verify every documented magnitude against its recorded query before reloading.
2. Reload the table in the Jakarta workspace. The schema is unchanged, so this is a data replacement, not a migration.
3. Update `privacy.py`, then `scorers.py` to import from it.
4. Update the system prompt's People section and worked examples.
5. Add the middleware and the `redact_output` flag last — it is inert until the answer carries an address.
6. Re-derive the Langfuse expected values and bump the dataset version.

**Rollback:** steps 3–6 are ordinary reverts. Step 2 is the one-way door — regenerating replaces the table's contents, so the previous generation must be reproducible from its committed seed before step 1 begins.

## Open Questions

- Whether the mail domain should be `pertamina.com` or a workshop-specific domain. Affects no requirement, no query and no magnitude; it is a string constant chosen at implementation time.
