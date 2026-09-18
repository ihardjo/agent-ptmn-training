## Context

See proposal.md — Why. The current state that constrains the approach:

- `agent_server/agent.py` builds a `CompositeBackend` with `StateBackend()` as the default and one route, `/skills/`, served by a `FilesystemBackend` in `virtual_mode`. Routing is longest-prefix; every routed result is remapped back under its prefix, so the prefix survives into listings.
- `/skills/` is made read-only by a `FilesystemPermission(operations=["write"], mode="deny")` rule, not by the backend refusing. The archived `migrate-to-deep-agent` design states the principle: telling the agent not to write is not a control, a rule that refuses the write is.
- That same design fixed a provenance rule — *repository means a person wrote it, Volume means the agent did* — which this change breaks. OpenWiki content is human-authored and arrives on the Volume. Hence the `deep-agent-loop` delta.
- OKF v0.2 is the *format* the tier is written in, not a second source system. Its conformance bar is deliberately low: parseable frontmatter with a non-empty `type` on every non-reserved document, and reserved meanings for `index.md` and `log.md`. Everything else in the spec is SHOULD.
- **Databricks Apps have no FUSE mount for Unity Catalog Volumes.** `FilesystemBackend(root_dir=...)` cannot be pointed at one. Volume access is the Files API: `upload`, `download`, `list_directory_contents`, `delete`, `create_directory`, `get_metadata`.
- `BackendProtocol` is an ABC whose async methods default to `asyncio.to_thread(self.<sync>)`. A backend implementing only the sync methods is complete and does not block the event loop.
- The data lives in another workspace and region, reached by a dedicated service principal whose UC grants are confined to `workshop_ai_platform.example` — `cross-workspace-sql` makes those grants the enforcement boundary.
- `agent_evaluation/` scores 19 items; four expect a refusal for want of a resolution target, carrying a comment that they flip when a wiki supplies one. Four of eight evaluators read the statements the agent issued, and a `wiki_was_read` evaluator was deliberately not built because there was no wiki.
- The agent's privacy rule is enforced by checking answers against the *known* set of names in the source data, rather than by asking a model whether privacy was respected.

## Goals / Non-Goals

**Goals:**
- One tier, two prefixes, each with a single provenance and a single writability — readable off the path alone.
- Read-only enforced at the strongest layer available, not only in middleware.
- A tier whose absence is survivable, because the course is taught on laptops that may not have the credential.
- A seeded, committed corpus, so the eval flip is reproducible without access to the real internal systems.

**Non-Goals:**
- **How content gets from OpenWiki onto the Volume.** No connector, no scheduled job, no change-detection. This change consumes a populated Volume; population is an upstream concern with its own owner.
- No semantic search over the wiki. The agent lists and reads files. Vector Search over the corpora is a later change if retrieval quality demands it.
- No per-user scoping. Notes are shared, which is what was asked for; per-user memory is a different capability (`managed-memory` or Lakebase) and not this one.
- No change to `utils.py` or the wire format. A wiki read is an ordinary tool call and renders as one.

## Decisions

### 1. A custom `VolumeBackend` over the Files API

`agent_server/backends.py` gains `VolumeBackend(BackendProtocol)` implementing `ls`, `read`, `write`, `edit`, `delete`, `glob`, and `grep` against `w.files.*`, constructed with the Jakarta workspace client `tools.py` already builds. Only the sync methods are written; the protocol's `asyncio.to_thread` defaults supply the async half.

`grep` and `glob` are `list_directory_contents` plus `download` in Python. There is no ripgrep to delegate to and no local file to hand it. This is acceptable because the corpora are small text documents; it would not be if the wiki grew to thousands of files, which is the trigger to revisit Non-Goal 2.

*Alternative considered.* Stage the Volume to local disk at startup and mount it with `FilesystemBackend`. Rejected: it makes writes a two-phase problem, it makes every container hold a stale copy, and it puts agent-writable content back on ephemeral disk — the thing `build_backend()`'s default deliberately avoids.

### 2. One Volume, two directories, read-only enforced in middleware

```
CompositeBackend(
    default = StateBackend(),                 #  /                  turn scratch
    routes  = {
        "/skills/":          FilesystemBackend(<repo>/skills, virtual_mode=True),
        "/wiki/openwiki/":   VolumeBackend(<wiki_volume>, subdir="openwiki"),
        "/wiki/notes/":      VolumeBackend(<wiki_volume>, subdir="notes"),
    },
)
```

One Volume — `workshop_ai_platform.example.agent_wiki`, which already existed in the workshop schema, empty and unused — with two top-level directories. It was three in the first draft, which treated OKF as a source system alongside OpenWiki; OKF is the format the whole bundle is written in, so the directory dissolved. The service principal gets `READ VOLUME` + `WRITE VOLUME` on it, one grant pair, one resource to provision. Read-only on the source directory is enforced by `FilesystemPermission(operations=["write"], paths=["/wiki/openwiki/**"], mode="deny")`, exactly the mechanism that already protects `/skills/`.

**Be clear about what this does and does not buy.** A UC volume grant is per-volume, not per-path, so the credential the agent holds *can* write to the source directory. What stops it is the permission rule in its own process. That is a real control — it holds against an injected instruction as well as against the agent's own initiative, which is the argument the archived design makes for the skills deny — but it is a narrower one than a grant: a bug in route configuration, or any code path that reaches `VolumeBackend` without going through the middleware, gets a writable handle on human-authored content.

Two things make that acceptable here. The `/skills/` tier already sets this precedent for the content that matters most, since skills reach the system prompt and wiki documents do not. And the failure mode is recoverable: source content is a copy, reproducible by re-running the seed or the upstream sync, so a bad write costs a refresh rather than the document.

*Alternative considered.* Two Volumes — `wiki_sources` granted `READ VOLUME` only, `wiki_notes` granted read and write — making read-only a property of the credential rather than of the process, in line with `cross-workspace-sql` making UC grants the enforcement boundary. Rejected for the operational cost: two resources, two grant pairs, and two things to get right in every workspace the course is taught in. If source content is later populated by a real sync from OpenWiki rather than a committed seed, the calculus changes — an agent that can silently corrupt synced content is worse than one that can corrupt a fixture — and this is the decision to revisit.

### 3. The Volume lives in Jakarta, beside the data

The wiki holds the targets the ticket table is missing. Putting them in the same metastore as the table keeps one credential path, one set of grants to review, and the fact next to the data it qualifies. The cost is that every wiki read is a cross-region round trip.

*Alternative considered.* A Volume in the app's own workspace, which would be local and fast. Rejected: it introduces a second storage authority and a second grant surface for the sake of latency on files measured in kilobytes.

### 4. The prompt names the prefixes; it does not carry an index

The agent is told the two wiki prefixes exist and what each means, and lists or globs on demand. No generated index of wiki contents is injected into the prompt.

This mirrors progressive skill disclosure, and it keeps prompt cost fixed as the corpora grow. It costs a round trip before the first read, which is the right trade: an index in the prompt is paid on every request, including the majority that never touch the wiki.

### 5. A write-time name guard, not a prompt instruction

`volume-backed-wiki` requires that no personal name be persisted. Enforcing it by instruction alone would leave a spec requirement with nothing behind it — the same reason Decision 2 keeps a refusing rule over the source directories rather than trusting the prompt. `VolumeBackend.write`/`edit` under `/wiki/notes/` check content against the known name set — the same set `agent_evaluation/scorers.py` already checks answers against — normalising case and surrounding whitespace, and refuse the write with an error naming the problem so the agent can rewrite in aggregate form.

Its limits should be stated plainly rather than discovered: it catches names in the known set, not names arriving from somewhere else, and not a name the agent has paraphrased. It is a backstop on a known corpus, which is exactly the situation `agent-evaluation` already relies on for the same reason. The eval keeps an item that writes a note after a person-shaped query, so the guard is measured and not merely present.

### 6. A committed seed corpus

`wiki_seed/` holds the documents, and `scripts/seed_wiki.py` uploads them. Without this, the four flipped eval items cannot be run by anyone who lacks access to the real OpenWiki, which is everyone teaching the course from a laptop.

The seed is authored as a conformant OKF bundle, which makes it the worked example of the format the course teaches — trainees read the seed to learn what a concept looks like before writing one.

The seed fixes the resolution targets explicitly — including the P2 Bug target the flipped items measure against — so the expected values are derivable. Per `agent-evaluation`, each flipped item records the query that computes it from the table *and* the target the seed supplies.

### 7. The eval flip keeps stable ids, and the version cannot live in the dataset name

`q-p2-target-adherence`, `q-sla-breach-count`, and `q-target-trend` change `kind` from `decline` to `value`. `q-fastest-squad` and `q-defects-per-release` **do not flip** — the wiki supplies policy, not a squad dimension, and those refusals stay correct.

**Found during implementation: stable ids and a versioned dataset name are mutually exclusive.** Langfuse item ids are unique *per project across datasets*, so seeding a second dataset with the same ids fails with a 409 on the first item, and ids stay reserved after deletion so the old ones cannot be freed. One of the two properties had to go.

Stable ids won, because they are the one that does the work: they make a run comparable to an earlier run item by item, which is the whole point of holding the dataset outside the repository. So `sdlc-agent-eval-v1` is **mutated in place**, the `-v1` in its name is a permanent misnomer, and the version moved to `EXPECTATIONS_VERSION`, the dataset description, and the run name.

The cost is real and worth stating: superseded expectations are not re-runnable. Past runs keep their recorded scores in Langfuse, so the v1 baseline stays *readable*, but once `dataset.py` changes there is no way to re-execute the old answer key. A regression against v1 has to be read from the stored run rather than reproduced.

The two target questions also had their wording changed to name their quarter — "kuartal III 2026" rather than "kuartal ini". The agent has no clock and the table runs to December 2026, so a relative quarter made the expected value depend on the date of the run. That is an ambiguity about dates, not about the capability the items exist to score.

`wiki_was_read` joins the method-scoring evaluators. It reads the trace for a read under a wiki prefix, which means the evaluators that count "statements issued against the data" must exclude wiki reads as well as planning and delegation — the same exclusion `agent-evaluation` already requires, extended to one more kind of tool call.

### 8. Notes do not outrank sources or data

Three authorities now answer questions, and they can disagree. The precedence is stated in the prompt: the table for data, the source corpora for policy, notes last and never as the basis for a figure. A note is the agent's own prior conclusion; treating it as evidence would let one bad turn harden into a fact that every later turn cites.

### 9. OKF v0.2 is the format, and conformance is cheap to hold

Each tier is an OKF bundle. Conformance needs three things: parseable YAML frontmatter on every non-reserved document, a non-empty `type` in it, and reserved meanings for `index.md` and `log.md`. Nothing else in the spec is mandatory.

**Two bundles, not one, and the reason matters.** The tiers looked like one bundle with two subdirectories until implementation, when two facts settled it the other way. `/wiki/` itself is deliberately not a route (Decision 2), so a shared bundle root would have to live at a path the agent cannot read — an unreachable `index.md` is worse than no `index.md`. And OKF cross-links are bundle-relative: the seed's `/policies/resolution-targets.md` resolves only if the tier *is* the root. §3 explicitly allows a bundle to be a subdirectory, so each tier carries its own root `index.md` and its own `okf_version`.

That is low enough to hold without tooling, which is the reason to adopt it rather than invent a local convention. The format is a directory of markdown files — `cat` reads it, `git` ships it, and the agent's existing `read_file` consumes it with no parser.

*What this replaces.* An earlier reading of "OKF" in this project took it for the Open Knowledge Foundation's Frictionless Data specifications — `datapackage.json`, Table Schema, tabular descriptors. That was the wrong standard: those describe *datasets*, and what this tier holds is *knowledge about* datasets, which is exactly the distinction OKF's motivation section draws. The earlier framing would have produced a JSON descriptor of the ticket table, which the agent can already get from `DESCRIBE TABLE`.

*Consequence for the agent.* It becomes a bundle **producer** as well as a consumer, because `/wiki/notes/` is a bundle it writes. A note written without frontmatter breaks conformance for every later reader, so the write path has to supply `type` — see Decision 10.

### 10. The agent writes conformant concepts, enforced at the write path

A durable note is a concept. It needs frontmatter with a `type`, and it should carry `generated: { by: <actor>, at: <timestamp> }` so a later reader can tell what produced it and when — OKF's actor convention (§7) gives the agent an identity of the form `<producer>/<version>`.

Relying on the prompt to remember this would be a mistake of the same kind as relying on it to refuse a destructive statement: the eval has already shown that prompt instructions about output format hold most of the time and not all of the time. So the note-writing path supplies the frontmatter rather than asking the model to, in the same spirit as the write-time name guard in Decision 5.

*Trade-off.* The agent cannot then choose an arbitrary `type`, since the path is writing it. A small fixed vocabulary for notes — an observation, an analysis — is the cost, and it is worth paying to keep the bundle conformant by construction rather than by good behaviour.

### 11. Targets carry trust state; the attested-computation type is available but not used yet

Target concepts use `sources`, `generated`, `verified`, and `stale_after`. A resolution target is a policy fact with an owner and a review date, and those four fields are exactly the questions a consumer of it has.

OKF also defines `type: Attested Computation` (§10) — a concept carrying a sanctioned way to compute a value, so a consumer can confirm the value came from the blessed computation rather than an improvisation. That is a close match for something this project already does: the evaluation dataset stores a `ground_truth_sql` beside every expected number for precisely that reason.

Not adopted in this change, deliberately. Attestation needs an executor and an attester, and the spec itself defers the runtime protocol, receipt and verdict formats, and the attester ABI to a future revision (§12). Adopting the type now would mean inventing the half the spec has not settled. The fit is recorded here because it is the obvious next use of this tier, and because the eval's `ground_truth_sql` is already the thing that would become the computation.

## Risks / Trade-offs

- **A note written without frontmatter silently breaks conformance** → the write path supplies `type` and `generated` rather than the prompt requesting them (Decision 10); a conformance check over the bundle is part of the task list.
- **Wiki content reaches the model as text and could carry instructions.** OpenWiki content is human-authored but not review-gated the way the repository is. → The source prefixes are read-only and the skills tier stays the only path by which instructions enter the prompt; the prompt states that wiki content is data to cite, not direction to follow. Decision 2 is explicit that the credential can write the source tree and only the permission rule stops it, which is what makes that rule load-bearing here.
- **Grants widen past the single-schema boundary `cross-workspace-sql` sets.** → The widening is one volume-level grant pair on one Volume in the same schema, recorded in the `cross-workspace-sql` impact rather than left implicit, and not a catalog-level or blanket privilege. It does include `WRITE VOLUME` over the source directory, which Decision 2 accepts and explains.
- **Durable storage is a longer-lived disclosure than a reply.** A name written to the Volume outlives the conversation and is readable by users who never asked. → Decision 5's guard, plus a spec requirement and an eval item; the requirement also forbids satisfying the constraint by declining to write at all.
- **Every read is a cross-region round trip.** → Reads happen only on paths the agent chooses, files are small, and Decision 4 keeps the tier out of the prompt for requests that do not need it. Effort reporting in the eval will show the cost; if it is material, Non-Goal 2 is the release valve.
- **The notes tree accumulates and nobody prunes it.** Shared, durable, agent-written text with no owner is how a knowledge base becomes wrong. → Notes are revisable and deletable by the agent, Decision 8 denies them authority, and the course itself is the audience that will see the tree grow — which is arguably the lesson.
- **The baseline stops being comparable at the moment of the flip.** → Stable ids and a version bump make the discontinuity explicit; a v2 baseline is recorded before any prompt tuning follows.
- **A trainee without the Jakarta credential gets a different agent.** → Required by spec: the tier is absent, the agent starts, and adherence questions return to being refusals. Logged at startup so the difference is visible rather than puzzling.

## Migration Plan

1. Use the existing `workshop_ai_platform.example.agent_wiki`; grant the service principal `READ VOLUME` + `WRITE VOLUME` on it, at volume scope only.
2. Seed `openwiki/` from `wiki_seed/`. `notes/` starts empty and is created on first write.
3. Deploy with the Volume path configured. Verify the startup log names both wiki prefixes and that a write to the source prefix is refused by the permission rule.
4. Run the eval at v1 expectations to confirm nothing regressed that the wiki should not have touched.
5. Flip the four items, bump the version, add `wiki_was_read`, and record the v2 baseline.

**Rollback** is unsetting the Volume configuration. The routes are not added, the agent starts without the tier, and behavior returns to what the v1 baseline describes — which is the same degradation path a missing credential takes, so it is exercised by ordinary local development rather than only in an incident.

## Open Questions

- Which document is authoritative when two concepts state the same target and disagree. Deferrable: the seed can be authored without a conflict, and the precedence rule in Decision 8 covers notes-versus-source, which is the case that arises first. OKF offers `status` and `verified` as the materials for a precedence rule when one is needed.
- Whether the notes tree eventually wants a naming convention the agent must follow. Deferrable: it changes prompt guidance, not the tier, the specs, or the task breakdown.
