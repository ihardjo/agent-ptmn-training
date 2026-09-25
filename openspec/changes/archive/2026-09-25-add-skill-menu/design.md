## Context

See proposal.md — *Why*. The mechanism this change fills already exists and needs no work: `build_backend()` mounts `skills/` read-only at `/skills/`, `filesystem_permissions()` denies writes there, and `init_agent()` logs the discovered count. What is missing is content.

Two constraints shape everything below.

**The published standard is the conformance target, and it is prescriptive about the thing this change is built around.** It rates *"directives to ignore safety rules or alter Claude's behavior"* a High risk indicator, requires a reviewer to screen for adversarial instructions, and names *Triggering accuracy* and *Coexistence* as the first two evaluation dimensions. That combination rules out one distractor design and hands over a better one.

**The standing instructions are already very full.** `system_prompt.md` runs about 200 lines across five slots and carries most of what a naive skill menu would say. Anything a skill duplicates is paid for twice, and the prompt is also the variable the recorded evaluation baseline is most sensitive to — so the menu is designed to sit *beside* the prompt, not on top of it.

## Goals / Non-Goals

**Goals:**
- A ten-skill menu where selecting correctly is a distinguishable act, and selecting wrongly is cheap.
- Conformance that a script checks, not a reviewer's memory.
- Governance records that exist in the repository rather than in someone's head.

**Non-Goals:**
- No change to the loop, the backend, or the permission rule. If `agent.py` needs editing, something was wrong before this change and it is a finding.
- No answer-quality dataset changes. Selection is a new measurement laid alongside the existing one, so baseline comparability survives.
- No resolution of whether `due_date` should be a noise column. That belongs to `sdlc-ticket-dataset`.
- No attempt to unify `.claude/skills/` with `skills/`. Different surfaces, deliberately.

## Decisions

### 1. Distractors compete through the description, never through the body

The sharpest distractors considered during exploration carried *wrong* bodies: one supplying industry benchmark figures, one inviting the agent to name its top performer. Both would have produced vivid workshop moments and both are forbidden — the standard's risk table rates instruction manipulation High, and its review checklist requires screening for exactly these. A skill authored to demonstrate a failure is indistinguishable at runtime from one authored to cause it.

The compliant mechanism is better anyway. A distractor gets an over-broad **description** and a correct **body**:

```
   description  ──── competes for selection ────▶  the distractor's job
        body    ──── redirects or declines   ────▶  the safety property
```

Cost of a mis-selection is one wasted read. The lesson survives intact because it was never about the wrong answer — it was about *Triggering accuracy*, which the standard names as evaluation dimension one. The workshop demonstration becomes a trace with three skill reads where one would do, which is the failure that actually happens in production libraries.

*Alternative considered:* omit distractors and ship five core skills. Rejected — it returns the menu to the state where selection cannot be observed, which is the problem this change exists to fix.

### 2. Gerund naming across all ten

The standard recommends gerund form and separately warns against *"inconsistent patterns within your skill collection"*. Noun phrases are an acceptable alternative, but mixing them is not. The existing `load-path-probe` is a noun phrase and is being deleted, so there is no legacy to preserve — the menu starts consistent.

### 3. Frontmatter stays at `name` and `description`; governance lives beside the skills

The enterprise standard wants a registry recording purpose, owner, version, dependencies, and evaluation status. The authoring standard specifies exactly two frontmatter fields.

**Verified in task 1.5: `deepagents` 0.7.15 does tolerate extra frontmatter keys.** A skill carrying `owner`, `version`, `evaluation_status`, and `dependencies` alongside `name` and `description` was discovered, selected, and read with no exception. So this decision is no longer forced by the library, and stands on its own merits instead:

- The authoring standard specifies two fields. Extra keys work *here* and are non-standard everywhere, so a skill that relies on them is one that only this runtime can load.
- The enterprise standard asks for "an internal registry" — a catalog, singular. Governance scattered across ten frontmatter blocks is not a catalog and cannot be reviewed at a glance.
- The agent can read one registry file and answer questions about its own menu. It cannot aggregate ten frontmatter blocks without reading all ten, which is the cost progressive disclosure exists to avoid.

So governance goes in two top-level files:

```
skills/
├── REGISTRY.md          ← purpose · owner · version · dependencies · eval status
├── SECURITY-REVIEW.md   ← the checklist, completed, per skill
└── <ten skill dirs>/SKILL.md
```

Both `_skills_present()` and the loader glob `*/SKILL.md`, so a file at the tier root is not a skill. **Verified in task 1.4:** with `REGISTRY.md` present the loaded count stayed at 10, and the agent listed `/skills/` and read `/skills/REGISTRY.md` on request. The registry is readable by the agent without being a menu entry, which is the property this layout was chosen for.

### 4. Conformance is a script, following the shape `check-okf` already set

The repository already has the pattern: `uv run check-okf` checks a bundle of markdown-with-frontmatter against a published format. Skills are a bundle of markdown-with-frontmatter against a published format. `uv run check-skills` checks name form and length, description non-emptiness, length, and third person, body line count, reference depth, registry/tier correspondence, and absence of scripts, URLs, and credentials.

*Alternative considered:* a review checklist in the PR template. Rejected — the standard requires the human review *as well*, but a limit a person checks by eye is a limit that drifts.

### 5. Selection is scored from the trace, in its own query set

**Corrected after task 1.3.** This decision previously said skill reads are distinguishable in the trace *by tool name*. They are not. A skill read is an ordinary `read_file` call:

```
read_file  {"file_path": "/skills/converting-timezones/SKILL.md", "limit": "1000"}
```

and `read_file` is the same tool that serves `/wiki/openwiki/` and `/wiki/notes/`. The distinguishing signal is the **`/skills/` path prefix in the `file_path` argument**, not the tool name — which is the tiered filesystem working exactly as `deep-agent-loop` specifies, since the prefix is what identifies the tier.

Three consequences for the scorer:

- It SHALL match on `file_path` starting with `/skills/`, and SHALL NOT match on tool name. A scorer keyed to a tool name would silently count every wiki read as a skill read, inflating selection cost on exactly the adherence questions where wiki reads are correct and expected.
- The skill *name* is the second path segment, so the scorer recovers which skill was read by parsing the path rather than by string-matching the body.
- The existing `wiki_was_read` evaluator has the mirror-image requirement and must keep matching only `/wiki/`. The two evaluators partition `read_file` calls between them and neither may claim the other's.

With that correction the underlying claim holds: skill reads remain excluded from method scoring, as `replace-agent-server` established, and selection scoring reads the same calls for the opposite purpose.

The 30–50 selection queries (3–5 per skill, per the standard) go in a **separate** set from the Langfuse answer-quality dataset. Mixing them would change the denominator of every existing score and break comparison with the recorded baseline for no benefit — the two measure different things and fail independently.

### 6. The collision map is the design

Which skill competes with which is the substance here, not an implementation detail:

```
  CORE                                  DISTRACTOR              collision
  ────────────────────────────────────────────────────────────────────────────
  computing-target-adherence   ◀────▶   checking-due-dates      "SLA", "breach",
                                                                "overdue", "telat"
  computing-target-adherence   ◀────▶   benchmarking-against-   "is this good?",
  measuring-sprint-velocity             industry                "how do we compare?"
  (all five)                   ◀────▶   formatting-service-     "report", "table",
                                        review                  "laporan"
  ────────────────────────────────────────────────────────────────────────────
  (none — promises an absent capability)  explaining-ticket-history
  (none — promises an absent capability)  ranking-squad-performance
```

`checking-due-dates` is the sharpest and is the user's original `/check-due-sla`, kept deliberately. Its description is honest about what it does — it really does compare against `due_date` — and its body opens by stating that `due_date` carries no priority signal (medians of 32/31/32/33 days across P1–P4) and is not the policy target, then sends the agent to `computing-target-adherence`.

**Redirects must form a directed acyclic graph.** Distractors point at core skills; core skills point at nothing. Two skills that redirect to each other would spend the request bouncing between them. `formatting-service-review` points at the standing instructions, which is outside the graph entirely.

### 6a. Where each skill lands on the existing evaluation dataset

The collision map above is about descriptions competing with each other. This one is about which *already-recorded* questions each skill competes for, and it matters for two reasons: a collision over a question with existing ground truth can be measured before the new selection set exists, and a skill competing for a `decline` item is competing for a question whose correct answer is to refuse.

| Skill | Existing items it competes for | Kind |
|---|---|---|
| `computing-target-adherence` | `q-p2-target-adherence`, `q-sla-breach-count`, `q-target-trend` | value |
| `auditing-data-quality` | `q-closed-before-created`, `q-done-without-resolution`, `q-distinct-assignees`, `q-normalisation-method` | value, claim |
| `splitting-planned-unplanned-work` | `q-unplanned-effort-share` | value |
| `measuring-sprint-velocity` | *(none)* | — |
| `escalating-breaches` | *(none)* | — |
| `checking-due-dates` | `q-p2-target-adherence`, `q-sla-breach-count`, `q-target-trend` | value |
| `benchmarking-against-industry` | `q-p2-target-adherence`, `q-target-trend`, `q-points-predict-duration` | value, claim |
| `explaining-ticket-history` | `q-ticket-narrative`, `q-ticket-people` | decline |
| `ranking-squad-performance` | `q-fastest-squad` | decline |
| `formatting-service-review` | `q-assignee-ranked-table`, `q-raw-rows` | value, claim |

Four things follow.

**The `checking-due-dates` collision is head-on, over three items at once.** It competes with `computing-target-adherence` for exactly the items `add-volume-backed-wiki` flipped from `decline` to `value` when the wiki supplied the target. Those items carry the `wiki_was_read` evaluator, so a mis-selection is detectable in two independent ways: the figure is wrong, and the wiki was never read. This is the sharpest measurement in the change and task 5.5 already targets it.

**`ranking-squad-performance` and `explaining-ticket-history` compete for refusals.** `q-fastest-squad` records `missing_fact: "any squad or team field; component and project are not teams"` — which is close to verbatim what that skill's body must say. The distractor is therefore not merely harmless when selected; reading it should make the refusal *more* reliable, not less. If the selection measurement shows the opposite, the body is wrong and not the design.

**`formatting-service-review` competes for a privacy item.** `q-assignee-ranked-table` asks for a ranked table of top assignees and is scored for whether a person is named. A broad formatting skill stealing that trigger is the one case in the menu where a distractor sits next to a hard safety rule. Its body must therefore defer to the standing instructions on the rank-not-name rule rather than restating it, so there is no second, weaker copy of that rule anywhere in the tier.

**Two core skills have no existing coverage, and one decline item has no competitor.** `measuring-sprint-velocity` and `escalating-breaches` are answerable only through questions the dataset does not yet ask; their selection queries under task 5.1 will be the first items that exercise them, and their answer quality stays unmeasured by the existing dataset. In the other direction `q-defects-per-release` — declined for want of a release field — has no skill competing for it, so it serves as a control: a decline that no distractor can explain away.

*Alternative considered:* adding answer-quality items for the two uncovered core skills as part of this change. Rejected — it changes the denominator of the recorded baseline, which Decision 5 exists to protect. Those items belong to a follow-up whose only job is extending coverage.

### 7. Descriptions, since the description *is* the distractor

Third person, what-and-when, well inside 1,024 characters. These are the design artifact; the bodies are implementation.

| Skill | Description (abridged) |
|---|---|
| `computing-target-adherence` | Computes resolution-target adherence and breach counts for Bug and Incident tickets by combining ticket data with the targets held in the wiki. Use when asked whether targets were met, or for breach counts and adherence rates. |
| `auditing-data-quality` | Detects data-quality defects: closure before creation, closed tickets with no resolution, durations against unclosed work, status disagreeing with its category, assignee names differing only by case or whitespace. Use before reporting a figure a defect would distort. |
| `splitting-planned-unplanned-work` | Computes the split of effort between planned delivery work and unplanned operational work, using work type and the absence of a sprint. Use when asked about capacity allocation. |
| `measuring-sprint-velocity` | Computes sprint velocity from story points, handling the large share of tickets carrying no story-point value. Use when asked about velocity or throughput per sprint. |
| `escalating-breaches` | Applies the escalation matrix to breached tickets and reports the matrix's review status alongside its routing. Use when asked who should be notified about a breach. |
| `checking-due-dates` | Checks tickets against the `due_date` field to find work closed after its due date or now past due. Use when asked about overdue tickets, late work, missed deadlines, or SLA breaches. |
| `explaining-ticket-history` | Explains what happened on an individual ticket by reconstructing events from its recorded fields. Use when asked to describe or narrate a specific ticket by identifier. |
| `benchmarking-against-industry` | Places delivery and service metrics in context against external comparators. Use when asked whether a figure is good or how performance compares to other organisations. |
| `ranking-squad-performance` | Ranks squads, teams, and delivery groups by resolution speed and throughput. Use when asked which team performs best. |
| `formatting-service-review` | Formats findings as a table with sources for the weekly service review. Use when asked for a report, a summary table, or output suitable for review. |

### 8. The system prompt changes as little as possible, and subtractively

Where a core skill now owns a procedure, the prompt should point rather than repeat. But the prompt is what the recorded baseline is most sensitive to, so the first pass changes **nothing** and the menu is measured against the existing prompt. Prompt trimming is a follow-up with its own before-and-after, not a confound inside this one.

## Risks / Trade-offs

- **`deepagents` reads more skills than expected, or eagerly** → The whole progressive-disclosure claim rests on library behaviour observed with a menu of one. Verified explicitly with ten before anything else is built; if disclosure is not lazy at ten, the menu is the wrong shape and this change stops.

- **A root-level `REGISTRY.md` disturbs discovery** → Predicted safe from the `*/SKILL.md` glob, verified in task 1. Fallback is `docs/skills/`, at the cost of the agent no longer being able to read its own registry.

- **Selection accuracy degrades at ten on `databricks-gpt-5-2`** → This is the measurement, not a failure of it. The standard's guidance is to stop adding when performance degrades; ten is well inside the 20-per-request ceiling but the model is not a Claude model and its recall is unmeasured. A poor result is a publishable finding and a reason to consolidate.

- **The distractors work too well and never fire** → Then the workshop loses its vivid moment and production gains a clean agent. Acceptable: the measurement is the artifact either way, and a demonstration can be staged live by removing a body's corrective paragraph without ever shipping it.

- **Ten descriptions dilute each other and hurt a skill that worked alone** → This is the standard's *Coexistence* dimension and the reason selection is re-measured across the whole menu whenever one is added, per the spec.

- **Bodies drift from the wiki they cite** → `computing-target-adherence` and `escalating-breaches` restate rules that live in `/wiki/openwiki/`. If the wiki changes, the skills are stale and nothing detects it. Mitigated by recording the dependency in the registry so the blast radius is discoverable, and by having the bodies cite and defer to the wiki rather than duplicate its numbers. Not eliminated.

## Migration Plan

1. Verify library behaviour at ten skills and with root-level non-skill files. Stop if disclosure is not lazy.
2. Land the conformance checker before the skills, so no skill is ever written unchecked.
3. Land the five core skills; measure answer quality against the recorded baseline to confirm no regression.
4. Land the five distractors; measure selection.
5. Land registry, security review, and the human review pass.

Rollback is deleting directories: the tier degrades to empty, `_skills_present()` returns false, and the agent starts and serves without skills — a path `migrate-to-deep-agent` already verified.

## Open Questions — both resolved, see measurement.md

**1. Where the selection query set lives — resolved: the repository.**
`agent_evaluation/skill_selection.py`, driven by `uv run
measure-skill-selection`. Langfuse's value for the answer-quality dataset is
stable item ids that make run-to-run comparison possible, at the cost that
ids are reserved per project and expectations must be mutated in place. The
selection set needs neither: its expectations are derived from the menu, so
they *should* change when the menu changes, and keeping it in the repository
means a description edit and the expectation it invalidates land in the same
diff. Comparability comes from `measurement.md` recording the baseline.

**2. Whether `formatting-service-review` earns its slot — resolved on
evidence, kept anyway.** It scored 100 % and stole no triggers, which is
exactly the documented condition for dropping the menu to nine: it costs
nothing and therefore demonstrates nothing. It is retained because ten
skills with five distractors is the requested shape, and because a
zero-cost prompt-duplicating skill is itself the demonstration — it is the
one entry that can be pointed at to show why seven of the originally
requested ten were rejected. Recorded so the choice is visible as a choice.

## Open Questions

- **Why the agent under-reads.** The menu was designed against over-reading
  and the measurement found the opposite: every selection failure is a
  missed read, never a surplus one. Whether that is a property of this
  model, of descriptions that are too narrow, or of a system prompt that
  already answers most questions is not answerable from one run, and it is
  the question that decides what to change next.
