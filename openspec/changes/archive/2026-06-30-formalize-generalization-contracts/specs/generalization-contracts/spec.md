## ADDED Requirements

### Requirement: Constraint extraction remains scenario-neutral
The plugin SHALL extract assignment requirements into scenario-neutral runtime facts covering constraints, deliverables, resources, verification expectations, missing signals, and source references. The plugin MUST NOT introduce architecture-level fields, prompt branches, validators, or planning controls whose semantics only apply to a specific assignment family.

#### Scenario: Mixed-domain assignment is extracted through generic facts
- **WHEN** a course document mentions data cleaning, external APIs, visual reports, services, or written analysis
- **THEN** the extracted artifacts represent them as generic constraints, deliverables, resources, stages, and evidence expectations rather than selecting a domain package or hard-coded task template

#### Scenario: Uncertain requirement is handled conservatively
- **WHEN** the source document implies a hard requirement but lacks enough detail to make the requirement fully precise
- **THEN** the extracted artifact records the uncertainty in missing signals and preserves the stricter plausible constraint instead of silently dropping it

### Requirement: Resource closure and verifiability are explicit
The plugin SHALL classify every deliverable stage by resource closure and verification boundary before planning. Each classification MUST include a rationale and MUST reference the extracted constraint, deliverable stage, or resource record that caused the decision.

#### Scenario: Required external credential is outside the closure
- **WHEN** a stage needs an API key, account, credential file, payment, identity verification, phone verification, or other human-only resource
- **THEN** the resource and verifiability artifacts classify the stage as outside the AI execution closure and provide the data needed to create a `supply_halt`

#### Scenario: Local artifact has deterministic evidence
- **WHEN** a stage can be checked through files, commands, service probes, checksums, table contents, or other deterministic observations
- **THEN** the verifiability artifact classifies the stage as machine-verifiable and records the evidence that P5 or P6 must collect

### Requirement: Language-equivalent degradation is attempted before fallback
The plugin SHALL attempt language-equivalent degradation for stages that cannot be directly machine-verified before choosing `default_trade` or `supply_halt`. Each attempt MUST record the proposed restatement, source, outcome, evidence expectation, and rationale.

#### Scenario: Direct machine verification is unavailable but a rubric can close the task
- **WHEN** a stage cannot produce deterministic pass/fail evidence but can be judged against explicit textual, tabular, code-review, or rubric criteria
- **THEN** the stage is degraded to a language-equivalent verification path instead of immediately becoming `default_trade` or `supply_halt`

#### Scenario: No language-equivalent path remains credible
- **WHEN** the degradation budget is exhausted and no restatement can produce a credible verification path
- **THEN** the plugin records the failed degradation attempts and chooses either a permitted `default_trade` or a `supply_halt` when real external input is required

### Requirement: Planning derives DAG shape from extracted contracts
The plugin SHALL derive the final DAG from extracted constraints, resource closure, verifiability results, and dependency relationships. The planner MUST NOT select DAG nodes by matching a fixed domain template or task-family package.

#### Scenario: Two assignments share a surface topic but differ in constraints
- **WHEN** two course documents use similar domain words but require different deliverables, resources, or verification boundaries
- **THEN** the planner creates DAG nodes from the extracted facts for each document rather than reusing a prebuilt topic template

#### Scenario: Plan node exposes evidence expectations
- **WHEN** a DAG node is created
- **THEN** the node includes its verification tier, human-readable acceptance criterion, expected evidence or invariants where available, and references needed for later audit
