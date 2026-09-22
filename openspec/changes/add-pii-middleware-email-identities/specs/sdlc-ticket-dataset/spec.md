## ADDED Requirements

### Requirement: Identity fields are email-valued and derived from a documented rule

The fields recording who reported and who was assigned to a ticket SHALL hold email addresses rather than person names. Each address SHALL be produced from a person's name by a single documented, deterministic rule, so that an address can be folded back to exactly one identity and two addresses can be compared for identity without a lookup table.

The rule SHALL be recorded alongside the dataset definition. No identity SHALL appear in the dataset in name form.

This representation SHALL NOT change the column count, the column names, or the set of columns requiring escaping.

#### Scenario: Identity fields hold addresses

- **WHEN** the distinct values of the reporter and assignee fields are listed
- **THEN** every non-absent value SHALL be an email address
- **AND** no value SHALL be a person's name in the form a person would write it

#### Scenario: An address resolves to one identity

- **WHEN** the documented derivation rule is applied in reverse to any address in the dataset
- **THEN** it SHALL yield exactly one identity
- **AND** two addresses derived from the same identity SHALL be recognisable as the same identity

#### Scenario: The schema is unchanged in shape

- **WHEN** the table schema is inspected before and after this change
- **THEN** the column count SHALL be identical
- **AND** the set of columns requiring backtick escaping SHALL be unchanged

#### Scenario: An address is an identity for privacy purposes

- **WHEN** a consumer reproduces an identity field's value in an answer
- **THEN** it SHALL be treated as having identified an individual
- **AND** the absence of a name in the value SHALL NOT make it compliant

## MODIFIED Requirements

### Requirement: The dataset contains planted, documented findings

The dataset SHALL contain a documented set of non-obvious patterns that a competent analyst can discover. Each planted finding SHALL be verifiable by query, and the verifying query SHALL be recorded alongside the dataset definition.

Where a finding concerns an individual, it SHALL be reportable without disclosing that individual — whether in name form or in any other form the dataset represents identity in.

#### Scenario: A planted finding is verifiable

- **WHEN** the verifying query for a planted finding is run against the dataset
- **THEN** the finding SHALL be present at the documented magnitude

#### Scenario: A naive query misrepresents a planted finding

- **WHEN** a consumer asks how long work takes and is answered from end-to-end duration alone
- **THEN** the answer SHALL materially misrepresent the dataset, because waiting dominates working
- **AND** the correct characterisation SHALL require distinguishing the two intervals

#### Scenario: Concentration of work on one individual is present

- **WHEN** closures are aggregated by the identity assigned
- **THEN** a single individual SHALL account for a documented and disproportionate share
- **AND** that share SHALL be reportable in aggregate without identifying the individual

#### Scenario: The concentration magnitude survives the identity representation

- **WHEN** the concentration finding is recomputed after identities change representation
- **THEN** the documented share SHALL be unchanged
- **AND** the number of distinct individuals SHALL be unchanged

### Requirement: The dataset contains planted, documented defects

The dataset SHALL contain a documented set of data-quality defects, so that validation and stewardship work has something real to find. Each defect class SHALL have a documented row count and a detecting query.

The identity-variant defect SHALL be expressed in whatever form the dataset represents identity in, so that aggregating by identity without normalising first understates the concentration finding regardless of that representation.

#### Scenario: Chronologically impossible rows exist

- **WHEN** rows are checked for closure preceding creation
- **THEN** a documented number of violating rows SHALL be found

#### Scenario: Cross-field inconsistencies exist

- **WHEN** rows are checked for a duration recorded against work that has not closed, for closure without a resolution, or for a status category disagreeing with its status
- **THEN** each check SHALL find a documented number of violating rows

#### Scenario: An identity field carries formatting variants

- **WHEN** the assigned-identity field is aggregated without normalising case and surrounding whitespace
- **THEN** a single individual SHALL be split across multiple groups
- **AND** the concentration finding SHALL be silently understated rather than producing an error

#### Scenario: The variant defect is preserved under the address representation

- **WHEN** identities are represented as addresses
- **THEN** the same individual SHALL still appear under multiple spellings differing only in case or surrounding whitespace
- **AND** the documented count of raw groups collapsing to normalised groups SHALL be recorded for the address form
