# volume-backed-wiki Specification

## Purpose

Defines the agent's durable knowledge tier: how policy facts reach the agent from a Unity Catalog Volume as an Open Knowledge Format bundle, how files arrive in the format they were authored in, how the agent writes durable notes into the same wiki, how a reader tells authored policy from an agent's note, what may never be written there, and how the agent behaves when the Volume is unreachable.

## Requirements

### Requirement: The knowledge tier is an Open Knowledge Format bundle

The tier SHALL be a conformant OKF v0.2 bundle. Every non-reserved markdown document in it SHALL carry a parseable YAML frontmatter block containing a non-empty `type`. The reserved filenames `index.md` and `log.md` SHALL, when present, be a directory listing and an update history respectively rather than concept documents. The agent SHALL be able to consume the bundle without bespoke tooling, and SHALL tolerate unknown `type` values, unknown frontmatter keys, and missing optional fields rather than rejecting a document.

#### Scenario: A concept document is read

- **WHEN** the agent reads a document from the tier
- **THEN** the document SHALL have frontmatter declaring its `type`
- **AND** the agent SHALL be able to use the body without needing a schema registry or a format-specific parser

#### Scenario: A document carrying an unfamiliar type or extra keys

- **WHEN** a document declares a `type` the agent has no handling for, or frontmatter keys it does not recognise
- **THEN** the agent SHALL treat it as a generic concept and use it
- **AND** it SHALL NOT be rejected or reported as malformed

#### Scenario: A document the agent writes

- **WHEN** the agent writes a durable note to the tier
- **THEN** that document SHALL also carry frontmatter with a non-empty `type`
- **AND** the bundle SHALL remain conformant after the write, because the agent is a producer of the bundle and not only a consumer

#### Scenario: A reserved filename

- **WHEN** a file named `index.md` or `log.md` is present
- **THEN** it SHALL be treated as a listing or a history rather than as a concept
- **AND** the agent SHALL NOT require either to be present in order to use the tier

### Requirement: Policy facts carry their provenance and trust state

A concept stating a policy fact the data cannot supply — a resolution target, a threshold, a definition — SHALL record where it came from and what has confirmed it, using the OKF provenance, trust, and lifecycle families. An answer that rests on such a fact SHALL cite the concept it came from.

#### Scenario: An answer that depends on a policy fact

- **WHEN** the agent answers using a target read from the tier
- **THEN** it SHALL name the concept the target came from
- **AND** the figure SHALL be attributable to that document rather than presented as though it came from the data

#### Scenario: A fact whose freshness has lapsed

- **WHEN** a concept declares a staleness horizon and that horizon has passed
- **THEN** the agent SHALL report the fact as possibly out of date rather than as current
- **AND** it SHALL still be usable, since staleness is an advisory signal and not an access control

#### Scenario: A fact with no confirmation recorded

- **WHEN** a concept carries no verification
- **THEN** the agent SHALL still be able to use it
- **AND** the absence of confirmation SHALL be reportable, so an unconfirmed target is distinguishable from a confirmed one

### Requirement: Internal knowledge sources are reachable as files

Policy content SHALL be readable by the agent as files under a durable tier, without that content existing as a Unity Catalog table and without the agent holding credentials for the system it was authored in.

The tier SHALL carry two prefixes, divided by the form content arrives in rather than by who wrote it. A **landing prefix** SHALL hold files as people dropped them, in whatever format they arrived in, including formats that are not markdown. A **wiki prefix** SHALL hold the OKF bundle the agent reads and writes. A reader SHALL be able to tell from the prefix alone which of the two a path names.

#### Scenario: A policy fact is read from the wiki prefix

- **WHEN** the agent needs a policy fact
- **THEN** it SHALL read that content through the durable tier's filesystem interface
- **AND** the document it reads SHALL be a conformant OKF concept

#### Scenario: A source document arrives in its authored format

- **WHEN** a person drops a file that is not markdown under the landing prefix
- **THEN** it SHALL remain reachable there in that format
- **AND** the agent SHALL be able to read its text without that file having been converted first

#### Scenario: No source-system credentials in the agent

- **WHEN** the agent reads internal knowledge content
- **THEN** it SHALL do so through the durable tier alone
- **AND** it SHALL NOT authenticate to the authoring system directly

### Requirement: The landing prefix is read-only to the agent

The landing prefix SHALL refuse writes, edits, and deletes from the agent. It is where people put files, and what someone put there SHALL be changeable where they put it rather than through the agent, so that the copy the agent reads cannot diverge from its origin through the agent's own action.

The refusal SHALL be enforced by a rule the agent cannot reach, not by instruction and not by the storage grant. A grant over the Volume covers both prefixes alike, so an absent rule leaves the prefix writable however firmly the prompt forbids it.

#### Scenario: A write to the landing prefix is refused

- **WHEN** the agent attempts to write, edit, or delete under the landing prefix
- **THEN** the operation SHALL fail
- **AND** the existing content SHALL be unchanged

#### Scenario: The refusal holds against an injected instruction

- **WHEN** content the agent reads instructs it to write to the landing prefix
- **THEN** the write SHALL still be refused
- **AND** the refusal SHALL not depend on the agent having declined to attempt it

#### Scenario: A refused write does not end the request

- **WHEN** a write to a source prefix is refused
- **THEN** the agent SHALL receive the refusal as a result it can act on
- **AND** the request SHALL continue rather than terminating

### Requirement: The agent writes durable notes into the wiki

The agent SHALL be able to record what it learns to the wiki prefix. A note written during one request SHALL be readable in a later request, in a different session, by a different user.

Notes SHALL be held in the wiki itself, alongside authored policy, rather than in a tier of their own. A knowledge base divided by author is two knowledge bases, and a reader looking for what is known about a subject SHALL find it in one place.

#### Scenario: A note survives the thread

- **WHEN** the agent writes a note to the writable prefix and the thread ends
- **THEN** the note SHALL be readable in a subsequent request
- **AND** its content SHALL be unchanged by the thread ending

#### Scenario: A note is visible across sessions and users

- **WHEN** a note written in one session is sought in another
- **THEN** it SHALL be readable there
- **AND** it SHALL NOT be scoped to the session or user that wrote it

#### Scenario: A note is revisable

- **WHEN** the agent determines a note it previously wrote is wrong or stale
- **THEN** it SHALL be able to overwrite or delete that note
- **AND** the change SHALL be durable on the same terms as the original write

#### Scenario: A re-seed leaves a note at an unseeded path alone

- **WHEN** the committed bundle is uploaded again
- **THEN** a note the agent wrote at a path the bundle does not contain SHALL be unaffected
- **AND** a path the bundle does contain MAY be replaced, since the seeded document is the authored one

### Requirement: Provenance is carried by the actor, not by the path

The wiki prefix holds both authored policy and the agent's own notes, so the path SHALL NOT be what distinguishes them. Every document SHALL instead declare its author in OKF frontmatter, under the §7 actor convention: a `human:` actor for authored content, and `<producer>/<version>` for a document the agent generated.

The agent SHALL NOT be asked to supply its own actor. The write path SHALL stamp it, so that conformance is a property of the tier rather than of the agent's good behaviour.

A consumer SHALL be able to rank the two: a figure SHALL rest on authored policy or on the data, and never on a document some earlier turn generated.

#### Scenario: An agent's note declares an agent actor

- **WHEN** the agent writes a note
- **THEN** the stored document SHALL carry a `generated.by` naming the producer and its version
- **AND** that value SHALL NOT have been supplied by the model

#### Scenario: Authored policy is distinguishable from a generated note

- **WHEN** a reader encounters two documents under the wiki prefix
- **THEN** the actor in each document's frontmatter SHALL say which was authored and which was generated
- **AND** the distinction SHALL NOT require knowing which path each was read from

#### Scenario: A generated note is not evidence for a figure

- **WHEN** a figure could be drawn from a document carrying an agent actor
- **THEN** the agent SHALL recompute it from the data instead
- **AND** where the two disagree, the data SHALL win

### Requirement: Durability does not weaken the privacy constraint

The constraint forbidding the agent from identifying an individual SHALL apply to everything the agent writes to the durable tier, not only to what it returns to a caller. A durable file outlives the reply that prompted it and is readable by users who never asked the original question, so it SHALL be treated as the wider disclosure, not the narrower one.

The constraint SHALL hold against **every form the identity takes**, not only the form a person would write. Where the data records staff by a derived identifier rather than by name, disclosing that identifier SHALL be a disclosure of the individual: an identifier that names no one in its own text still names someone in effect, and a guard that admits it on that basis is defeated on a technicality.

#### Scenario: A name is not persisted

- **WHEN** the agent writes to the durable tier after querying data containing staff identities
- **THEN** no personal name SHALL appear in the written content
- **AND** the aggregate or ranked form SHALL be written instead, as it would be in an answer

#### Scenario: A derived identifier is not persisted either

- **WHEN** the agent writes to the durable tier content carrying the identifier the data records a person by, rather than that person's name
- **THEN** the write SHALL be refused on the same footing as a name
- **AND** the refusal SHALL remain recoverable, so the agent can restate the finding in ranked form

#### Scenario: Row-level data is not accumulated on the Volume

- **WHEN** the agent records something it learned from querying the ticket table
- **THEN** it SHALL write the finding rather than the rows the finding came from
- **AND** the durable tier SHALL NOT become a copy of the remote table

#### Scenario: The constraint is not satisfied by refusing to write

- **WHEN** a finding worth recording concerns the distribution of work across people
- **THEN** the agent SHALL still record it in a form that names no individual
- **AND** declining to record it at all SHALL NOT be the expected behavior

### Requirement: An unreachable Volume degrades the request, not the process

The agent SHALL start and serve requests when the durable tier is unconfigured or unreachable. A failure to reach the Volume SHALL be reported to the agent as a result and logged, and SHALL NOT be cached in a way that prevents a later request from succeeding.

#### Scenario: The tier is not configured

- **WHEN** no Volume is configured for the durable tier
- **THEN** the agent SHALL start and serve requests using its remaining capabilities
- **AND** the absence SHALL be reported in the application log

#### Scenario: The Volume cannot be reached mid-request

- **WHEN** a read or write against the durable tier fails
- **THEN** the agent SHALL receive the failure as a result it can act on
- **AND** the request SHALL continue rather than terminating

#### Scenario: A transient failure is not cached

- **WHEN** the Volume is unreachable during one request and reachable during the next
- **THEN** the later request SHALL succeed
- **AND** it SHALL NOT be refused on the strength of the earlier failure

### Requirement: A fact absent from both the data and the wiki is still refused

Adding the durable tier SHALL NOT convert the agent's refusals into guesses. Where a question needs a fact that neither the ticket table nor the wiki supplies, the agent SHALL decline and name what is missing, exactly as it does today.

#### Scenario: The wiki supplies the missing target

- **WHEN** a question requires a resolution target and the wiki holds it
- **THEN** the agent SHALL compute the answer using that target
- **AND** it SHALL state that the target came from the wiki rather than from the data

#### Scenario: Neither source holds the fact

- **WHEN** a question requires a fact held in neither the table nor the wiki
- **THEN** the agent SHALL decline and name the missing fact
- **AND** it SHALL NOT substitute an industry-typical value or infer one

#### Scenario: A read is evidenced, not asserted

- **WHEN** an answer depends on a fact drawn from the wiki
- **THEN** the trace SHALL show the read that supplied it
- **AND** an answer citing a wiki fact without a corresponding read SHALL be distinguishable from one that read it
