## ADDED Requirements

### Requirement: OpenSpec scope stays at plugin-governance level
仓库 SHALL 使用 OpenSpec 描述插件代码规范、目录归属、prompt 边界和维护要求。OpenSpec 内容 SHALL NOT 成为 P0-P8 运行时执行流程或 `spec.yaml`、`plan.yaml`、`delivery/` 等运行时产物的主定义来源。

#### Scenario: Reader looks for plugin rules
- **WHEN** a contributor opens `openspec/specs/plugin-governance/spec.md`
- **THEN** 贡献者可以直接识别插件治理规则，而不需要先阅读运行时编排 prompt

#### Scenario: Reader looks for pipeline execution details
- **WHEN** a contributor needs the actual orchestration flow or artifact semantics
- **THEN** 文档会把他们引导到插件 prompt 和实现文件，而不是把 OpenSpec 当作运行时事实来源

### Requirement: Plugin surfaces are explicitly discoverable
仓库 SHALL 明确记录贡献者需要维护的插件关键表面，包括插件元数据、顶层 skill 入口、sub-agent prompt、编排支撑代码，以及保护状态迁移的测试。

#### Scenario: Contributor needs the plugin entrypoints
- **WHEN** a contributor needs to locate the plugin's external entrypoints
- **THEN** 文档列出 `plugins/homework-pipeline/.claude-plugin/plugin.json` 和 `plugins/homework-pipeline/skills/hw/SKILL.md`

#### Scenario: Contributor needs the internal control surfaces
- **WHEN** a contributor needs to locate the plugin's internal behavior definitions
- **THEN** 文档列出 `plugins/homework-pipeline/.claude/agents/` 和 `plugins/homework-pipeline/.homework/orchestrator_state.py`

### Requirement: Governance docs preserve role boundaries
仓库 SHALL 按职责与边界描述每个插件表面，使贡献者可以区分哪些文件定义用户入口、编排策略、sub-agent 行为和状态持久化，而不是只能从阶段性 prompt 叙述里反推。

#### Scenario: Contributor changes an agent prompt
- **WHEN** a contributor edits a file under `plugins/homework-pipeline/.claude/agents/`
- **THEN** 治理文档将该目录描述为 sub-agent 行为与交接契约，而不是插件元数据或状态持久化

#### Scenario: Contributor changes orchestration state code
- **WHEN** a contributor edits `plugins/homework-pipeline/.homework/orchestrator_state.py`
- **THEN** 治理文档将该文件描述为持久化状态与阶段迁移表面

### Requirement: Spec-affecting plugin changes update governance docs together
任何会改变插件元数据、入口点、agent 职责边界或状态迁移职责的变更 SHALL 在同一个 change 中同步更新对应的 OpenSpec spec 以及相关的贡献者文档。

#### Scenario: Plugin contract changes
- **WHEN** a contributor changes plugin-facing behavior such as the primary skill entrypoint, agent ownership, or state command surface
- **THEN** 同一个 change 包含反映新契约的 OpenSpec 更新

#### Scenario: Runtime-only change
- **WHEN** a contributor changes retry logic or validation details inside the execution pipeline without changing plugin-facing contracts
- **THEN** 他们可以只更新实现文档和测试，而不扩大 OpenSpec 的治理范围
