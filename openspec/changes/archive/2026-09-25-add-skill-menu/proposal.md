## Why

The `/skills/` tier has been wired since `migrate-to-deep-agent` but holds nothing: its single occupant, `skills/load-path-probe/`, states in its own body that it carries no procedure and is replaced by "the wiring-exercise change". That change is this one. Until it lands, three requirements in `deep-agent-loop` — progressive disclosure, on-demand reading, and *"an irrelevant skill is never read"* — are specified but not demonstrable, because a menu of one offers no selection to get right or wrong.

The workshop needs the opposite of a menu of one. Skill **selection** is the capability being taught: a real skill library is mostly irrelevant to any given question, and an agent that reads four bodies to answer a one-skill question has failed in a way no answer-quality score detects. That failure only becomes visible when the menu contains skills that compete.

## What Changes

- **Replace `skills/load-path-probe/` with a ten-skill menu**, five carrying real procedures and five deliberately over-broad, all ten wired into the live tier rather than described on paper.

- **Adopt the published Agent Skills authoring and enterprise standards** as the conformance target for every skill in the tier:
  - `name`: gerund form, ≤64 characters, lowercase/numbers/hyphens, no reserved words
  - `description`: third person, ≤1,024 characters, stating both *what* and *when*
  - SKILL.md body under 500 lines; bundled references exactly one level deep
  - No executable scripts, no network calls, no credentials, no MCP tool references — the whole tier stays markdown, which keeps it in the standard's lowest risk tier
  - **No instruction manipulation.** The standard rates "directives to ignore safety rules or alter Claude's behavior" as a High risk indicator and requires screening for it. This forbids the two sharpest distractors considered during exploration — one that supplied industry benchmark figures (defeating the system prompt's rule against numbers absent from the data and the wiki) and one that invited naming a top-performing individual (defeating the privacy rule). Both are rejected here **by the standard**, and recorded as rejected so the decision is not revisited.

- **Define the compliant distractor mechanism: an over-broad description over an honest body.** A distractor competes for selection and, once read, correctly redirects or declines. It costs a wasted read; it never causes a wrong answer. This is precisely the standard's named *Coexistence* failure mode — *"description is too broad, stealing triggers from existing Skills"* — installed deliberately so it can be measured rather than discovered in production.

- **The five core skills**, each carrying a procedure that is absent from `system_prompt.md` and non-obvious enough to justify a read:
  - `computing-target-adherence` — the breach procedure spanning the table and three wiki documents: working-time basis, per-(type, priority) thresholds, Bug and Incident scope only, exclusions reported with counts, period attributed by `closed_at`. Names `due_date` as the wrong basis.
  - `auditing-data-quality` — the planted defect classes and their detecting queries.
  - `splitting-planned-unplanned-work` — sprint-null as the unplanned marker and the effort-basis choice, which `sdlc-ticket-dataset` requires be answerable and the prompt gives no method for.
  - `measuring-sprint-velocity` — story points per sprint, where a 49%-null column makes the denominator the whole answer.
  - `escalating-breaches` — reads the escalation matrix and reports that it is past its `stale_after`, rather than embedding routing that would go stale in the same way.

- **The five distractors**, graded and justified individually: `checking-due-dates`, `explaining-ticket-history`, `benchmarking-against-industry`, `ranking-squad-performance`, `formatting-service-review`. Three compete with a core skill for the same question; two promise capabilities the data does not have.

- **Add the governance artifacts the enterprise standard requires** and the repository currently has nowhere to put: a registry recording purpose, owner, version, dependencies and evaluation status per skill; a completed security review checklist; and a stated separation of duties, since these skills are machine-authored and the review is the human contribution.

- **Score skill selection.** Per the standard, each skill gets 3–5 representative queries spanning should-trigger, should-not-trigger, and an ambiguous edge case. This measures *triggering accuracy*, which no existing scorer covers — `replace-agent-server` deliberately excluded skill reads from method scoring, correctly, because they are not statements against the data. They are now their own signal and need their own scorer.

- **Aim the distractors at questions the evaluation already asks.** The menu is not being designed against hypothetical questions: seven of the ten skills compete for items already in the Langfuse dataset, including three `value` items that the wiki made answerable and three `decline` items whose whole purpose is to be refused. A distractor that steals the trigger for `q-fastest-squad` or `q-ticket-narrative` is competing for a question whose correct answer is already recorded, so the collision is measurable against existing ground truth rather than only against the new selection set. Design.md carries the item-by-item map, including the two core skills with no existing coverage and the one decline item no skill competes for.

- **Rejected: keeping the ten skill names from the original request.** Seven of them (`interpret-request`, `check-schema`, `query-tickets`, `aggregate-tickets`, `retrieve-sop`, `validate-and-present`, and most of `compute-metric`) restate content already carried in `system_prompt.md`. A skill that restates the prompt is a tax paid twice — once on every request for its description, once again on the read. One of the seven survives as `formatting-service-review`, kept precisely *as* a distractor so the menu demonstrates the cost.

## Capabilities

### New Capabilities
- `agent-skill-menu`: What the `/skills/` tier contains and how it is governed — the authoring standard each skill conforms to, the prohibition on bodies that contradict the system prompt's safety rules, the deliberate-distractor design and its limits, the registry and security-review record each skill carries, and the requirement that selection accuracy be measured before the menu grows.

### Modified Capabilities
- `deep-agent-loop`: The requirement *Skill content is disclosed progressively* is specified against a menu where relevance is unambiguous — its scenario reads *"a request unrelated to any discovered skill"*. With a menu whose descriptions deliberately compete, not-reading-the-unrelated is no longer sufficient: the requirement changes to selecting the correct skill among several plausible ones, and to bounding how many bodies a single request may read.
- `agent-evaluation`: Evaluation currently scores the answer and the method, where method means statements issued against the data — skill reads are explicitly excluded. A menu built to be mis-selected makes selection a scored behaviour in its own right, distinct from both.

## Impact

- **`skills/`** — `load-path-probe/` deleted; ten skill directories added, each `SKILL.md` only. New `skills/REGISTRY.md` and `skills/SECURITY-REVIEW.md`, which are not skills: `_skills_present()` and the loader both glob `*/SKILL.md`, so a top-level file is readable at `/skills/` without being loaded as a menu entry. **To verify, not assume** — see design.
- **`agent_server/agent.py`** — expected unchanged. `SKILLS_DIR`, the deny rule, and the startup log already handle *n* skills. Any change here is a finding, not a plan.
- **`agent_server/prompts/system_prompt.md`** — small and subtractive if anything. The menu must not duplicate the prompt; where a core skill now carries a procedure, the prompt should point rather than repeat. Deliberately minimal, because the prompt is the one variable the recorded eval baseline is most sensitive to.
- **`agent_evaluation/`** — a skill-selection scorer and its query set. This is a **new measurement, not a change to the existing one**: answer-quality items and their expected values are untouched, so scores stay comparable to the recorded baseline.
- **Model coverage** — the standard requires testing across the models in use. The agent runs `databricks-gpt-5-2` and the judge runs `gpt-oss-120b`; neither is a Claude model, so the standard's Haiku/Sonnet/Opus matrix is satisfied in intent (test on the models you actually deploy) rather than literally. Recorded so the deviation is deliberate.
- **Cross-surface** — this repository already contains the split the standard warns about: `.claude/skills/` are development-time skills for Claude Code, `skills/` are runtime skills for the deployed agent. They are separate surfaces that do not sync, and nothing should attempt to unify them.
- **Out of scope** — whether `due_date` should remain a noise column is a `sdlc-ticket-dataset` question, not this change's. `checking-due-dates` treats it as it currently is: present, plausible, and carrying no priority signal.
