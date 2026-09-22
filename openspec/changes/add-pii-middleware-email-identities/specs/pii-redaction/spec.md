## Purpose

Defines the output-side net that removes identity-bearing values from what the agent returns to a caller, and the boundaries of that net: where it applies, where applying it would destroy required behaviour, and which surfaces it does not reach. The net exists because the agent's privacy rule is otherwise enforced only by instruction on the answer path.

## ADDED Requirements

### Requirement: Identity-bearing values are removed from the answer by the system

The agent's answer SHALL be checked for identity-bearing values by the system before it reaches the caller, and any found SHALL be removed. This check SHALL NOT depend on the agent having chosen to comply with its instructions.

Detection SHALL be by the **shape** of the value rather than by membership of an enumerated list of known identities. A closed vocabulary cannot recognise a spelling nobody enumerated; shape-based detection is what covers the identities the vocabulary does not hold.

#### Scenario: An answer carrying an identity value

- **WHEN** the agent's answer contains a value matching the shape of an identity field
- **THEN** that value SHALL NOT appear in the response delivered to the caller

#### Scenario: A compliant answer is delivered unchanged

- **WHEN** the agent's answer reports figures by rank and carries no identity value
- **THEN** the response SHALL be delivered byte-for-byte as the agent produced it

#### Scenario: An identity spelling absent from the known set

- **WHEN** an answer carries an identity value that is not present in the enumerated set of known identities but matches the identity field's shape
- **THEN** it SHALL still be removed

### Requirement: Removal is a net beneath the instruction, not a substitute for it

The instruction requiring the agent to report identities by rank SHALL remain the primary control. Removal SHALL NOT be treated as satisfying the output requirement on its own, because substituting a placeholder for each occurrence produces a privacy-safe answer that is still the wrong answer: the required form replaces identities with their **position in a ranking**, which is a transformation over the whole result set and cannot be produced by per-value substitution.

#### Scenario: A redacted answer is still a defective answer

- **WHEN** the net removes an identity from an answer that a rank-based answer would not have contained
- **THEN** the delivered answer SHALL be recorded as a failure of the agent to follow its instruction
- **AND** it SHALL NOT be scored as compliant merely because no identity was delivered

#### Scenario: Ranked reporting needs no removal

- **WHEN** the agent reports a concentration finding as a ranked table with positions in place of identities
- **THEN** the net SHALL find nothing to remove

### Requirement: A detected identity degrades the answer rather than failing the request

Detection SHALL NOT terminate the request. The caller SHALL receive an answer with the identity removed rather than an error, consistent with the durable-write guard, which returns a recoverable error so the agent can restate its finding rather than aborting the turn.

#### Scenario: Detection during a request

- **WHEN** an identity value is detected in the agent's answer
- **THEN** the request SHALL complete and return a response
- **AND** the caller SHALL NOT receive an error status in place of the answer

### Requirement: Values the agent must reason over are not removed before it sees them

Identity values SHALL remain intact in the results of tools the agent calls. The agent is required to aggregate by identity in order to discover how work is distributed; removing identities from tool results would collapse distinct individuals into one indistinguishable value and make the distribution unreportable.

The constraint SHALL apply to what the agent writes, not to what it reads.

#### Scenario: Aggregating by identity

- **WHEN** the agent queries the source data grouped by an identity field
- **THEN** the returned rows SHALL carry their distinct identity values
- **AND** the agent SHALL be able to compute each identity's share of the total

#### Scenario: Removal that would destroy grouping is not applied

- **WHEN** identity removal is configured
- **THEN** it SHALL NOT be applied to tool results
- **AND** it SHALL NOT be applied to the caller's question, which the agent must be able to read in full in order to decline it correctly

### Requirement: Values required for traceability are not removed

Removal SHALL be scoped to the identity field's shape only. Values that carry no identity but which the agent's output requirements depend on — notably the source references that let a reader trace a figure back to the document or record it came from — SHALL NOT be removed.

Enabling removal for a value class that the traceability requirement depends on SHALL be treated as a regression, not as additional safety.

#### Scenario: A cited source reference survives

- **WHEN** an answer cites a policy document by its recorded source reference
- **THEN** that reference SHALL appear intact in the delivered answer

#### Scenario: Over-broad removal is a regression

- **WHEN** removal is configured for a value class that appears in source references
- **THEN** the configuration SHALL be rejected as a regression against the traceability requirement

### Requirement: Surfaces the net does not reach are documented

Where the transport delivers agent activity over more than one channel, any channel the net does not cover SHALL be documented as an uncovered surface, with what it can carry and why it is out of scope.

An uncovered surface SHALL NOT be described as covered, and the answer path SHALL be covered regardless.

#### Scenario: An uncovered channel is recorded

- **WHEN** a delivery channel exists that the net does not process
- **THEN** it SHALL be named in the change record together with the content it can carry
- **AND** the coverage claim made for the net SHALL exclude it

#### Scenario: The answer path is covered

- **WHEN** the agent's prose answer is streamed to the caller
- **THEN** it SHALL pass through the net before delivery
