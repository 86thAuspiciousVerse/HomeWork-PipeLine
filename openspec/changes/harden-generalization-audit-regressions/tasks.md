## 1. Breakpoint Hardening

- [x] 1.1 Add validation helpers for complete `supply_halt` entries, including id, stage id, kind, reason, obtain steps, resume instruction, closure status, and source/provenance reference.
- [x] 1.2 Apply `supply_halt` validation in `classify_breakpoints` before a run is paused.
- [x] 1.3 Apply `supply_halt` validation in late `add_supply_halt_item` paths used by P5/P6.
- [x] 1.4 Add tests that reject incomplete supply items and accept complete user-actionable supply items.

## 2. Default Trade and Provenance

- [x] 2.1 Add validation helpers for `default_trade` metadata, including relaxed requirement, fallback reason, evidence source, and non-real-output marker.
- [x] 2.2 Preserve default fallback metadata through state, facts, or provenance output so delivery cannot present default output as real execution evidence.
- [x] 2.3 Preserve human-provided supply resolution as a value reference without storing secret plaintext.
- [x] 2.4 Add tests for default fallback marking and human-supply provenance.

## 3. Fixture Expectations

- [x] 3.1 Add machine-readable semantic expectations for `test-cases/空气质量预测`, covering local data closure, time-aware constraints, required deliverables, and no API-key `supply_halt`.
- [x] 3.2 Add machine-readable semantic expectations for `test-cases/公交网络分析`, covering external API-key supply and CSV/GEXF/HTML deliverables traceable to plan nodes.
- [x] 3.3 Add normalization helpers that compare generated or fixture P0-P4 artifacts to expected facts without exact YAML text matching.

## 4. Regression Tests

- [x] 4.1 Add semantic regression tests for the air-quality fixture expectations.
- [x] 4.2 Add semantic regression tests for the transit-network fixture expectations.
- [x] 4.3 Add anti-template tests that reject scenario-specific planner controls while allowing domain words in course content and rationale.
- [x] 4.4 Run existing orchestrator smoke tests plus the new audit and semantic regression tests.

## 5. Documentation

- [x] 5.1 Document that this change depends on the generic P0-P4 contract from `formalize-generalization-contracts`.
- [x] 5.2 Document where provenance or semantic expectation files live and how contributors update them when fixture behavior intentionally changes.
