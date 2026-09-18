## MODIFIED Requirements

### Requirement: Expectations are versioned against system capability

The expected outcome for a question SHALL reflect what the system is capable of at that version. When a capability is added that makes a previously unanswerable question answerable, the affected items SHALL be updated to expect an answer, and the version those expectations represent SHALL be recorded where a consumer of a score can discover it.

The version SHALL NOT be required to live in the dataset's identity. Where the platform holding the dataset requires item identifiers to be unique across datasets, a new dataset cannot reuse the identifiers of the old one, and stable identifiers take precedence: they are what makes a run comparable to an earlier run item by item. In that case the dataset is mutated in place and the version is carried alongside it.

A consequence follows and SHALL be stated rather than left implicit: where expectations are mutated in place, superseded expectations are not re-runnable. Past runs retain their recorded scores, but the answer key they were measured against no longer exists.

#### Scenario: A question unanswerable at one version and answerable at the next

- **WHEN** a question requires a fact the system has no access to
- **THEN** the expected outcome at that version SHALL be a refusal
- **AND** when a later version supplies access to that fact, the same item SHALL be updated to expect the computed answer
- **AND** the item SHALL keep its identifier, so the two runs remain comparable item by item

#### Scenario: Adding capability can lower the score

- **WHEN** items are updated from expecting a refusal to expecting an answer
- **THEN** the score MAY fall, because the agent is now being asked to do more
- **AND** such a fall SHALL NOT be treated as a regression in the agent

#### Scenario: The platform forbids a versioned dataset identity

- **WHEN** item identifiers must be unique across datasets, so a second dataset cannot reuse them
- **THEN** the dataset SHALL be mutated in place and its version recorded alongside it rather than encoded in its name
- **AND** a consumer SHALL be able to determine which expectations a score was measured against without relying on the dataset's name

#### Scenario: A score quoted from a superseded answer key

- **WHEN** a score was recorded against expectations that have since been updated
- **THEN** that score SHALL remain readable with the version it was measured against
- **AND** it SHALL NOT be presented as comparable to a score measured against the current expectations
