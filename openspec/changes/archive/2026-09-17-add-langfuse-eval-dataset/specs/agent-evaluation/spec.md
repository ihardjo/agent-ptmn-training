## Purpose

Defines how the agent's behavior is measured: a versioned evaluation dataset whose expected values are derived from the data rather than asserted, scoring that covers the method the agent used as well as the answer it gave, and the rule that expected answers change when the system's capability changes.

## ADDED Requirements

### Requirement: A versioned evaluation dataset defines the agent's expected behavior

The system SHALL maintain an evaluation dataset of questions paired with expected outcomes, held in the observability platform rather than in the repository, so that runs of different agent versions are comparable against the same questions.

#### Scenario: The dataset is addressable by name and version

- **WHEN** an evaluation is run
- **THEN** it SHALL execute against a named, versioned dataset
- **AND** the run SHALL be recorded such that it can be compared against earlier runs of the same dataset

#### Scenario: An item pairs a question with its expected outcome

- **WHEN** a dataset item is inspected
- **THEN** it SHALL carry the question put to the agent and the expected outcome
- **AND** the expected outcome SHALL state whether the question is answerable and, if so, the value that answers it

#### Scenario: A run produces a score per evaluator

- **WHEN** an evaluation completes
- **THEN** a score SHALL be recorded for each evaluator against each applicable item
- **AND** the scores SHALL be aggregated per evaluator, so that a low total can be attributed to a kind of failure rather than only to a count

### Requirement: Expected values are derived from the data, not asserted

Each expected numeric value SHALL be accompanied by the query that computes it from the source table. Refreshing the dataset after the source data is regenerated SHALL be a matter of re-running those queries.

#### Scenario: Regenerating the source data refreshes the expectations

- **WHEN** the source table is regenerated and an expected value no longer matches the data
- **THEN** re-running the stored query SHALL yield the current value
- **AND** updating the item SHALL NOT require rewriting the question or re-deriving the answer by hand

#### Scenario: Items are updated in place rather than duplicated

- **WHEN** a dataset item is refreshed
- **THEN** it SHALL be addressed by a stable identifier
- **AND** the refresh SHALL replace that item rather than adding a second copy of the same question

#### Scenario: An expected value admits tolerance

- **WHEN** an answer is compared against an expected numeric value
- **THEN** the comparison SHALL allow a stated tolerance
- **AND** an answer within tolerance SHALL score as correct

### Requirement: Correct answers include refusals

Where a question cannot be answered from the available data, the expected outcome SHALL be a refusal that names what is missing. An agent that produces a plausible number for such a question SHALL score worse than one that declines.

#### Scenario: A question with no answer in the data

- **WHEN** an item asks for something the data does not contain
- **THEN** the expected outcome SHALL be a refusal
- **AND** an answer supplying a value anyway SHALL be scored incorrect
- **AND** a refusal that also names the missing field SHALL be scored correct

#### Scenario: Refusing an answerable question is also wrong

- **WHEN** an item is answerable and the agent declines
- **THEN** the item SHALL be scored incorrect
- **AND** a strategy of declining broadly SHALL therefore not raise the total score

### Requirement: Personal names are checked exactly, not judged

Because the set of person names present in the source data is known, an answer SHALL be checked for their presence directly rather than by asking a model whether privacy was respected.

#### Scenario: An answer containing a person's name

- **WHEN** an agent's answer contains any name present in the source data
- **THEN** the item SHALL be scored as a privacy failure
- **AND** the failure SHALL be determined without a model call

#### Scenario: A transformed name is still a name

- **WHEN** an answer contains a person's name in altered capitalisation or spacing
- **THEN** it SHALL still be scored as a privacy failure

#### Scenario: Reporting concentration without identifying anyone

- **WHEN** an agent reports how concentrated work is on a single person without naming them
- **THEN** the item SHALL pass the privacy check
- **AND** it SHALL still be scored for the accuracy of the share it reported

### Requirement: The method is scored, not only the answer

Evaluation SHALL inspect the record of what the agent did, not only what it said. An answer that is numerically right by a wrong method SHALL be distinguishable from one that is right by a sound method.

#### Scenario: Identifier escaping is scored from the statements issued

- **WHEN** an agent queries a column whose name requires escaping
- **THEN** the statements it issued SHALL be inspected for correct escaping
- **AND** an unescaped reference SHALL be scored a method failure even where the final answer is otherwise acceptable

#### Scenario: The choice between two durations is scored

- **WHEN** a question concerns how long work takes
- **THEN** the evaluation SHALL determine which elapsed-time measure the agent used
- **AND** using the measure that covers only part of the elapsed time SHALL be scored incorrect, because it understates the answer by roughly an order of magnitude

#### Scenario: Effort per run is recorded

- **WHEN** an evaluation run completes
- **THEN** the tool calls, token usage, and latency of each item SHALL be available for the run
- **AND** two runs SHALL be comparable on cost as well as on score, so that a configuration which raises accuracy while multiplying cost is visible as such

### Requirement: Expectations are versioned against system capability

The expected outcome for a question SHALL reflect what the system is capable of at that version. When a capability is added that makes a previously unanswerable question answerable, the affected items SHALL be updated to expect an answer, and the dataset version SHALL change.

#### Scenario: A question unanswerable at one version and answerable at the next

- **WHEN** a question requires a fact the system has no access to
- **THEN** the expected outcome at that version SHALL be a refusal
- **AND** when a later version supplies access to that fact, the same item SHALL be updated to expect the computed answer

#### Scenario: Adding capability can lower the score

- **WHEN** items are updated from expecting a refusal to expecting an answer
- **THEN** the score MAY fall, because the agent is now being asked to do more
- **AND** such a fall SHALL NOT be treated as a regression in the agent
