## Why

The agent's privacy rule — never name an individual — is enforced structurally on exactly one surface. A write to `/wiki/notes/` is refused by `_name_guard` ([backends.py:321](../../../agent_server/backends.py#L321)); the **chat answer is protected by instruction alone**. Nothing in the system refuses a name on its way to the caller, so the guarantee holds only while the model chooses to honour it.

That gap is worth closing on its own terms. It is worth closing *now* because the identity columns are moving to email form, and the vocabulary check the current guard is built on does not see an email as an identity at all:

```
names_in("Budi Santoso closed 701 tickets")           → ['budi santoso']
names_in("budi.santoso@pertamina.com closed 701")     → []          ← verified
```

`normalise()` collapses whitespace only, so `budi santoso` (space) never matches `budi.santoso` (dot). Left unaddressed, the migration would silently convert a working guard into a guard that passes everything — and because the evaluation's `no_pii_leak` scorer is built on the same name vocabulary, the leak would be scored green. The guard and the test that covers it would go blind together.

## What Changes

**Identity columns become email-valued**

- `reported_by` and `assigned_to` hold email addresses instead of person names. Addresses are **derived** from the existing `FIRST_NAMES`/`LAST_NAMES` constants by a documented, deterministic rule, so an address can be folded back to one identity.
- The schema stays at **24 columns** with unchanged types. No new escaping cases; the three backtick-requiring custom fields are untouched.
- **BREAKING** for anything that reads those two columns as display names — the system prompt's People section, the `auditing-data-quality` skill's normalisation query, and the F7 concentration figures.
- The planted spelling-variant defect moves into email space (`Budi.Santoso@…` vs `budi.santoso@…`), preserving the lesson that identities must be normalised before aggregating. Row counts and the hero's 23.3 % share are held constant.

**A redaction net on the answer**

- `PIIMiddleware("email", strategy="redact", apply_to_output=True)` is added to the agent's middleware list, with `apply_to_input` and `apply_to_tool_results` both off.
- Tool results deliberately keep their addresses: the agent *must* group by identity to find the distribution. The constraint is on what it writes, not what it queries.
- The middleware is a **net, not the control**. The required output form is a rank (`1 (tertinggi)`, `2`, `3`) — a whole-result-set transformation that per-span substitution cannot produce. `[REDACTED_EMAIL] closed 701` is private and still wrong. The system-prompt rule stays primary; the net catches what escapes it.

**The write guard is repurposed, not replaced**

- `privacy.py` is **kept**. It has exactly one consumer and `PIIMiddleware` cannot take it over: `after_model` inspects `last_ai_msg.content`, while a durable write travels as a tool-call *argument* on `.tool_calls`, which the middleware never reads.
- It changes from a *name* vocabulary to an *identity* vocabulary matching both the name form and the derived email form.
- Its docstring currently claims the guard and the evaluation scorer "cannot drift apart." They are two independent code paths over the same constants and can drift freely. The claim is removed and the duplication is made explicit.

**Evaluation keeps measuring the model, not the net**

- `no_pii_leak` scores the model's output **before** redaction, so it continues to measure whether the agent obeyed the rule. A scorer reading post-redaction output would return 1.0 unconditionally and measure nothing.
- A separate score records whether the net fired — an agent that leaks and gets caught is materially different from one that never leaks, and a single verdict would hide which happened.

**Explicitly out of scope**

- `PIIMiddleware("url")` is **not** enabled. The five OKF `sources:` URLs in `wiki_seed/` are required citations; redacting them would break the traceability the format rule mandates.
- The `updates` stream channel is documented as an unscrubbed surface rather than fixed. `routes.py:55` streams `["updates", "messages"]`; the middleware's stream transformer handles `messages`/`tools`/`values` and passes `updates` through untouched. Answer prose is covered via `messages`; tool-call arguments on `updates` are not.

## Capabilities

### New Capabilities

- `pii-redaction`: Output-side detection and redaction of identity-bearing values in what the agent returns to a caller. Covers where redaction applies and where it must not, why detection by *shape* complements the closed-vocabulary guard rather than replacing it, the requirement that a detected leak degrade the answer rather than fail the run, and the surfaces the net does not reach.

### Modified Capabilities

- `sdlc-ticket-dataset`: adds a requirement fixing the identity columns as email-valued and derived from a documented rule; the planted spelling-variant defect is restated in email form so its detecting query and row count remain valid.
- `agent-evaluation`: the privacy-check requirement currently reasons from "the set of person names present in the source data is known." The known set is now identities in email form, and the check must cover both spellings. The requirement is also extended to state that the privacy score measures the agent's own output rather than a redacted copy of it.

## Impact

| Area | Change |
|---|---|
| `scripts/generate_sdlc_tickets.py` | email derivation rule; identity values; variant plant at L397–399; F7/D5 verification queries |
| `agent_server/privacy.py` | name vocabulary → identity vocabulary; docstring correction |
| `agent_server/agent.py` | add `PIIMiddleware` to the middleware list (L237) |
| `agent_server/prompts/system_prompt.md` | People section; worked examples showing identity values |
| `agent_evaluation/scorers.py` | `PERSON_NAMES` → identity set; pre-redaction scoring; net-fired score |
| `agent_evaluation/dataset.py` | 13 `forbid_person_names` items re-verified against email data |
| `skills/auditing-data-quality/SKILL.md` | normalisation query (L69) and its stated counts |
| `tests/` | `test_volume_backend.py`, `test_wiki_tier.py`, `test_eval_wiki.py`, `conftest.py` |
| Data | `sdlc_tickets` must be regenerated and reloaded; expected values in the Langfuse dataset re-derived |

**Dependencies and risks**

- The durable-write privacy requirement lives in `volume-backed-wiki`, an **in-flight change at 36/37 tasks** whose specs are not yet under `openspec/specs/`. This change does not modify that capability, but the two must not land inconsistently — `volume-backed-wiki` should be completed and archived first, or its requirement updated in place to say *identity* rather than *personal name*.
- No new dependency. `PIIMiddleware` ships with the already-pinned `langchain>=1.4.1` and the agent already passes a `middleware` list.
- Regenerating the table invalidates every recorded expected value. Per `agent-evaluation`'s versioning requirement, superseded expectations are not re-runnable, so the version carried alongside the dataset must be bumped when this lands.
