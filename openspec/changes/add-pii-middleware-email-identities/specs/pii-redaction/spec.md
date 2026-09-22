## Purpose

Defines the system-enforced net that keeps identity-bearing values out of what the agent returns to a caller, and the boundaries of that net: where in the turn it has to act, where acting would destroy required behaviour, and which surfaces it does not reach. The net exists because the agent's privacy rule is otherwise enforced only by instruction on the answer path.

## ADDED Requirements

### Requirement: No identity reaches the caller in the agent's answer

The answer delivered to a caller SHALL contain no identity-bearing value, and this SHALL NOT depend on the agent having chosen to comply with its instructions. The requirement is on the delivered bytes; where in the turn the system acts to achieve it is a design decision, constrained by the requirement below that it act before the model generates.

Detection SHALL be by the **shape** of the value rather than by membership of an enumerated list of known identities. A closed vocabulary cannot recognise a spelling nobody enumerated; shape-based detection is what covers the identities the vocabulary does not hold.

#### Scenario: An answer that would otherwise carry an identity value

- **WHEN** the agent is asked a question whose data contains identity values
- **THEN** no identity value SHALL appear in the response delivered to the caller
- **AND** this SHALL be verified over the transport the routes actually serve, not only over an in-process call

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

### Requirement: Identities are pseudonymised before the model receives them

Identity values SHALL be replaced with a stable pseudonym in tool results **before the model sees them**. A model that never receives an identity cannot emit one, and that guarantee holds regardless of how the answer is subsequently transported.

Removal SHALL NOT be applied only on the way out. Where the answer is delivered token by token as the model produces it, a rewrite performed after generation reaches the stored conversation but not the bytes already sent, so an output-side control can pass every test and still protect no served request.

The pseudonym SHALL preserve distinguishability: two different people SHALL receive two different pseudonyms, and the same value SHALL always receive the same one. The agent is required to aggregate by identity to discover how work is distributed, and a scheme that collapsed every identity to a single token would make the distribution unreportable.

The pseudonym SHALL be derived from the value exactly as stored, without normalising it first. Normalising on the agent's behalf would silently repair the dataset's planted identity-variant defect, removing the requirement that the agent normalise before aggregating.

#### Scenario: The model never receives an identity

- **WHEN** a tool returns rows containing identity values
- **THEN** the content passed to the model SHALL contain no identity value
- **AND** this SHALL hold for the streamed answer as well as a non-streamed one

#### Scenario: Distinct people remain distinct

- **WHEN** a tool returns rows for two different people
- **THEN** the pseudonymised rows SHALL carry two different values
- **AND** the agent SHALL still be able to compute each one's share of the total

#### Scenario: One person does not split

- **WHEN** the same identity value appears in several rows
- **THEN** every occurrence SHALL receive the same pseudonym

#### Scenario: The planted variant defect is not repaired

- **WHEN** one person appears under several spellings that differ only in case or surrounding whitespace
- **THEN** those spellings SHALL receive different pseudonyms
- **AND** an agent aggregating without normalising SHALL still understate the concentration

#### Scenario: An identity in the question is pseudonymised too

- **WHEN** the caller's question contains an identity value
- **THEN** the model SHALL receive it pseudonymised, so it cannot echo the value back

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
