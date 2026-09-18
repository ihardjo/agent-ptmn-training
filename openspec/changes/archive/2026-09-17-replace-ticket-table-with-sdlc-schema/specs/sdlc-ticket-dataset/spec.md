## Purpose

Defines the shape and the known properties of the workshop's training table: its schema, the language rule governing its text, the findings and defects deliberately planted in it, and the gaps deliberately maintained in it. Downstream evaluation work derives ground truth from these properties, so they are a contract rather than an accident of generation.

## ADDED Requirements

### Requirement: The dataset spans planned and unplanned work in one table

The dataset SHALL record software delivery work and unplanned operational work in a single table, discriminated by a work-type field. Questions about the split between planned and unplanned effort SHALL be answerable without joining another source.

#### Scenario: Work types coexist

- **WHEN** the distinct work types in the dataset are listed
- **THEN** they SHALL include both delivery types (Bug, Story, Task) and operational types (Incident, Service Request, Change)

#### Scenario: Capacity split is answerable

- **WHEN** a consumer asks what share of effort went to unplanned rather than planned work
- **THEN** the dataset SHALL contain sufficient fields to compute it, using the work-type field and the sprint field together
- **AND** unplanned work SHALL be distinguishable by carrying no sprint

### Requirement: Column naming is vendor-neutral with a documented hostile minority

Column names SHALL NOT reference any specific issue-tracking product. The majority SHALL be lower-case identifiers requiring no escaping. Exactly three columns, representing custom fields carried over from a source system, SHALL require escaping because they contain spaces, parentheses, or a slash.

#### Scenario: The conformed core needs no escaping

- **WHEN** the agent queries any column outside the documented hostile minority
- **THEN** the identifier SHALL be usable without backticks

#### Scenario: The carried-over fields need escaping

- **WHEN** the agent queries a carried-over custom field
- **THEN** that identifier SHALL require backtick escaping
- **AND** an unescaped reference SHALL fail to parse rather than returning wrong results

#### Scenario: No product name appears in the schema

- **WHEN** the table and column names are inspected
- **THEN** no name SHALL contain a vendor or product identifier

### Requirement: Text language follows provenance

Field text SHALL indicate who produced it. Values a tracking tool would generate — work type, status, status category, priority, severity, resolution, sprint, component — SHALL be in English. Values a person would type — the title and the root-cause classification — SHALL be in Bahasa Indonesia.

#### Scenario: Enumerated values are English

- **WHEN** the distinct values of a tool-generated field are listed
- **THEN** they SHALL be English terms

#### Scenario: Human-entered text is Bahasa Indonesia

- **WHEN** ticket titles are read
- **THEN** they SHALL be in Bahasa Indonesia

### Requirement: Elapsed time is decomposable into waiting and working

The dataset SHALL carry separate timestamps for creation, work start, and closure, so that time spent waiting before work began is measurable separately from time spent working. A single end-to-end duration SHALL NOT be the only available measure.

#### Scenario: Wait and cycle time are separately computable

- **WHEN** a consumer computes how long work takes
- **THEN** the interval from creation to start and the interval from start to closure SHALL each be computable
- **AND** the two SHALL be materially different in the dataset, such that reporting only one misrepresents the other

#### Scenario: Timestamps are absent for work not yet at that stage

- **WHEN** a ticket has not started, or has not closed
- **THEN** the corresponding timestamp SHALL be absent rather than defaulted
- **AND** any duration derived from an absent timestamp SHALL also be absent

### Requirement: The dataset contains planted, documented findings

The dataset SHALL contain a documented set of non-obvious patterns that a competent analyst can discover. Each planted finding SHALL be verifiable by query, and the verifying query SHALL be recorded alongside the dataset definition.

#### Scenario: A planted finding is verifiable

- **WHEN** the verifying query for a planted finding is run against the dataset
- **THEN** the finding SHALL be present at the documented magnitude

#### Scenario: A naive query misrepresents a planted finding

- **WHEN** a consumer asks how long work takes and is answered from end-to-end duration alone
- **THEN** the answer SHALL materially misrepresent the dataset, because waiting dominates working
- **AND** the correct characterisation SHALL require distinguishing the two intervals

#### Scenario: Concentration of work on one individual is present

- **WHEN** closures are aggregated by the person assigned
- **THEN** a single individual SHALL account for a documented and disproportionate share
- **AND** that share SHALL be reportable in aggregate without naming the individual

### Requirement: The dataset contains planted, documented defects

The dataset SHALL contain a documented set of data-quality defects, so that validation and stewardship work has something real to find. Each defect class SHALL have a documented row count and a detecting query.

#### Scenario: Chronologically impossible rows exist

- **WHEN** rows are checked for closure preceding creation
- **THEN** a documented number of violating rows SHALL be found

#### Scenario: Cross-field inconsistencies exist

- **WHEN** rows are checked for a duration recorded against work that has not closed, for closure without a resolution, or for a status category disagreeing with its status
- **THEN** each check SHALL find a documented number of violating rows

#### Scenario: An identity field carries formatting variants

- **WHEN** the person-assigned field is aggregated without normalising case and surrounding whitespace
- **THEN** a single individual SHALL be split across multiple groups
- **AND** the concentration finding SHALL be silently understated rather than producing an error

### Requirement: The dataset maintains deliberate gaps

The dataset SHALL NOT contain fields for resolution targets, team or squad membership, release or version, cost, or free-text narrative description. These absences are a property of the dataset, so that questions with no answer in the data exist by design and are not an oversight to be corrected.

#### Scenario: A plausible question has no answer in the data

- **WHEN** a consumer asks which team resolves work fastest, what a class of work cost, or the bug rate per release
- **THEN** the dataset SHALL contain no field from which to answer
- **AND** the correct response SHALL be to report the gap rather than to substitute a proxy

#### Scenario: Resolution targets are absent

- **WHEN** the dataset is inspected for a target, threshold, or breach indicator
- **THEN** none SHALL be present
- **AND** any adherence question SHALL require the target to be supplied from outside the dataset

#### Scenario: Narrative description is absent while classification is present

- **WHEN** a consumer asks what the top root causes are
- **THEN** the question SHALL be answerable from the root-cause classification
- **AND** a request to explain the narrative of one specific ticket SHALL NOT be answerable
