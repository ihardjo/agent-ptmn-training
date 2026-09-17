## 1. Provision the Jakarta identity

- [x] 1.1 Create a dedicated account-level service principal for this agent in account `e30d235c-1395-4c7d-ab08-11581920fac8` and verify it appears in `databricks account service-principals list`
- [x] 1.2 Grant the service principal access to the Jakarta workspace `dbc-86b2f2e8-b955` and verify it is listed by `databricks service-principals list --profile jakarta-workshop`
- [x] 1.3 Generate an OAuth M2M client id and secret for the service principal and verify the credentials authenticate by running `databricks current-user me` against the Jakarta host with them

## 2. Apply and verify Unity Catalog grants

- [x] 2.1 Grant `USE CATALOG` on `workshop_ai_platform` and `USE SCHEMA, SELECT, MODIFY, CREATE TABLE` on `workshop_ai_platform.example` to the service principal, per design Decision 4
- [x] 2.2 Verify the grant boundary with `SHOW GRANTS TO <sp>` — confirm no privilege beyond `USE CATALOG` is held at the catalog level, and that no other catalog or schema appears
- [x] 2.3 Verify negative scope: as the service principal, confirm `SHOW SCHEMAS IN workshop_ai_platform` does not expose readable objects outside `example`, and that a `SELECT` against `workshop_ai_platform.default` is rejected

## 3. Store credentials and declare them to the app

- [x] 3.1 Put the client id and secret into the `agent-ptmn-training` secret scope and verify both keys appear in `databricks secrets list-secrets agent-ptmn-training --profile dbc-93c4f1e3-5706`
- [x] 3.2 Declare both secrets as app resources in `databricks.yml` alongside the existing `langfuse-secret` entry, and add the matching env vars to the app config in both `databricks.yml` and `app.yaml`; verify with `databricks bundle validate --profile dbc-93c4f1e3-5706`
- [x] 3.3 Add the same variables plus the Jakarta host to `.env.example`, and set real values in local `.env`; verify `.env` is still untracked with `git ls-files --error-unmatch .env`

## 4. Wire the remote MCP server

- [x] 4.1 Add a Jakarta-scoped `WorkspaceClient` factory in `agent_server/tools.py` that reads the host and OAuth credentials from environment, returning `None` when unset; verify it builds a client whose `config.host` is the Jakarta host and not the ambient Singapore one
- [x] 4.2 Add a second `DatabricksMCPServer` for `{jakarta_host}/api/2.0/mcp/sql` to `init_mcp_client`, passing the Jakarta client and `handle_tool_error=True` per design Decision 8, leaving the existing `system-ai` server and its ambient auth untouched
- [x] 4.3 Skip the Jakarta server when its credentials are absent, and verify `init_mcp_client` still returns a usable client with only the local server configured

## 5. Enable tools on the agent

- [x] 5.1 Uncomment and wire the MCP tool path in `agent_server/agent.py`, keeping the `try`/`except` fallback and making the warning name the server that failed; verify the agent still starts with Jakarta unreachable and serves a request using `get_current_time`
- [x] 5.2 Cache the resolved MCP tool list at process level per design Decision 7, so the cross-region `initialize` + `tools/list` round trip happens once rather than on every `init_agent()` call; verify by logging discovery and confirming it appears once across several requests
- [x] 5.3 Add agent instructions covering three-level Unity Catalog naming and backtick escaping for identifiers containing spaces or parentheses, naming the target schema; verify the model emits backticks for `No Tiket` and `Waktu Selesai (jam)`

## 6. Verify behavior locally

- [x] 6.1 Start the server with `uv run start-app` and confirm `execute_sql`, `execute_sql_read_only`, and `poll_sql_result` are present on the agent
- [x] 6.2 Ask a question answerable from `data_tiket_it` and verify the agent returns a grounded answer — covers the reading and discovery scenarios in the spec
- [x] 6.3 Ask the agent to create a derived table in `workshop_ai_platform.example` and verify it exists in Jakarta and that the agent reported a summary rather than the full result set — covers the remote materialisation scenario
- [x] 6.4 Ask the agent to write to a schema outside its grants and verify the statement is rejected by Unity Catalog and the failure is surfaced in the response, not swallowed — covers the out-of-scope write scenario
- [x] 6.5 Verify a Langfuse trace is produced carrying the session id and the SQL text, since it is the only per-user attribution record for writes

## 7. Deploy

- [x] 7.1 Deploy to the Databricks App, using `databricks apps deploy` from the synced bundle path if `databricks bundle deploy` still panics on CLI v1.16.0, and verify the app reaches `RUNNING`
- [x] 7.2 Run the deployed agent against `data_tiket_it` over `/invocations` and verify it answers from live Jakarta data
- [x] 7.3 Confirm no durable copy of remote data exists in the Singapore workspace — no new tables, no cached extracts — per the residency requirement in the spec
- [x] 7.4 Record the rollback lever in the change: re-comment the MCP path and redeploy for a behavior revert, or revoke the service principal's grants for an immediate access cut with no deploy
