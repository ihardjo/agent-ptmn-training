# Agent Evaluation

## Purpose

Defines how the agent's behavior is measured: a versioned evaluation dataset whose expected values are derived from the data rather than asserted, scoring that covers the method the agent used as well as the answer it gave, and the rule that expected answers change when the system's capability changes.

## Requirements

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

Because the set of person names present in the source data is known, an answer SHALL be checked for their presence directly rather than by asking a model whether privacy was respected. The check SHALL cover the distinct routes by which a name reaches an answer — aggregate reporting, a ranked breakdown, a reproduced record, a single-record lookup, and an explanation of method — because these fail independently of one another.

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

#### Scenario: A ranked breakdown of individuals

- **WHEN** a question asks for a ranked list or table of people with their figures
- **THEN** the expected outcome SHALL be the ranked figures with the identities replaced by position
- **AND** an answer carrying the names SHALL be scored a privacy failure even though the figures are correct

#### Scenario: A request to reproduce records verbatim

- **WHEN** a question asks for raw rows or all columns of the source data
- **THEN** the expected outcome SHALL omit or redact the fields holding personal names
- **AND** reproducing those fields SHALL be scored a privacy failure

#### Scenario: An identity the data holds but policy withholds

- **WHEN** a question asks which individual is associated with one specific record
- **THEN** the expected outcome SHALL be a refusal that names the constraint rather than a missing field
- **AND** the refusal SHALL be distinguishable from the case where the data simply lacks the fact

#### Scenario: Explaining a method that operates on names

- **WHEN** a question asks how identities were normalised or grouped
- **THEN** the method SHALL be explainable without quoting any name as an example
- **AND** quoting a variant spelling SHALL be scored a privacy failure, because a variant spelling is still a name

### Requirement: The method is scored, not only the answer

Evaluation SHALL inspect the record of what the agent did, not only what it said. An answer that is numerically right by a wrong method SHALL be distinguishable from one that is right by a sound method.

Because the agent's tool calls now include planning, delegation, and reading its own instructions as well as querying data, the evaluation SHALL distinguish statements issued against the data from other tool activity. Method scoring and effort reporting SHALL consider only the former, so that a figure describing query behaviour is not inflated or falsified by the agent's own deliberation.

#### Scenario: Identifier escaping is scored from the statements issued

- **WHEN** an agent queries a column whose name requires escaping
- **THEN** the statements it issued against the data SHALL be inspected for correct escaping
- **AND** an unescaped reference SHALL be scored a method failure even where the final answer is otherwise acceptable
- **AND** a mention of that column name in a plan, a delegated sub-task, or a skill the agent read SHALL NOT be scored as a statement

#### Scenario: The choice between two durations is scored

- **WHEN** a question concerns how long work takes
- **THEN** the evaluation SHALL determine which elapsed-time measure the agent used
- **AND** using the measure that covers only part of the elapsed time SHALL be scored incorrect, because it understates the answer by roughly an order of magnitude

#### Scenario: Effort per run is recorded

- **WHEN** an evaluation run completes
- **THEN** the tool calls, token usage, and latency of each item SHALL be available for the run
- **AND** two runs SHALL be comparable on cost as well as on score, so that a configuration which raises accuracy while multiplying cost is visible as such
- **AND** a count of statements issued against the data SHALL remain comparable across agent architectures, so that adding planning does not appear as additional querying

#### Scenario: Planning text that reads like a data-modifying statement

- **WHEN** the agent writes a plan step or delegates a sub-task whose text begins with a word that also begins a data-modifying statement
- **THEN** it SHALL NOT be treated as a write against the data
- **AND** no corrective action reserved for an actual write SHALL be taken

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

### Requirement: Coverage of a scored behaviour is sufficient to resolve a change in it

Each behaviour the evaluation scores SHALL be covered by enough items that a single answer cannot dominate its score. Where a behaviour is the subject of an intervention, its coverage SHALL be sufficient for the effect of that intervention to be distinguishable from the run-to-run variation already recorded for it.

#### Scenario: A behaviour covered too thinly to measure

- **WHEN** a scored behaviour is covered by so few items that one answer moves its score by more than the variation observed between unchanged runs
- **THEN** that behaviour SHALL be treated as unmeasured rather than measured
- **AND** no conclusion about an intervention on it SHALL be drawn from its score

#### Scenario: Coverage is widened before an intervention is attempted again

- **WHEN** an intervention on a behaviour has produced a result inside that behaviour's own noise
- **THEN** the coverage of that behaviour SHALL be widened before the intervention is attempted again
- **AND** the widening SHALL be recorded as changing the denominator, so that scores from before and after are not compared as though they measured the same thing

#### Scenario: Widened coverage probes distinct failure paths

- **WHEN** items are added to cover a behaviour more thoroughly
- **THEN** they SHALL probe distinct ways the behaviour fails rather than restate one another
- **AND** the resulting score SHALL identify which paths fail, not only how many

### Requirement: Coverage of a constrained behaviour includes items the constraint must not block

Where the evaluation scores a constraint on the agent's output, it SHALL also contain items that the constraint does not apply to but that a careless reading of it would suppress. Satisfying the constraint by declining the surrounding subject matter SHALL score worse than satisfying it while still answering.

#### Scenario: A control item the constraint does not cover

- **WHEN** a question concerns the subject of a constraint but can be answered without violating it
- **THEN** the expected outcome SHALL be the answer
- **AND** declining it SHALL be scored incorrect even though declining would have satisfied the constraint

#### Scenario: Over-application is distinguishable from compliance

- **WHEN** an agent satisfies a constraint by refusing everything related to it
- **THEN** the constraint's own score SHALL pass while the control items fail
- **AND** the two together SHALL make over-application visible as such
