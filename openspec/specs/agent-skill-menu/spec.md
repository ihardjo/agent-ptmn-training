# agent-skill-menu Specification

## Purpose

Defines what the repository-held skill menu contains and how it is governed: the published authoring standard every skill conforms to, the hard limit that a skill may not contradict the agent's own safety rules, the deliberate-distractor design that makes skill selection observable, and the registry, security review, and selection evaluation each skill carries before it ships.

## Requirements

### Requirement: Every skill conforms to the published authoring standard

Each skill in the tier SHALL conform to the Agent Skills authoring standard. Its `name` SHALL be at most 64 characters of lowercase letters, numbers, and hyphens, SHALL contain no reserved vendor word, and SHALL follow one naming form consistently across the whole menu. Its `description` SHALL be non-empty, at most 1,024 characters, written in the third person, and SHALL state both what the skill does and when it applies. The body SHALL be under 500 lines, and any bundled reference SHALL be reachable in one step from the definition file rather than through another reference.

Conformance SHALL be checkable mechanically rather than by reading, so that a non-conforming skill is caught before it reaches the tier.

#### Scenario: A conforming skill is accepted

- **WHEN** the menu is checked against the standard
- **THEN** every skill SHALL satisfy the name, description, body-length, and reference-depth limits
- **AND** the check SHALL report which limit each skill was measured against

#### Scenario: A non-conforming skill is reported

- **WHEN** a skill exceeds a limit, omits a required field, or writes its description in the first or second person
- **THEN** the check SHALL fail and SHALL name the skill and the limit it violated
- **AND** the failure SHALL be reported before deployment rather than at request time

#### Scenario: Naming is consistent across the menu

- **WHEN** the skill names are listed
- **THEN** they SHALL all use the same naming form
- **AND** no name SHALL be a vague or generic term that fails to identify the activity it covers

### Requirement: A skill may not contradict the agent's safety rules

No skill body SHALL direct the agent to ignore, weaken, or condition any rule carried in its system prompt. In particular, no skill SHALL direct the agent to disclose an individual's identity, nor to supply a figure that neither the data nor the policy source contains. A skill that competes for selection SHALL do so through its description only; its body SHALL be correct.

This holds regardless of intent. A skill authored to demonstrate a failure is indistinguishable at runtime from one authored to cause it, so the prohibition SHALL be on the content and not on the motive.

#### Scenario: A skill body contradicting a safety rule is refused

- **WHEN** a skill body would instruct the agent to name an individual, to supply an outside figure, or to disregard an instruction it has been given
- **THEN** that skill SHALL NOT be admitted to the tier
- **AND** the reason SHALL be recorded, so the decision is not reconsidered as though it were untested

#### Scenario: Reading any skill leaves the safety rules intact

- **WHEN** the agent reads any skill in the menu and acts on it
- **THEN** no individual SHALL be named in the answer
- **AND** no figure SHALL appear that neither the data nor the policy source supplies

#### Scenario: The tier carries no executable content

- **WHEN** the contents of the tier are inspected
- **THEN** they SHALL contain no executable script, no network call, and no credential
- **AND** the tier SHALL consist of documents that are read rather than run

### Requirement: The menu contains deliberate distractors

The menu SHALL contain skills whose descriptions compete for selection with a skill that is a better fit, so that choosing correctly is a capability the agent can be observed exercising rather than one it gets for free from a menu with a single plausible entry.

A distractor SHALL compete through its description and SHALL be truthful in its body. Where a distractor is selected, reading it SHALL lead the agent to the correct skill or to a correct refusal. The cost of a mis-selection SHALL therefore be a wasted read, never a wrong answer.

#### Scenario: A distractor competes for a question a core skill serves better

- **WHEN** a question matches both a distractor's description and a core skill's description
- **THEN** both SHALL be plausible from their descriptions alone
- **AND** the correct choice SHALL be determinable only from content the descriptions do not carry

#### Scenario: A selected distractor does not produce a wrong answer

- **WHEN** the agent reads a distractor's body
- **THEN** that body SHALL redirect it to the skill that fits, or SHALL state that the data cannot answer the question
- **AND** the agent's final answer SHALL be no worse than if the distractor had not been read

#### Scenario: A distractor promising an absent capability declines

- **WHEN** a distractor's description offers an analysis the data holds no field for
- **THEN** its body SHALL state which field is missing
- **AND** it SHALL direct the agent to report the gap rather than to substitute a proxy

### Requirement: Skill selection is measured before the menu grows

Each skill SHALL carry a set of representative queries covering cases where it should be selected, cases where it should not, and at least one case where the correct choice is genuinely ambiguous. Selection accuracy SHALL be measured against those queries, and SHALL be reported separately from the correctness of the agent's answers, because a right answer reached by reading three wrong skills is a distinct failure that answer scoring does not detect.

Adding a skill to the menu SHALL require that selection accuracy across the existing menu be re-measured, so that a new description broadening over an existing skill's territory is caught as a regression.

#### Scenario: Each skill carries its own selection queries

- **WHEN** a skill is added to the menu
- **THEN** it SHALL be accompanied by queries for which it should be selected, queries for which it should not, and an ambiguous case
- **AND** a skill without them SHALL NOT be admitted

#### Scenario: Selection is scored apart from answer quality

- **WHEN** a request is evaluated
- **THEN** which skills were read SHALL be scored separately from whether the answer was correct
- **AND** a correct answer reached after reading skills that did not apply SHALL be distinguishable from one reached without them

#### Scenario: A broadened description is caught as a regression

- **WHEN** a skill is added or its description is widened
- **THEN** selection accuracy SHALL be re-measured across the whole menu
- **AND** a fall in the selection accuracy of any existing skill SHALL be reported as a regression of this change rather than attributed to the older skill

### Requirement: Each skill carries a governance record

Every skill SHALL have a recorded purpose, an owner accountable for maintaining it, a version, the sources it depends on, and the date and outcome of its last evaluation. The tier SHALL also carry the outcome of a security review covering every skill against the published risk indicators.

A skill SHALL be reviewed by someone other than its author. Where skills are machine-authored, the review is the human contribution and SHALL NOT be treated as satisfied by the authoring step.

#### Scenario: The registry accounts for every skill

- **WHEN** the registry is compared against the tier
- **THEN** every skill present SHALL have a registry entry, and every entry SHALL correspond to a skill present
- **AND** each entry SHALL record purpose, owner, version, dependencies, and evaluation status

#### Scenario: A skill's dependencies are discoverable without reading it

- **WHEN** a skill depends on a policy document or a data field that may change
- **THEN** that dependency SHALL be recorded in the registry
- **AND** a change to the dependency SHALL be traceable to the skills affected by it

#### Scenario: Review is separate from authorship

- **WHEN** a skill is added or changed
- **THEN** the change SHALL be reviewed by a person who did not author it
- **AND** the security review outcome SHALL be recorded against the version reviewed

### Requirement: A skill earns its place by carrying what the prompt does not

A skill SHALL NOT restate guidance already carried in the agent's standing instructions. Content that applies to most requests belongs in those instructions, where it is loaded once; content placed in a skill is paid for twice, as a description on every request and as a body when read.

A skill SHALL therefore carry a procedure that is needed rarely, is specific enough that the agent would otherwise get it wrong, or spans sources the standing instructions do not join.

#### Scenario: A duplicate of the standing instructions is not admitted

- **WHEN** a proposed skill's content is already present in the agent's standing instructions
- **THEN** it SHALL NOT be admitted as a skill
- **AND** the standing instructions SHALL remain the single place that content lives

#### Scenario: A skill spanning sources is admitted

- **WHEN** a procedure requires combining measured data with policy held outside the data
- **THEN** it SHALL be eligible for the menu
- **AND** the standing instructions SHALL point to it rather than reproducing it
