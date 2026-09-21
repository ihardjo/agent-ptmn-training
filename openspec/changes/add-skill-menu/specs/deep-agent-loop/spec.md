## MODIFIED Requirements

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
