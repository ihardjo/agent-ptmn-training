## MODIFIED Requirements

### Requirement: The filesystem is tiered by path prefix

The agent SHALL access files through a single filesystem interface whose path prefix determines which tier serves the request. Each tier SHALL have a distinct lifetime, and the prefix SHALL be sufficient to determine that lifetime without inspecting the file.

The prefix SHALL also be sufficient to determine **whether the agent may write to it**, without inspecting the file and without knowing which storage backs the tier: a single durable store may serve several prefixes, and a grant over that store says nothing about any one of them.

Authorship SHALL NOT be inferred from the prefix. A tier may deliberately hold both authored and agent-generated documents — a knowledge base divided by author is two knowledge bases — and where it does, the document itself SHALL declare its author. The prefix answers *may I write here*; the document answers *who wrote this*.

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

#### Scenario: A prefix states writability

- **WHEN** the agent encounters a path under any configured prefix
- **THEN** the prefix SHALL determine whether a write there is permitted
- **AND** that determination SHALL NOT require reading the file or knowing which storage backs the tier

#### Scenario: One prefix may carry both provenances

- **WHEN** a prefix holds both authored documents and documents the agent wrote
- **THEN** each document SHALL declare its own author
- **AND** a reader SHALL NOT have to infer authorship from the path it was read from

#### Scenario: A read-only prefix is enforced by rule, not by grant

- **WHEN** a durable store serves both a writable prefix and a read-only one
- **THEN** the refusal on the read-only prefix SHALL come from a permission rule
- **AND** it SHALL hold even though the storage grant permits the write
