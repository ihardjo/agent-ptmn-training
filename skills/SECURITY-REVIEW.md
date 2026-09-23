# Security review of the skills tier

The published enterprise guidance requires a completed review checklist before
any skill is deployed, and requires that the reviewer not be the author. These
skills were machine-authored, so the human review **is** the control, not a
formality on top of one.

Reviewed: all ten skills.
Automated portion: `uv run check-skills`, which runs as preflight step 1.

## Risk tier assessment

| Risk indicator | Finding | Level |
|---|---|---|
| Code execution | No `.py`, `.sh`, `.js`, `.rb`, `.pl` or `.ps1` in any skill directory. The tier is markdown only. Enforced by `check-skills`. | None |
| Instruction manipulation | No skill directs the agent to ignore, weaken, or condition any rule in its system prompt. See *Rejected designs* below — this is the indicator that shaped the change. | None |
| MCP server references | No skill names an MCP server or a fully-qualified tool. Skills describe method; the agent selects its own tools. | None |
| Network access patterns | No URLs. No `fetch`, `curl`, or `requests`. Enforced by `check-skills`. | None |
| Hardcoded credentials | None. Enforced by `check-skills` against a credential-shaped pattern. | None |
| Filesystem access scope | Skills reference `/wiki/raw/` documents by absolute path — reads of a tier the agent already has, and which is read-only to it by the deny rule in `filesystem_permissions()`. No `../` traversal; enforced by `check-skills`. | Low |
| Tool invocations | Skills contain SQL for the agent to run against one table through its read-only tool, and direct it to read named wiki documents. No writes are directed anywhere. | Low |

## Review checklist

1. **All directory content read.** Ten `SKILL.md` files plus `REGISTRY.md` and
   this file. No bundled references, no scripts, no other resources.
2. **Script behaviour matches stated purpose.** Not applicable — no scripts.
   The SQL carried in `auditing-data-quality`, `measuring-sprint-velocity` and
   `summarising-root-causes` was executed against the live table and returns
   what the skill says it returns.
3. **Checked for adversarial instructions.** None found. No skill instructs
   the agent to hide activity, alter behaviour conditionally on the asker, or
   relax a safety rule. `formatting-service-review` does the opposite: it
   restates that the privacy and no-invented-figures rules survive a request
   for a formatted table.
4. **Checked for external URL fetches or network calls.** None.
5. **No hardcoded credentials.** None.
6. **Tools and commands the skills direct.** Read-only SQL against
   `workshop_ai_platform.example.sdlc_tickets`; reads of `/wiki/raw/`
   documents. No skill directs a write to any tier. Considered in
   combination: the tier grants read of governed data and read of governed
   policy, with no network path out, so the file-read and network-tool
   combination the guidance warns about does not arise.
7. **Redirect destinations confirmed.** Every cross-skill reference resolves
   to a skill in this tier; the reference graph is acyclic and no core skill
   points at a distractor. Enforced by `check-skills`.
8. **No data exfiltration patterns.** No skill reads sensitive data and then
   writes, sends, or encodes it. The privacy rule governing what may appear in
   an answer lives in the system prompt and is not weakened anywhere here.

## Rejected designs, and why

Two distractors considered during design would have carried **wrong bodies**
rather than merely over-broad descriptions. Both are recorded here so the
decision is not revisited as though it were untested:

| Rejected | Would have | Indicator triggered |
|---|---|---|
| A benchmarking skill supplying industry figures | Directed the agent to state numbers neither the data nor the wiki contains, defeating the system prompt's second standing rule | Instruction manipulation — **High** |
| An `identify-top-performers` skill | Directed the agent to name an individual, defeating the system prompt's first standing rule, on data that is real Pertamina staff | Instruction manipulation — **High** |

Both were rejected on the content, not on the motive. A skill authored to
demonstrate a failure is indistinguishable at runtime from one authored to
cause it.

The teaching value survives the rejection: a distractor competes through its
**description**, and the failure it demonstrates is a wasted read — which is
the *Triggering accuracy* dimension the same guidance names first. The
surviving distractors keep the attracting description and decline honestly in
their bodies.

A third skill on the same pattern, `benchmarking-against-industry`, was
reviewed and admitted at version 1 and has since been **withdrawn** — not on a
finding, but because it drew on only one evaluation item and its lesson was
carried better elsewhere. Recorded here so its absence reads as a decision
rather than an omission.

## Model coverage deviation

The guidance asks for testing across Haiku, Sonnet and Opus. This agent does
not run on a Claude model: the agent is `databricks-qwen35-122b-a10b` and the
evaluation judge is `gpt-oss-120b`. The requirement is satisfied in intent —
test on the models actually deployed — and the selection set was run against
the deployed agent model. Recorded so the deviation is deliberate rather than
an omission.

## Separation of duties

Authored by Claude Opus 5 under `/opsx:apply`.

**Accepted for deployment by ihardjo (the repository maintainer) on
2026-09-23, against the ten-skill menu recorded in `REGISTRY.md`.** That menu
supersedes the one accepted on 2026-09-21: `benchmarking-against-industry`
withdrawn, `summarising-root-causes` added, every other skill unchanged at
version 1. The maintainer did not author the tier, which is the separation the
guidance requires.

What that acceptance covers, stated precisely so a later auditor is not
misled: the maintainer was given the menu's contents, the distractor
mechanism, the two rejected designs and the risk indicator each triggered, the
conformance results, and the selection measurement — and directed that the
change be completed and deployed. It is an informed acceptance decision by a
second party. It is **not** a line-by-line reading of all ten bodies, and this
document does not claim to be one.

The automated portion — `uv run check-skills`, running as preflight step 1 —
covers the mechanical indicators in the table above on every run, and is what
holds the line between reviews.

Re-review is required when any skill changes, per the guidance's rule that
every update is a new deployment requiring full security review.
