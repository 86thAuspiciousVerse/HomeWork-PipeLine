## Why

通用泛化契约稳定后，还需要让降级、默认产物、人工补给和语义回归形成可审计闭环。否则管线虽然能分类和规划，但仍可能把近似默认产物误当真实结果，或在 prompt 修改后悄悄丢掉关键语义行为。

## What Changes

- Harden `default_trade` and `supply_halt` handling so fallback output, pending supply, and human-provided resources carry complete reason, resume instruction, closure status, and provenance references.
- Add validation that rejects incomplete supply breakpoints before the run is paused and presented to the user.
- Add validation that requires default artifacts to be visibly marked as approximate fallback output rather than real execution evidence.
- Add semantic regression fixtures for the existing air-quality and transit-network assignments, asserting key P0-P4 facts without comparing exact YAML wording.
- Add tests that prevent scenario-specific control fields or hidden task-family templates from entering the generalization path.
- Keep this change focused on auditability and regression protection; it does not introduce domain packages, runner expansion, or a verifier atom library.

## Capabilities

### New Capabilities

- `generalization-audit-regressions`: Defines provenance hardening, breakpoint completeness, default-output marking, and semantic regression safeguards for the generalization workflow.

### Modified Capabilities

- None.

## Impact

- Affected plugin surfaces include `orchestrator_state.py`, breakpoint serialization, default artifact metadata, provenance or facts output, and regression tests under `tests/` or fixture expectation files.
- This change is intended to follow `formalize-generalization-contracts`; it assumes P0-P4 artifacts already expose generic contract fields and source references.
- OpenSpec remains a behavior contract. Runtime artifact schema details stay in plugin implementation and tests.
