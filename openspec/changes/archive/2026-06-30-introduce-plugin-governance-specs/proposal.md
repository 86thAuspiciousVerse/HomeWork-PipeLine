## Why

当前仓库已经有插件代码、prompt 和测试，但治理规则分散在 README、skill prompt 和 agent prompt 里，而且叙述重点偏向运行管线。缺少一层稳定的插件规范，导致贡献者很难快速分辨“插件契约”和“运行时编排细节”的边界。

## What Changes

- 引入 OpenSpec 作为仓库内的插件治理层。
- 新增一个只覆盖插件规范、目录职责、职责边界和同步要求的基础 capability。
- 在 README 中明确 OpenSpec 的作用范围，避免把它误解为 P0-P8 执行管线或运行时产物的规范源。

## Capabilities

### New Capabilities
- `plugin-governance`: 规范插件元数据、入口点、agent/状态代码职责边界，以及哪些变更必须同步更新治理文档

### Modified Capabilities
- None

## Impact

- 新增 `openspec/` 目录和变更提案
- 新增插件治理主 spec
- 更新 README 的文档边界说明
- 不改动现有运行时实现、编排逻辑或产物 schema
