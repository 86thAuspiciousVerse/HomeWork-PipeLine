## ADDED Requirements

### Requirement: Supply breakpoints are complete before pause
The plugin SHALL reject `supply_halt` breakpoint entries that do not contain enough information for a user to understand, obtain, and register the missing resource. Each accepted `supply_halt` entry MUST include stable id, stage id, kind, reason, obtain steps, resume instruction, closure status, and source or provenance reference.

#### Scenario: Incomplete supply item is produced
- **WHEN** breakpoint classification or later execution attempts to add a `supply_halt` item without obtain steps or resume instruction
- **THEN** the plugin rejects the item before presenting a paused run to the user

#### Scenario: Complete supply item pauses the run
- **WHEN** a stage truly requires an external credential, account, dataset, or human-only resource and all required supply fields are present
- **THEN** the plugin records the item, pauses the run, and preserves the user-facing reason and recovery instruction

### Requirement: Default trade output is marked as fallback
The plugin SHALL mark every default artifact or default path as fallback output. The metadata MUST identify the relaxed requirement, fallback reason, evidence source, and why the output is not equivalent to real execution evidence.

#### Scenario: Default artifact enters delivery
- **WHEN** a permitted `default_trade` artifact is generated and later included in facts or delivery metadata
- **THEN** the plugin marks it as fallback output and prevents it from being represented as a real measured or externally verified result

#### Scenario: Default trade lacks rationale
- **WHEN** a default artifact lacks the relaxed requirement or fallback rationale
- **THEN** validation fails before the artifact is treated as complete

### Requirement: Provenance distinguishes completion sources
The plugin SHALL distinguish AI-executed output, language-equivalent verification, default fallback, human-provided input, pending supply, manually completed work, and unresolved work in its auditable state or final provenance output.

#### Scenario: Human-provided value resolves supply
- **WHEN** a user resolves a `supply_halt` item by registering an environment variable, file path, or other value reference
- **THEN** provenance records the item as human-provided without storing secret plaintext

#### Scenario: Audit reads final facts
- **WHEN** the final facts or provenance output is inspected
- **THEN** each listed artifact can be classified by completion source without reading the full execution trace

### Requirement: Semantic regressions protect representative P0-P4 behavior
The repository SHALL include semantic regression coverage for representative assignment fixtures. The tests MUST assert stable facts and cross-artifact consistency rather than full serialized artifact text.

#### Scenario: Air-quality fixture remains closed
- **WHEN** the air-quality fixture is checked against P0-P4 semantic expectations
- **THEN** the tests assert local data closure, time-aware constraints, required deliverables, and absence of API-key `supply_halt`

#### Scenario: Transit-network fixture requires external supply
- **WHEN** the transit-network fixture is checked against P0-P4 semantic expectations
- **THEN** the tests assert that the external API key is represented as human supply and that CSV, graph, and HTML deliverables remain traceable to plan nodes

### Requirement: Regression tests block hidden scenario templates
The repository SHALL test that the generalization path does not depend on scenario-specific control fields, domain packages, or hidden task-family templates. The tests MUST allow domain words in input content while rejecting architecture controls that make the domain label drive planning.

#### Scenario: Domain label appears only as content
- **WHEN** a fixture contains words such as GIS, dashboard, time series, or API collection in the course requirement
- **THEN** tests allow those words in extracted constraints and rationale but reject them as planner template selectors

#### Scenario: Template selector is introduced
- **WHEN** a runtime artifact or prompt contract adds a field that selects a fixed domain package or hard-coded task-family DAG
- **THEN** the regression suite fails
