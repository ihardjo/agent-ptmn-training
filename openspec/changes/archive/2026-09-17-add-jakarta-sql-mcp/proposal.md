## Why

The agent runs as a Databricks App in `dbc-93c4f1e3-5706` (ap-southeast-1, Singapore) but the workshop data lives in `workshop_ai_platform.example` in `dbc-86b2f2e8-b955` (ap-southeast-3, Jakarta) — a separate Unity Catalog metastore. The agent currently has one local tool (`get_current_time`) and cannot see that data at all.

Three constraints close off the obvious alternatives: Databricks Apps is not available in ap-southeast-3, so the agent cannot move to the data; the data may not come to rest in Singapore, so Delta Sharing the schema into the Singapore metastore is ruled out; and the target schema holds tables, which the schema-scoped managed MCP servers (UC Functions, Vector Search) do not expose. The remaining route is the workspace-scoped managed **SQL MCP server** on the Jakarta host, which has been verified live and serverless there.

## What Changes

- Add a second `DatabricksMCPServer` pointed at `https://dbc-86b2f2e8-b955.cloud.databricks.com/api/2.0/mcp/sql`, backed by a `WorkspaceClient` explicitly configured for the Jakarta workspace rather than the app's ambient Singapore credentials.
- Enable the MCP tool path in `agent.py`, which is currently commented out — the agent gains `execute_sql`, `execute_sql_read_only`, and `poll_sql_result`.
- Grant the agent **read and write** access to `workshop_ai_platform.example`. `execute_sql` permits `INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE`, and `ALTER TABLE`; this is intended, so participants' agents can materialise results in Jakarta rather than carrying rows back to Singapore.
- Introduce a dedicated account-level service principal for Jakarta access, with its OAuth M2M credentials stored in the existing `agent-ptmn-training` Databricks secret scope and declared as app resources in `databricks.yml`, following the pattern already established by `langfuse-secret`.
- Add agent instructions covering Unity Catalog three-level naming and backtick escaping — every column in the target table contains spaces or parentheses (`No Tiket`, `Waktu Selesai (jam)`), so unescaped SQL will fail.

## Capabilities

### New Capabilities

- `cross-workspace-sql`: The agent queries and writes Unity Catalog tables in a remote Databricks workspace through the managed SQL MCP server, authenticating as a dedicated service principal whose Unity Catalog grants are the sole scope boundary.

### Modified Capabilities

None. `langfuse-tracing` continues to apply unchanged — traces will now carry SQL and result rows, but no requirement in that spec changes.

## Impact

**Code**
- `agent_server/tools.py` — a second MCP server entry and a Jakarta-scoped `WorkspaceClient` factory
- `agent_server/agent.py` — uncomment and wire the MCP tool path, add system instructions
- `agent_server/utils.py` — `get_databricks_host_from_env()` stays for the local `system/ai` server; the Jakarta host is explicit, not derived

**Configuration**
- `databricks.yml` / `app.yaml` — two new secret-backed env vars and two new app resource declarations
- `.env.example` — the same vars for local development

**External state (not in this repo)**
- A new account-level service principal in account `e30d235c-1395-4c7d-ab08-11581920fac8`, granted into the Jakarta workspace
- Unity Catalog grants on `workshop_ai_platform.example` in the Jakarta metastore
- Two new keys in the `agent-ptmn-training` secret scope

**Risk**
- The SQL MCP server is workspace-scoped, not schema-scoped: nothing in the URL limits it. The service principal's grants are the entire security boundary, and they now include write. A grant applied at the catalog level instead of the schema level would silently extend write access to every schema in `workshop_ai_platform`.
- Per-user authorization is foreclosed for this tool. A Singapore user token is not valid in Jakarta, so all queries run as the shared service principal and Unity Catalog audit logs cannot attribute a write to an individual.
- Recovery from a destructive statement depends on Delta time travel, which is time-boxed by `VACUUM` retention.
