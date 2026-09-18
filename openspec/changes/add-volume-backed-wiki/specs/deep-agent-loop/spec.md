## MODIFIED Requirements

### Requirement: The filesystem is tiered by path prefix

The agent SHALL access files through a single filesystem interface whose path prefix determines which tier serves the request. Each tier SHALL have a distinct lifetime, and the prefix SHALL be sufficient to determine that lifetime without inspecting the file.

The prefix SHALL also be sufficient to determine two further properties of a file without inspecting it: **who authored it** — a person or the agent — and **whether the agent may write to it**. Neither property SHALL be inferable from the storage a tier happens to use, because a single durable store may hold both human-authored content synced from an internal system and content the agent wrote itself. Where a tier holds both, it SHALL be subdivided so that each prefix carries one provenance and one writability.

#### Scenario: Unprefixed paths are turn-scoped scratch

- **WHEN** the agent writes to a path outside any configured tier prefix
- **THEN** the content SHALL be available for the remainder of the request
- **AND** it SHALL NOT persist after the thread ends

#### Scenario: A prefix identifies the tier serving it

- **WHEN** a file operation is issued against a configured tier prefix
- **THEN** it SHALL be served by that tier rather than by the default
- **AND** listings SHALL preserve the prefix so the tier remains identifiable in the result

#### Scenario: The most specific prefix wins

- **WHEN** a path could match more than one configured prefix
- **THEN** the longest matching prefix SHALL serve the request

#### Scenario: A prefix states provenance and writability

- **WHEN** the agent encounters a path under any configured prefix
- **THEN** the prefix SHALL determine whether that content was authored by a person or by the agent
- **AND** it SHALL determine whether a write there is permitted
- **AND** neither determination SHALL require reading the file or knowing which storage backs the tier

#### Scenario: One store carrying both provenances is subdivided

- **WHEN** a durable store holds both human-authored content synced from an internal system and content the agent wrote
- **THEN** the two SHALL occupy distinct prefixes
- **AND** no single prefix SHALL contain both
