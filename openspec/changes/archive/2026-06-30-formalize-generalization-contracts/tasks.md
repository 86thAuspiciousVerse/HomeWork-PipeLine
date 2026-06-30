## 1. Runtime Contract Surface

- [x] 1.1 Audit current P0-P4 artifact fields in `spec-extractor`, `resource-planner`, `adjudicator`, and `plan-selector` prompts and identify duplicate or conflicting contract wording.
- [x] 1.2 Add a plugin-owned artifact contract module or equivalent validator surface for `spec.yaml`, `resource_plan.yaml`, `verifiability_report.yaml`, and `plan.yaml` focused on generic fields and cross-file references.
- [x] 1.3 Validate that contract fields cover constraints, deliverables, resources, closure, verification tier, evidence expectation, degradation attempts, breakpoints, and source references without scenario-specific schema fields.

## 2. P0-P4 Prompt Contract Updates

- [x] 2.1 Update `spec-extractor.md` so constraint extraction explicitly preserves hard/soft constraints, deliverables, missing signals, verification expectations, and source references in scenario-neutral terms.
- [x] 2.2 Update `resource-planner.md` so resource closure and human supply records consistently include rationale, obtain steps, closure status, and source references.
- [x] 2.3 Update `adjudicator.md` so the degradation ladder records machine-verifiable, language-equivalent, `default_trade`, and `supply_halt` decisions with evidence expectations and `downgrade_attempts`.
- [x] 2.4 Update `plan-selector.md` so DAG nodes are derived from extracted contracts and include tier, acceptance text, evidence expectations, failure policy, and source references without domain-template selection.

## 3. Contract Validation Tests

- [x] 3.1 Add focused tests for valid synthetic P0-P4 artifacts that exercise generic required fields and cross-artifact references.
- [x] 3.2 Add focused tests that reject missing required fields in constraints, resources, verifiability records, and plan nodes.
- [x] 3.3 Add focused tests that reject scenario-specific control fields or task-family template selectors in the generic contract surface.

## 4. Verification and Documentation

- [x] 4.1 Run the existing orchestrator smoke tests and the new contract validation tests.
- [x] 4.2 Update contributor-facing documentation to explain that OpenSpec describes plugin behavior while runtime artifact schemas remain owned by the plugin implementation.
