## ADDED Requirements

### Requirement: Skill selection is scored as its own behaviour

Evaluation SHALL score which skills the agent read, separately from whether its answer was correct and separately from the method it used against the data. A correct answer reached after reading skills that did not apply SHALL score worse than the same answer reached without them, because the wasted reads are a cost the agent controls and no answer-quality measure detects.

Skill reads SHALL remain excluded from method scoring and from effort reported as query behaviour: a skill read is not a statement issued against the data, and counting it as one would falsify both. Exclusion from those measures SHALL NOT mean exclusion from measurement.

#### Scenario: Wasted reads are visible in the score

- **WHEN** the agent answers correctly after reading skills that did not apply to the question
- **THEN** the selection score SHALL be worse than for the same answer reached by reading only what applied
- **AND** the answer-quality score SHALL be unaffected

#### Scenario: Selection is scored on both directions of error

- **WHEN** selection is evaluated
- **THEN** it SHALL detect both failing to read a skill that applied and reading one that did not
- **AND** neither failure SHALL be inferable from the answer alone

#### Scenario: Skill reads stay out of method and effort figures

- **WHEN** method and effort are scored for a request in which skills were read
- **THEN** those figures SHALL count only statements issued against the data
- **AND** they SHALL be comparable with runs recorded before the menu existed

#### Scenario: A question matching no skill is scored for restraint

- **WHEN** a question matches no skill in the menu
- **THEN** reading no skill SHALL score better than reading any
- **AND** the question SHALL still be scored for the correctness of its answer
