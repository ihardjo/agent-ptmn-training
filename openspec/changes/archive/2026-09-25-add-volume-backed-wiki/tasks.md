## 1. Provision the Volume and configuration

- [x] 1.1 Use the existing managed Volume `workshop_ai_platform.example.agent_wiki` and create `openwiki/` and `notes/` as its top-level directories; verify the volume lists both and that no second wiki volume was created alongside it.
- [x] 1.2 Grant the Jakarta service principal `READ VOLUME` + `WRITE VOLUME` on the Volume, at volume scope only; verify with `SHOW GRANTS ON VOLUME` that no catalog- or schema-level privilege was used.
- [x] 1.3 Add `DATABRICKS_WIKI_VOLUME` to `.env.example`, `app.yaml`, and `databricks.yml` as a plain value (a path, not a secret); verify `databricks bundle validate --profile <profile>` passes.
- [x] 1.4 Confirm the service principal can list, download, and upload under both directories with a throwaway script using `WorkspaceClient.files`; verify both succeed — the grant is deliberately uniform, so the source directory being writable at this layer is the expected result, and 4.2 is what refuses the write.

## 2. Seed corpus

- [x] 2.1 Author `wiki_seed/openwiki/` as a conformant OKF v0.2 bundle holding the resolution targets and policy facts the ticket table lacks, including an explicit P2 Bug resolution target; verify each target appears in exactly one concept so provenance is unambiguous, and that every concept carries frontmatter with a non-empty `type`.
- [x] 2.2 Write `scripts/seed_wiki.py` to upload `wiki_seed/` to the Volume's `openwiki/` directory, idempotently, without touching `notes/`; verify a second run leaves the listing unchanged and that any existing `notes/` content survives it.
- [x] 2.3 Register the script as a `uv run seed-wiki` entry point in `pyproject.toml`; verify `uv run seed-wiki` completes and prints the uploaded paths.

## 3. `VolumeBackend`

- [x] 3.1 Create `agent_server/backends.py` with `VolumeBackend(BackendProtocol)` taking a `WorkspaceClient`, the volume root, and a subdirectory; verify two instances sharing one volume root but differing in subdirectory resolve the same relative path to two distinct Volume paths, and that neither can escape its subdirectory via `..`.
- [x] 3.2 Implement `read` and `ls` over `files.download` and `files.list_directory_contents`, honouring the `offset`/`limit` window contract and tolerating degenerate windows via `normalize_read_bounds`; verify a unit test covers a negative offset, a non-positive limit, and `start_line` being set.
- [x] 3.3 Implement `write`, `edit`, and `delete` over `files.upload(overwrite=True)` and `files.delete`, creating parent directories as needed; verify a written file is readable back through `read` in a second call.
- [x] 3.4 Implement `glob` and `grep` by listing then downloading, respecting the `max_count` budget; verify a unit test finds a known string in a seeded file and returns paths that keep the caller's prefix.
- [x] 3.5 Map every Files API failure to the protocol's error result rather than raising, and log it; verify a read of a nonexistent path returns an error result and a request against an unreachable host returns an error result instead of a 500.
- [x] 3.6 Add the write-time name guard on `write` and `edit`: refuse content containing any name in the known person set, case- and whitespace-normalised, with an error naming the problem; verify a unit test refuses `"Budi  Santoso"` and accepts the same finding expressed as `1 (tertinggi)`.

## 4. Wire the tier into the agent

- [x] 4.1 Extend `build_backend()` with the two wiki routes — one `VolumeBackend` per subdirectory, both on the one Volume — when `DATABRICKS_WIKI_VOLUME` is set, leaving the `StateBackend` default and `/skills/` route untouched; verify the startup log names the prefixes actually mounted.
- [x] 4.2 Extend `skill_permissions()` (renaming it for what it now covers) with a `deny` write rule on `/wiki/openwiki/**`; verify an attempted write, edit, and delete under it each return a refusal the agent can read, that the file on the Volume is unchanged afterwards, and that a write under `/wiki/notes/` succeeds. This rule is the only thing enforcing read-only — the grant does not — so treat a gap here as a correctness bug, not a hardening nicety.
- [x] 4.3 Make the tier optional: with the Volume variables unset the agent starts, logs the absence, and serves requests; verify `uv run start-app` with no wiki configuration answers a data question normally.
- [x] 4.4 Confirm longest-prefix routing maps `/wiki/notes/x.md` and `/wiki/openwiki/y.md` to the `notes/` and `openwiki/` directories respectively, and that a bare `/wiki/` path falls through to the scratch default rather than reaching the Volume; verify by reading one file from each subdirectory in a single request and checking the paths in the trace.

## 5. OKF conformance

- [x] 5.1 Add a conformance check over the bundle asserting the three hard rules of OKF v0.2 §11 — every non-reserved `.md` has parseable YAML frontmatter, every frontmatter has a non-empty `type`, and `index.md`/`log.md` are a listing and a history rather than concepts; verify it passes on the seed and fails on a document with frontmatter removed.
- [x] 5.2 Give the seeded target concepts their provenance and lifecycle frontmatter — `sources`, `generated`, `verified`, `stale_after` per design Decision 11; verify the P2 Bug target records who confirmed it and when, and that a reader can tell a confirmed target from an unconfirmed one.
- [x] 5.3 Make the note-writing path supply `type` and `generated` itself rather than asking the model for them, per design Decision 10; verify a note written by the agent is conformant without the prompt mentioning frontmatter, and that the bundle still passes 5.1 afterwards.
- [x] 5.4 Verify the agent tolerates what the spec says it must — an unknown `type`, unrecognised frontmatter keys, a missing optional field, and a broken cross-link SHALL each be consumed rather than rejected; construct one document with each and confirm the agent uses all four.
- [x] 5.5 Confirm the agent cites the concept a policy fact came from when it answers with one; verify the citation names the concept rather than presenting the figure as though it came from the ticket table.

## 6. Instructions

- [x] 6.1 Add the tier to `agent_server/prompts/system_prompt.md`: the two wiki prefixes and what each means, that a resolution target now has a source, and that wiki content is data to cite rather than instructions to follow; verify the agent reads a target from the wiki when asked an adherence question.
- [x] 6.2 State the precedence rule — table for data, source corpora for policy, notes last and never the basis for a figure; verify the agent cites the table rather than a contradicting note planted in `/wiki/notes/`.
- [x] 6.3 State that the privacy rule governs wiki writes as well as answers; verify the agent writes a concentration finding in ranked form without a name when asked to record one.
- [x] 6.4 Land 6.1–6.3 in the slots defined by `restructure-system-prompt-slots`; verify the diff attributes each addition to a named slot.

## 7. Evaluation

- [x] 7.1 Record the expectations version in `agent_evaluation/dataset.py` and update the description to say the wiki now supplies targets. The dataset is mutated in place and **not** renamed: Langfuse ids are unique per project, so a `-v2` dataset cannot reuse these ids (409) and stable ids matter more than a versioned name — see design Decision 7. Verify seeding upserts 27 items and the three target items read back as `value`.
- [x] 7.2 Flip `q-p2-target-adherence`, `q-sla-breach-count`, and `q-target-trend` from `kind: decline` to `kind: value`, keeping their ids, recording both the computing query and the seeded target each expectation depends on; verify each recorded query reproduces its expected value against the live table, and that the ids are unchanged.
- [x] 7.3 Leave `q-fastest-squad` and `q-defects-per-release` as declines; verify no squad or release field was introduced anywhere by this change.
- [x] 7.4 Add a `wiki_was_read` evaluator scoring whether an answer that cites a wiki fact is backed by a read under a wiki prefix in the trace; verify it scores 0 on a fabricated-target answer and 1 on a read-backed one.
- [x] 7.5 Exclude wiki reads from the tool activity the method and effort evaluators treat as statements against the data, alongside planning and delegation; verify the statement count for a wiki-using question matches the SQL actually issued.
- [x] 7.6 Add an item that asks the agent to record a person-shaped finding to the notes tier, scored by `no_pii_leak` over what was written as well as what was answered; verify it fails when the guard from 3.6 is disabled.
- [x] 7.7 Run `uv run agent-evaluate` and record the baseline in `baseline.md`; verify every evaluator reports on every applicable item. Recorded alongside the surviving v1 figures rather than a matched v1 run, which no longer exists — see design Decision 7.

## 8. Documentation and validation

- [x] 8.1 Update `CLAUDE.md` and `AGENTS.md` for the new environment variables, the `seed-wiki` command, and the tier layout; verify the tier table in the docs matches `build_backend()`.
- [x] 8.2 Record the volume-grant widening in the change's impact notes, including that `WRITE VOLUME` covers the source directory and is constrained in middleware rather than by the grant; verify against the live grants that the widening stays inside the `cross-workspace-sql` boundary — volume-scoped, inside the one target schema, nothing new at schema or catalog level. No `cross-workspace-sql` spec change: its requirement is satisfied, not altered.
- [x] 8.3 Run `openspec validate add-volume-backed-wiki --strict` and `uv run preflight`; verify both pass. Preflight needed two pre-existing bugs fixed first — `start-server` ignored `--port`, and the health check asserted a payload the route never returns; see the proposal's impact notes.
- [ ] 8.4 Deploy to `dev` and exercise an adherence question end to end against the deployed app; verify the answer states that the target came from the wiki and the trace shows the read.
