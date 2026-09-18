## MODIFIED Requirements

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
