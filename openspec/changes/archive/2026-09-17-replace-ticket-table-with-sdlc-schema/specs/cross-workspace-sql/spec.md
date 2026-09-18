## MODIFIED Requirements

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
