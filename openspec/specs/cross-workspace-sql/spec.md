# cross-workspace-sql Specification

## Purpose
Lets the agent read and write Unity Catalog tables that live in a different Databricks workspace and region from the one hosting the agent, using the managed SQL MCP server, with a dedicated service principal's Unity Catalog grants as the only scope boundary.

## Requirements

### Requirement: Agent queries tables in the remote workspace

The agent SHALL expose the managed SQL MCP server hosted by the remote Databricks workspace as tools, so that it can answer questions about tables in `workshop_ai_platform.example` without those tables existing in the agent's own metastore.

#### Scenario: Reading a table the agent has no local copy of

- **WHEN** a user asks the agent a question answerable from `workshop_ai_platform.example.sdlc_tickets`
- **THEN** the agent issues SQL against the remote workspace's SQL MCP server
- **AND** the SQL executes on remote-region compute
- **AND** the agent answers from the returned rows

#### Scenario: Discovering the available data

- **WHEN** the agent needs to learn what tables or columns exist before querying
- **THEN** it SHALL be able to run `SHOW SCHEMAS`, `SHOW TABLES`, and `DESCRIBE TABLE` through the same tools
- **AND** the results reflect the remote metastore, not the agent's local one

#### Scenario: A query that exceeds the synchronous window

- **WHEN** a query does not complete within the MCP call's synchronous window and a statement identifier is returned instead of rows
- **THEN** the agent SHALL poll for completion using that identifier
- **AND** report the final result or the failure once the statement settles

### Requirement: Agent writes to the remote schema

The agent SHALL be able to execute data-modifying and table-creating statements against the remote schema, so that results can be materialised in the remote region rather than transferred back to the agent's region.

#### Scenario: Materialising a result set remotely

- **WHEN** the agent is asked to persist a derived result
- **THEN** it SHALL create or populate a table in the remote schema
- **AND** report only a summary of the operation rather than the full result set

#### Scenario: A write outside the granted scope

- **WHEN** the agent attempts to modify an object outside the schema it has been granted write access to
- **THEN** the statement SHALL fail on the remote workspace's authorization check
- **AND** the agent SHALL surface the failure rather than silently continuing

### Requirement: Remote access uses a dedicated identity, not the caller's

All statements issued to the remote workspace SHALL execute as a dedicated service principal provisioned for this purpose, whose credentials are supplied from secret storage and never appear in source or in the repository.

#### Scenario: Credentials are absent or invalid

- **WHEN** the remote credentials are not configured, or the remote workspace rejects them
- **THEN** the agent SHALL start and serve requests using its remaining tools
- **AND** report that remote SQL is unavailable rather than failing to start

#### Scenario: Two identities in one process

- **WHEN** the agent uses both its own workspace's tools and the remote workspace's tools in a single request
- **THEN** each SHALL authenticate against its own workspace
- **AND** neither set of credentials SHALL be used against the other workspace

#### Scenario: Requests from different end users

- **WHEN** two different end users invoke the agent
- **THEN** both users' statements SHALL execute as the same service principal with identical permissions
- **AND** remote audit records SHALL attribute the statements to that service principal

### Requirement: Scope is enforced by grants, not by configuration

Because the SQL MCP server is workspace-scoped and accepts arbitrary statements, the service principal's Unity Catalog grants SHALL be the enforcement boundary. Those grants SHALL be confined to the single target schema and SHALL NOT be applied at the catalog level or as blanket privileges.

#### Scenario: Reading outside the granted schema

- **WHEN** the agent issues a `SELECT` against a schema it was not granted
- **THEN** the remote workspace SHALL reject the statement
- **AND** no rows from that schema SHALL reach the agent

#### Scenario: Grants are audited against the boundary

- **WHEN** the service principal's effective privileges are reviewed
- **THEN** its write privileges SHALL resolve to the target schema only
- **AND** no privilege SHALL be held at the catalog level beyond what is required to traverse to that schema

### Requirement: Generated SQL is valid against the remote catalog

The agent SHALL be instructed such that the SQL it generates resolves correctly in the remote catalog, including fully qualified three-level names and escaping for identifiers that are not bare words. Because only a minority of the target table's columns require escaping, the agent SHALL determine which identifiers need it from the schema rather than escaping every identifier by default or assuming none needs it.

#### Scenario: Columns whose names contain spaces or punctuation

- **WHEN** the agent queries a column whose name contains a space, parentheses, or a slash
- **THEN** the generated SQL SHALL escape that identifier
- **AND** the statement SHALL succeed rather than failing to parse

#### Scenario: Columns that need no escaping

- **WHEN** the agent queries a column whose name is a bare word
- **THEN** the statement SHALL succeed whether or not that identifier is escaped
- **AND** the agent SHALL NOT report the column as unavailable on the grounds of its name

#### Scenario: A table mixing both kinds of identifier

- **WHEN** a single statement references both a bare-word column and a column requiring escaping
- **THEN** the agent SHALL escape only what requires it
- **AND** the statement SHALL parse and execute

#### Scenario: An unqualified table reference

- **WHEN** the agent refers to a table without its catalog and schema
- **THEN** the agent SHALL qualify it before execution, or recover from the resulting resolution error by requalifying and retrying

### Requirement: Remote data is not persisted in the agent's region

Data read from the remote workspace SHALL be held only for the duration of request processing. The system SHALL NOT create a durable copy of remote tables in the agent's own metastore or on the agent's local storage.

#### Scenario: Handling a result set

- **WHEN** the agent receives rows from the remote workspace
- **THEN** those rows SHALL exist only in request-scoped memory and in the trace record
- **AND** no table, file, or cache in the agent's own region SHALL retain them after the request completes
