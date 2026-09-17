## Context

See `proposal.md` — Why, for motivation. The design-relevant facts, all verified against the live workspaces:

| | Agent workspace | Data workspace |
|---|---|---|
| Host | `dbc-93c4f1e3-5706` | `dbc-86b2f2e8-b955` |
| Region | ap-southeast-1 (Singapore) | ap-southeast-3 (Jakarta) |
| Metastore | `metastore_aws_ap_southeast_1` | `pertamina-metastore-ap-southeast-3-aws` |
| Account | `e30d235c-1395-4c7d-ab08-11581920fac8` | same account |

- `/api/2.0/mcp/sql` answers on the Jakarta host and exposes `execute_sql`, `execute_sql_read_only`, `poll_sql_result`. It runs on serverless SQL — no warehouse needs configuring, and none is referenced in the tool's input schema.
- The target is a single Delta table, `workshop_ai_platform.example.data_tiket_it`. Every one of its seven columns needs escaping: `No Tiket`, `Tanggal`, `Pemohon`, `Kategori`, `Prioritas`, `Status`, `Waktu Selesai (jam)`.
- `agent_server/tools.py` already builds a `DatabricksMultiServerMCPClient`; `DatabricksMCPServer` accepts a per-server `workspace_client`, so two servers can authenticate against two workspaces in one client.
- `agent_server/agent.py` has the MCP tool path written but commented out, including a `try`/`except` that continues without MCP tools on failure.
- `routes.py:85` and `routes.py:119` both call `init_agent()` **per request**.

## Goals / Non-Goals

**Goals:**
- One additional MCP server entry reaching Jakarta, without disturbing the existing local `system/ai` server or its ambient authentication.
- Remote credentials resolved from secret storage, with the same declaration pattern `langfuse-secret` already uses.
- Cross-region latency paid once per process, not once per request.
- A failure to reach Jakarta degrades the agent rather than breaking it.

**Non-Goals:**
- Per-user authorization for remote queries. Foreclosed by the architecture, not deferred — see Decision 3.
- Any client-side restriction of which SQL the model may write. Enforcement is in Unity Catalog grants; see Decision 4.
- Genie spaces, UC functions, or vector indexes in the Jakarta workspace.
- Changing the LLM endpoint. `databricks-gpt-oss-120b` stays Singapore-served; the at-rest-only residency reading permits it.

## Decisions

### 1. Managed SQL MCP, not Genie or UC functions

The schema holds tables, and the schema-scoped MCP servers do not expose tables — `/api/2.0/mcp/functions/{catalog}/{schema}` serves UC functions and `/api/2.0/mcp/vector-search/{catalog}/{schema}` serves indexes. Pointing either at `workshop_ai_platform/example` yields zero tools.

*Alternatives considered.* A Genie space over the table would give curated natural-language access with bounded result shapes, but requires building and tuning the space before anything works, and Genie's SQL is non-deterministic. SQL UDFs wrapping fixed queries would be deterministic and would fix the projection, but demand that every question shape be anticipated — wrong for a workshop. The SQL MCP server needs no preparation at all and, given write access, subsumes both: the agent can create its own UDFs or tables if it needs them.

### 2. Query across the region boundary rather than replicating the data

Delta Sharing into the Singapore metastore would be the conventional answer and is already an established pattern in this account — provider `pertamina-sandbox-data-and-ai` exists. It is ruled out: a shared catalog is data at rest in Singapore. Moving the agent to Jakarta is ruled out separately, as Databricks Apps is unavailable in ap-southeast-3. Querying across the boundary leaves the only durable copy in Jakarta; rows exist in Singapore solely in request-scoped memory and in the Langfuse trace, which is itself Jakarta-hosted (`agentmonitoring.pertamina.ai` resolves into AWS Jakarta ranges).

### 3. A dedicated service principal with explicit OAuth M2M credentials

The app's ambient `WorkspaceClient()` authenticates to Singapore only; a Singapore token has no standing in the Jakarta workspace. Because both workspaces sit in one account, an account-level service principal can be granted into Jakarta and used from Singapore with a client id and secret.

It must be **purpose-built for this agent**, not the app's existing service principal and not one shared with other workloads — its grants are the whole security boundary (Decision 4), so anything else it can reach, the agent can reach.

**Verified during implementation — `auth_type` must be pinned.** Constructing `WorkspaceClient(host=..., client_id=..., client_secret=...)` is not sufficient. The SDK still walks its credential chain and prefers ambient Databricks auth, resolving `auth_type` to `databricks-cli` and sending a *Singapore* token to the Jakarta host, which returns `400 Invalid Token`:

```
  without auth_type   -> auth_type: databricks-cli   -> 400 Invalid Token
  auth_type="oauth-m2m" -> auth_type: oauth-m2m      -> 200, whoami = the SP
```

This is precisely the cross-contamination the spec forbids ("neither set of credentials SHALL be used against the other workspace"), and it fails closed but confusingly — the symptom looks like a bad secret. `auth_type="oauth-m2m"` is therefore load-bearing, not decoration.

The consequence is that end-user identity is lost at the boundary: all statements execute as this one principal, Unity Catalog audit attributes every write to it, and per-user authorization becomes impossible for this tool. `init_agent()` is already called without a user client, so nothing regresses today — but this makes that choice permanent for remote SQL. The compensating record is the Langfuse trace, which already carries `langfuse_session_id` (`routes.py:46`) and now also carries the SQL text.

### 4. Scope lives in the grants, because it cannot live in the URL

Every other managed MCP server pins its scope in the path. `/api/2.0/mcp/sql` does not — it accepts arbitrary statements and resolves them against whatever the calling identity can see. Verified: `SHOW CATALOGS` on the Singapore host returned nine catalogs, including some the catalogs API did not list.

So the grant set is the enforcement mechanism, and it must be tight and schema-level:

```
  GRANT USE CATALOG ON CATALOG workshop_ai_platform TO <sp>
  GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE
        ON SCHEMA workshop_ai_platform.example    TO <sp>
```

`MODIFY` or `ALL PRIVILEGES` granted at the catalog level instead would silently extend write to every schema under it, including `default`. Nothing else should be granted anywhere.

### 5. Both SQL tools are exposed, and write access is intentional

`execute_sql` permits `INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE`, `ALTER TABLE`, and `DROP`. This is the requested behavior, and it earns its place: it lets the agent `CREATE TABLE ... AS SELECT` in Jakarta and return a row count instead of dragging a large result set to Singapore — bulk data stays in-region and out of the model's context.

`execute_sql_read_only` is left exposed alongside it rather than filtered out, so the model can select the narrower tool for reads. That is a hint, not a control: filtering tools client-side would not be a security boundary either, since the model's tool choice is not a trust boundary. The only real guard is Decision 4.

*Accepted consequence.* A destructive statement is recoverable only through Delta time travel (`DESCRIBE HISTORY`, `RESTORE TABLE ... VERSION AS OF`), bounded by `VACUUM` retention — seven days by default.

### 6. The Jakarta host is explicit; the local server keeps deriving its own

`get_databricks_host_from_env()` (`utils.py:25`) returns `WorkspaceClient().config.host`, which is Singapore. It stays as-is for the `system/ai` server. The Jakarta server takes its host from configuration instead, so the two never collapse onto one workspace if the ambient environment shifts.

### 7. Tool discovery is cached per process, not per request

Both routes call `init_agent()` on every request. Fetching MCP tools there would add an `initialize` plus `tools/list` round trip to Jakarta — across regions — to every single request, before any work begins. The tool list is static, so it should be resolved once per process and reused. This is the one place where the obvious implementation carries a real latency cost.

### 8. Tool errors are returned to the model, not raised

`DatabricksMCPServer` accepts `handle_tool_error`. Returning the error as a string lets the model correct a malformed identifier or an unqualified name and retry, which matters given the escaping burden in Decision 9. Raising instead surfaces as a stream error and ends the turn.

**Verified during implementation — a failed statement is not an MCP error.** Both a missing table and a permission denial come back with MCP `isError: false`; the failure lives inside the payload as `status.state == "FAILED"` with the message under `status.error`:

```
  CREATE TABLE workshop_ai_platform.default.blocked_probe (x INT)
    mcp isError    : False
    statement state: FAILED
    error          : [INSUFFICIENT_PERMISSIONS] User does not have
                     USE SCHEMA on Schema 'workshop_ai_platform.default'
```

So `handle_tool_error` never fires for SQL failures — it only covers transport-level problems. The error text does reach the model in the tool output, so recovery is still possible, but the agent's instructions must tell it to check `status.state` rather than treat any returned payload as success. Decision 9's instructions carry that.

### 9. Escaping is handled by instruction, not by a SQL layer

Every column in the target table contains a space or parentheses, so unescaped SQL fails to parse — the failure mode is immediate and total. The agent's instructions must cover three-level qualification and backtick escaping. Interposing a query-rewriting layer was considered and rejected: it would have to parse SQL to be correct, and Decision 8 already gives the model a recovery path from the parse error.

## Risks / Trade-offs

- **The agent can reach anything the service principal can** → a dedicated principal, grants confined to one schema, nothing at catalog level beyond `USE CATALOG`. Verify with `SHOW GRANTS` after provisioning rather than assuming the grant statements were sufficient.
- **A destructive write is attributed to the service principal, not a person** → Langfuse traces carry the session id and the SQL text; treat them as the attribution record. Accepted, not mitigated away.
- **Free-form SQL can pull far more across the boundary than a curated tool would** → the CTAS pattern in Decision 5 is the escape hatch, and result sets are truncated by the statement API. At-rest-only residency means volume is a cost and latency concern here, not a compliance one.
- **Remote credentials in a second secret scope entry** → same storage and declaration path as `langfuse-secret`, which is already proven in this app. No new mechanism.
- **Jakarta unreachable, or credentials rotated out from under the app** → the `try`/`except` in the commented MCP block already degrades to the remaining tools; keep it, and make the log message name the remote server so the failure is diagnosable.
- **Cross-region round trips on every query** → unavoidable for the query itself; Decision 7 removes the avoidable per-request discovery cost.
- **Concurrent writes from multiple workshop participants under one principal** → see Open Questions.

## Migration Plan

1. Provision the service principal and its OAuth secret in the account; grant it into the Jakarta workspace.
2. Apply the Unity Catalog grants from Decision 4; confirm with `SHOW GRANTS`.
3. Store the client id and secret in the `agent-ptmn-training` secret scope; declare both as app resources in `databricks.yml`.
4. Wire the second MCP server and enable the MCP tool path; verify locally against Jakarta before deploying.
5. Deploy and confirm the agent answers a question over `data_tiket_it` end to end.

**Rollback.** Three levers, fastest first. As provisioned, the service principal is `agent-ptmn-training-jakarta-sql`, application id `bacd540f-d444-4aa1-880f-aa33ebc42825`.

1. **Revoke grants** — immediate, no deploy. Removes `MODIFY` / `CREATE TABLE` (or all privileges) from the service principal on `workshop_ai_platform.example`. Use this if the concern is access. Tools stay loaded but every statement fails closed.
2. **Unset the credentials** — remove `DATABRICKS_JAKARTA_CLIENT_ID` / `DATABRICKS_JAKARTA_CLIENT_SECRET` from the app config and redeploy. `jakarta_workspace_client()` returns `None`, the server is skipped, and the agent serves its remaining tools. Use this to drop the tools without touching Unity Catalog.
3. **Revert the code** — restore the previous `agent.py` / `tools.py` and redeploy for full removal.

Nothing in the data path is destructive to reverse. Tables the agent created in `example` persist through all three and must be dropped by hand if unwanted.

**Deployment note.** `databricks bundle deploy` currently panics on CLI v1.16.0 in `ResourceApp.OverrideChangeDesc` while planning the app resource. File sync completes first, so `databricks apps deploy` from the synced bundle path is the working route until the CLI is upgraded.

## Open Questions

- **Should `VACUUM` retention on `example` be lengthened for the duration of the workshop?** Seven days is the default recovery window for a destructive statement. Purely operational.

**Resolved.** Writes land directly in `workshop_ai_platform.example`, as in Decision 4 — no scratch schema. Accepted consequence: with several participants driving agents concurrently under one service principal, they will collide on table names and can overwrite each other's work, and `data_tiket_it` itself is writable rather than protected. Revisit if the workshop runs with more than a handful of concurrent users.
