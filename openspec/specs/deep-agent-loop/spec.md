# deep-agent-loop Specification

## Purpose

Defines how the agent plans multi-step work, delegates bounded sub-tasks, and reads and writes through a filesystem whose path prefixes carry distinct lifetimes and writability — including how repository-held skills are discovered, disclosed on demand, and protected from modification by the agent.

## Requirements

### Requirement: The agent plans multi-step work before executing it

For work requiring several dependent steps, the agent SHALL be able to record a plan and revise it as steps complete. The plan SHALL be observable after the fact, so that a reviewer can see what the agent intended as distinct from what it did.

#### Scenario: A multi-step request produces a recorded plan

- **WHEN** a user asks a question that cannot be answered by a single tool call
- **THEN** the agent SHALL record a plan of steps before or while executing them
- **AND** the plan SHALL appear in the request's trace

#### Scenario: A plan is revised as work proceeds

- **WHEN** the agent completes a planned step
- **THEN** it SHALL be able to update the plan to reflect what remains
- **AND** each revision SHALL be observable in the trace in the order it occurred

#### Scenario: A single-step request is not forced through planning

- **WHEN** a user asks a question answerable by one tool call
- **THEN** the agent SHALL NOT be required to produce a plan
- **AND** the answer SHALL be returned without additional planning turns

### Requirement: The agent delegates sub-tasks with isolated context

The agent SHALL be able to delegate a bounded sub-task to a subagent that does not inherit the full conversation context, and SHALL receive back only the sub-task's result. Delegation SHALL be observable in the trace.

#### Scenario: A delegated sub-task returns only its result

- **WHEN** the agent delegates a sub-task
- **THEN** the subagent SHALL execute with a context scoped to that sub-task
- **AND** only the sub-task's result SHALL be returned into the calling context

#### Scenario: Delegation is visible to a reviewer

- **WHEN** a request involves delegation
- **THEN** the trace SHALL show the delegation and the returned result as distinct from the calling agent's own tool calls

#### Scenario: A failing sub-task does not end the request

- **WHEN** a delegated sub-task fails
- **THEN** the calling agent SHALL receive the failure as a result it can act on
- **AND** the request SHALL continue rather than terminating

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

### Requirement: Skills are loaded from the repository

The agent SHALL discover skills from a directory held in the repository and deployed with the application. Each skill SHALL be a directory containing a definition file, and the agent SHALL be able to read a skill's full content when it judges the skill relevant.

#### Scenario: A skill in the repository is discoverable

- **WHEN** a skill directory containing a definition file is present in the skills directory
- **THEN** the agent SHALL discover it at startup
- **AND** the number of discovered skills SHALL be recorded in the application log

#### Scenario: A malformed skill does not prevent startup

- **WHEN** a directory in the skills location lacks a valid definition file
- **THEN** the agent SHALL start and serve requests
- **AND** the problem SHALL be reported in the log rather than raised to the caller

#### Scenario: No skills configured

- **WHEN** the skills directory is absent or empty
- **THEN** the agent SHALL start and serve requests using its remaining capabilities

### Requirement: Skill content is disclosed progressively

Only a skill's identifying metadata SHALL be carried in the agent's instructions at all times. A skill's full content SHALL be read only when the agent determines it is needed, so that the cost of an unused skill is bounded to its metadata.

Where more than one skill's metadata plausibly matches a request, the agent SHALL select among them rather than reading each in turn. Not reading the plainly unrelated is no longer sufficient: a menu whose descriptions overlap makes the number of bodies read a cost the agent controls, and that cost SHALL be bounded.

#### Scenario: Metadata is always present, body is not

- **WHEN** a request begins
- **THEN** each discovered skill's name and description SHALL be available to the agent
- **AND** no skill's full content SHALL have been read

#### Scenario: A relevant skill's content is read on demand

- **WHEN** the agent judges a skill relevant to the request
- **THEN** it SHALL read that skill's full content
- **AND** the read SHALL be observable in the trace, distinguishing a skill that was invoked from one that was merely available

#### Scenario: An irrelevant skill is never read

- **WHEN** a request is unrelated to any discovered skill
- **THEN** no skill content SHALL be read
- **AND** the request SHALL incur only the cost of the skills' metadata

#### Scenario: One skill is selected from several plausible descriptions

- **WHEN** a request matches the descriptions of more than one skill
- **THEN** the agent SHALL select the skill that fits rather than reading every candidate
- **AND** the number of skill bodies read SHALL be observable in the trace as a cost distinct from the answer

#### Scenario: Reading a skill that does not fit is recoverable

- **WHEN** the agent reads a skill that turns out not to fit the request
- **THEN** it SHALL be able to read the skill that does
- **AND** the request SHALL continue rather than proceeding on the unfitting skill's guidance

#### Scenario: Menu size does not degrade selection silently

- **WHEN** skills are added to the menu
- **THEN** the effect on selection SHALL be measured rather than assumed
- **AND** a menu that has grown past the point where selection is reliable SHALL be detectable from that measurement

### Requirement: The agent cannot modify its own skills

The skills tier SHALL be read-only to the agent. No instruction SHALL be able to enter the agent's prompt without having passed through review of a repository change.

#### Scenario: A write to the skills tier is refused

- **WHEN** the agent attempts to write, edit, or delete within the skills tier
- **THEN** the operation SHALL fail
- **AND** the existing skill content SHALL be unchanged

#### Scenario: Adding a skill requires a repository change

- **WHEN** a new skill is to be made available to the agent
- **THEN** it SHALL be added to the repository and deployed
- **AND** it SHALL NOT be possible to introduce it at runtime

### Requirement: Existing serving behavior is preserved

Replacing the agent loop SHALL NOT change the agent's external contract. Both routes, streaming and non-streaming responses, tool activity in the stream, tracing, and degradation when the remote tool server is unreachable SHALL behave as before.

#### Scenario: Both routes answer as before

- **WHEN** a client sends a request to either route, streaming or not
- **THEN** the response format SHALL be unchanged from before the migration

#### Scenario: Remote tool server unreachable

- **WHEN** the remote tool server cannot be reached at startup
- **THEN** the agent SHALL start and serve requests without those tools
- **AND** the failure SHALL be logged and SHALL NOT be cached, so a later request can succeed

#### Scenario: Tool discovery is not repeated per request

- **WHEN** successive requests are served by the same process
- **THEN** remote tool discovery SHALL have been performed once
- **AND** subsequent requests SHALL NOT incur the discovery round trip

#### Scenario: Requests remain traced

- **WHEN** a request is served by the new loop
- **THEN** a trace SHALL be produced containing the agent's tool calls, and its planning and delegation activity
