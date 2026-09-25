## Why

The agent can only answer from `workshop_ai_platform.example.sdlc_tickets`, and that table deliberately holds no resolution target, no threshold, and no breach indicator — `sdlc-ticket-dataset` maintains those absences as a contract. So every adherence question currently has the same correct answer: *I cannot tell you.* Four items in the evaluation dataset expect exactly that refusal, with a note against them that they flip once a wiki supplies the target.

Pertamina already holds those policy facts in its internal **OpenWiki**, which is not a Unity Catalog table and so cannot be reached by the SQL tools. Landing that content on a Unity Catalog Volume and mounting it as a `/wiki/` tier gives the agent the half of the answer the table cannot carry — the target to measure against — and closes the loop the dataset was built around.

It also supplies the course's demonstration of durable agent memory. `migrate-to-deep-agent` established the filesystem abstraction and left the tier unbuilt, naming this change as its successor; `agent.py:89` still carries the comment saying so.

## What Changes

- Add a **`/wiki/` tier** backed by a Unity Catalog Volume in the Jakarta workspace, routed through the existing `CompositeBackend` by path prefix, like `/skills/` before it.
- Implement a **`VolumeBackend`** against the `BackendProtocol` using the Databricks **Files API**. Databricks Apps have no FUSE mount for Volumes, so `FilesystemBackend` cannot be pointed at one — the tier is served by `files.upload` / `files.download` / `files.list_directory_contents` / `files.delete` over the Jakarta workspace client.
- **Represent the whole tier as an OKF v0.2 knowledge bundle** — [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md), a directory of markdown concepts with YAML frontmatter. OKF is the *format*, not a second source system: conformance requires that every non-reserved `.md` file carry parseable frontmatter with a non-empty `type`, and that `index.md` and `log.md` follow §8 and §9 when present.
- **Subdivide the tier by provenance**, as two top-level directories of one Volume, so the prefix still answers *who wrote this*:
  - `/wiki/openwiki/` — synced from the internal system, **read-only** to the agent
  - `/wiki/notes/` — **agent-written**, durable, shared across users and sessions
  Both are part of the same bundle and both must be conformant; the agent is a producer as well as a consumer.
- **Carry the policy facts with their trust state.** A resolution target is exactly the kind of fact that needs "who confirmed this, and is it still true" — so target concepts use OKF's provenance and lifecycle families (`sources`, `generated`, `verified`, `stale_after`) rather than being bare prose. The agent cites the concept it read, and a stale or unverified target is visible as such instead of being indistinguishable from a fresh one.
- **Retrieve and update.** The agent reads policy facts from the synced corpora and writes what it learns back to the same store under `/wiki/notes/`, where it survives the thread and is visible to the next request.
- Constrain what may be written: the privacy rule that governs the agent's *answers* SHALL also govern its *wiki writes*. A durable file is a longer-lived disclosure than a chat reply, not a shorter one.
- Flip the four resolution-target evaluation items from `decline` to `value`, keeping their ids, and bump the dataset version — the mechanism `agent-evaluation` already prescribes for a capability that makes a question answerable.
- Build the `wiki_was_read` evaluator that `add-langfuse-eval-dataset` deferred for want of a wiki.

## Capabilities

### New Capabilities
- `volume-backed-wiki`: A durable knowledge tier on a Unity Catalog Volume, written as an OKF bundle — how OpenWiki content is reached, how policy facts carry their trust state, how the agent writes durable conformant notes back, what provenance each path prefix carries, what may not be written there, and how the tier degrades when the Volume is unreachable.

### Modified Capabilities
- `deep-agent-loop`: The tiering requirement currently makes a path prefix sufficient to determine a file's **lifetime**. That is no longer enough. The Volume was to hold only agent-written content — the rule being *repository means a person wrote it, Volume means the agent did* — but OpenWiki content arrives on the Volume as human-authored material, so provenance and writability must be determined by the prefix too, not inferred from the tier.

## Impact

- **`agent_server/backends.py`** (new) — `VolumeBackend` over the Files API.
- **`agent_server/agent.py`** — two more routes in `build_backend()`; deny-write permissions extended to the synced subtree.
- **`agent_server/prompts/system_prompt.md`** — the agent must be told the tier exists, what each prefix means, and that a target now has a source. Lands in the slots `restructure-system-prompt-slots` defines, so that change should precede this one.
- **`agent_evaluation/dataset.py`, `scorers.py`** — four items flip; `wiki_was_read` is added.
- **`databricks.yml`, `app.yaml`, `.env.example`** — the Volume path as configuration (`DATABRICKS_WIKI_VOLUME`, a path and not a secret).
- **Grants** — the Jakarta service principal gains `READ VOLUME` + `WRITE VOLUME` on `workshop_ai_platform.example.agent_wiki`. Audited against the `cross-workspace-sql` boundary and **within** it: the privileges are volume-scoped, the volume sits inside the one target schema, and nothing was added at schema or catalog level (the service principal's catalog grant remains `USE_CATALOG` alone, which that spec already allows for traversal). So this widens what the identity can reach without moving the boundary.
  What it does *not* buy: because a volume grant is per-volume and not per-path, `WRITE VOLUME` covers the read-only source directory too. The `FilesystemPermission` deny rule is the only thing refusing that write — see design.md, Decision 2.
- **Two pre-existing bugs fixed in passing**, because task 8.3 requires `uv run preflight` to pass and it could not:
  - `agent_server/start_server.py` hard-coded `port=8000` and ignored the `--port` argument `scripts/preflight.py` passes it, so preflight always probed a port nothing was listening on. The default stays 8000, which is what Databricks Apps expects.
  - `scripts/preflight.py` asserted `/health` returns `{"status": "healthy"}`, but the route returns `{"status": "ok"}` — which is what `chat-completions-serving` specifies. The check asserted a value nothing produced.
  Neither is related to the wiki; both are recorded here because they are in this change's diff and belong to `chat-completions-serving`, not to `volume-backed-wiki`.
- **Out of scope** — how OpenWiki content gets *onto* the Volume. This change consumes a Volume whose population is an upstream concern; see design.md.
