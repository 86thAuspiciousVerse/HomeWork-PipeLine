## Why

当前泛化能力仍过度依赖 prompt 中的自然语言约定，关键产物是否稳定抽取约束、资源、验收点和降级原因缺少工程契约。现在需要先把 P0-P4 的“约束抽取 + 语言化路径降级”正式化为插件行为要求，同时保持架构不绑定任何具体课程、领域或题型。

## What Changes

- Introduce a generic P0-P4 generalization contract for extracting assignment constraints, deliverables, resources, verification boundaries, evidence expectations, and source references into structured runtime artifacts.
- Require verifiability decisions to follow a general degradation ladder: machine-verifiable evidence first, language-equivalent acceptance when machine checks are insufficient, then explicit `default_trade` or `supply_halt` candidates when neither can close the task.
- Require planning to derive DAG shape from extracted constraints, resource closure, and verifiability results instead of from scenario-specific templates, domain packages, or hard-coded task families.
- Add a plugin-owned validator surface for the generic P0-P4 artifacts, focused on required fields and cross-artifact references.
- Avoid adding any architecture-level field, runner, validator, or prompt branch that is specific to one assignment scenario such as GIS, API collection, dashboarding, time series, or report-only tasks.
- Leave strict breakpoint provenance, final audit trail hardening, and golden semantic regression fixtures to a follow-up change.

## Capabilities

### New Capabilities

- `generalization-contracts`: Defines the plugin-level behavior required for scenario-neutral constraint extraction, verifiability classification, language-equivalent degradation, and contract-driven planning.

### Modified Capabilities

- None.

## Impact

- Affected plugin surfaces include P0-P4 sub-agent prompts, runtime artifact schemas or validators, plan selection behavior, and focused contract tests under the homework pipeline plugin.
- No new third-party dependency is required by the proposal itself; implementation may use existing validation tooling or add minimal schema helpers if needed.
- OpenSpec remains a plugin governance and behavior contract layer. It does not become the runtime source of truth for `spec.yaml`, `resource_plan.yaml`, `verifiability_report.yaml`, `plan.yaml`, or delivery artifacts.
