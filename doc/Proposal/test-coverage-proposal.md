# HomeWork-PipeLine 测试覆盖提案

## 背景

当前项目已经有一条基础 smoke test，覆盖 `create-run`、`classify-breakpoints`、`commit-phase` 的 happy path，以及 `supply_halt` 暂停后禁止提交的场景。这能证明状态机最小链路可用，但还不足以支撑一个持续演进的管线项目。

HomeWork-PipeLine 的核心风险不只是代码异常，而是阶段契约漂移：agent 输出字段变形、断点信息不完整、计划 DAG 无法被执行器消费、facts 引用不存在的产物、packer 打包了不可信内容。这些风险需要通过分层测试覆盖，而不是只依赖端到端人工试跑。

本提案目标是建立一套适合当前原型阶段的测试覆盖路线：先稳住确定性状态机和 artifact 契约，再覆盖测试用例语义回归，最后逐步加入执行与打包层的集成测试。

测试边界需要明确：不建设也不测试固定“验证原子库”和“领域包”。P5/P6 仍由 LLM 现场生成检查脚本；测试关注现场检查是否留下足够证据、是否可被 auditor 独立复审、是否能在失败时诚实阻断。

## 测试目标

测试体系应保证以下事实长期成立：

1. 状态机在创建、进入阶段、提交、暂停、恢复、终态推进时行为稳定。
2. `supply_halt`、`sense_default_trade`、`manual_nodes` 等关键断点数据不会丢字段。
3. 每阶段 artifact 的 schema 可被机器校验，字段漂移会被及时挡下。
4. 现有课程测试用例能稳定抽取关键约束、资源需求、交付物和断点。
5. P5/P6 的执行、审计、失败降级和补给追加有可回归的最小样例。
6. P7/P8 不会生成引用不存在文件的文档，也不会把密钥或假产物打包进 delivery。
7. 修改 prompt、schema 或状态机后，可以快速发现破坏性变更。
8. 现场生成的检查脚本有明确意图、输入、实测值、PASS/FAIL 规则和执行输出。

## 当前覆盖现状

### 已覆盖

- 创建 run 目录和初始 `state.yaml`。
- `classify-breakpoints` 对无 `supply_halt` 的正常分类。
- `sense_default_trade` 写入 state。
- `commit-phase` 推进到下一阶段。
- `supply_halt` 非空时进入 `PAUSED`。
- 阶段 `PAUSED` 时禁止提交。

### 未覆盖

- `mark-entering` 的幂等行为。
- `resolve-supply-halt` 的逐条补给和全量恢复。
- `add-supply-halt` 对 P5/P6 新断点的追加行为。
- `manual-resolve-node` 对手动补完节点的登记。
- 多个 run 的 run_id 递增和隔离。
- 异常输入：未知阶段、缺失报告、非法 trigger、空字段、重复断点 id。
- artifact schema 校验。
- agent prompt 中声明的输入输出契约。
- 两个 `test-cases` 的语义回归。
- P5-P8 的最小集成流程。
- delivery 打包前后的完整性和安全性检查。
- P5/P6 现场检查报告格式。

## 测试分层

### L0：纯函数与模型单元测试

覆盖 `orchestrator_state.py` 中不依赖外部服务的确定性逻辑。

建议新增测试文件：

- `tests/test_state_lifecycle.py`
- `tests/test_breakpoints.py`
- `tests/test_manual_nodes.py`
- `tests/test_cli_errors.py`

重点用例：

- `create_run` 生成完整目录结构：`artifacts/`、`execution/traces/`、`code/`、`logs/`。
- 同一天多次 `create_run` 生成 `run_YYYYMMDD-001`、`run_YYYYMMDD-002`。
- `mark_entering` 对 `PENDING/RUNNING` 阶段可重入，对 `COMPLETED` 阶段不回退。
- `commit_phase` 只在合法阶段推进，未知阶段报错。
- 提交最后阶段后能进入 `COMPLETED`。
- `classify_breakpoints` 能保留 `why`、`obtain_steps`、`when_provided`。
- 非法 trigger 自动降级或报错的行为被固定下来。
- `resolve_supply_halt` 对单条断点只 resolve 当前项，多条全 resolved 后才恢复 `ENTERING`。
- `add_supply_halt_item` 会设置 `phase_status=PAUSED` 和 `auto_mode=scaffold_with_breakpoints`。
- `manual_resolve_node` 会写入 `EXECUTOR.manual_nodes`，并保留 `node/source/resolved_at`。

### L1：CLI 契约测试

CLI 是主 agent 实际调用状态机的入口，因此需要把命令行行为固定下来。

建议覆盖命令：

- `create-run`
- `get-run-info`
- `mark-entering`
- `classify-breakpoints`
- `commit-phase`
- `resolve-supply-halt`
- `add-supply-halt`
- `manual-resolve-node`
- `show`

重点断言：

- 正常命令返回 exit code 0。
- 参数缺失返回 exit code 2。
- stdout 是合法 JSON。
- JSON 摘要包含 `run_id/current_phase/phase_status/auto_mode/run_root/state_path`。
- `add-supply-halt` 能从 stdin JSON 读取复杂中文字段。
- CLI 不打印真实 secret，只保存 `value_ref`。

### L2：Artifact Schema 测试

这是提高长期可维护性的关键层。建议先建立 `homework_pipeline/schemas/` 或 `.homework/schemas.py`，用 Pydantic 定义核心 artifact。

建议新增测试文件：

- `tests/test_artifact_schemas.py`
- `tests/fixtures/artifacts/valid/*.yaml`
- `tests/fixtures/artifacts/invalid/*.yaml`

优先覆盖 schema：

- `spec.yaml`
- `resource_plan.yaml`
- `verifiability_report.yaml`
- `plan.yaml`
- `red_green_checklist.yaml`
- `facts.json`

重点断言：

- 有效 fixture 能通过。
- 缺少关键字段会失败。
- `supply_halt` 缺少 `obtain_steps` 会失败。
- `plan.final_dag.nodes[].name` 唯一。
- `plan.final_dag.edges` 不能引用不存在的 node。
- `facts.artifacts[].path` 在非 `pending_supply` 时必须可解析。
- `PROVENANCE` 的 origin 只能是允许枚举值。

### L3：Agent Prompt 契约测试

虽然 agent prompt 不是普通代码，但它们是运行时协议的一部分。应做轻量 lint，避免无意删除关键硬约束。

建议新增测试文件：

- `tests/test_agent_prompt_contracts.py`

重点断言：

- 每个 agent 文件都有 frontmatter：`name`、`description`、`tools`。
- `spec-extractor` 明确输出 `spec.yaml`。
- `resource-planner` 明确要求 `obtain_steps` 和 `why`。
- `adjudicator` 明确输出 `breakpoints_summary.supply_halt` 的必填字段。
- `plan-selector` 明确输出 `final_dag.nodes` 和 `acceptance`。
- `hw-orchestrator` 明确保存 `execution/traces/<node>__attempt<n>.txt`。
- `hw-orchestrator` 明确现场检查需要记录检查意图、输入、实测值、PASS/FAIL 规则和输出。
- `auditor` 明确输出 `red_green_checklist.yaml` 和 `audit_report.md`。
- `auditor` 明确不能直接复用 P5 的 PASS，必须独立复审证据或重写检查。
- `facts-deriver` 明确 `facts.json` 是单一事实源。
- `packer` 明确不写 secret、不伪造缺失文件。

这类测试不是验证 prompt 质量，而是防止关键协议被误删。

### L4：课程测试用例黄金回归

现有 `test-cases` 是泛化能力最有价值的资产。建议把它们转化为黄金回归测试，不依赖真实 LLM 调用，而是用固定 fixture 或半自动快照验证关键语义。

建议目录结构：

```text
tests/fixtures/golden/
├── air_quality/
│   ├── expected_constraints.yaml
│   ├── expected_resources.yaml
│   ├── expected_verifiability.yaml
│   └── expected_plan_shape.yaml
└── transit_network/
    ├── expected_constraints.yaml
    ├── expected_resources.yaml
    ├── expected_verifiability.yaml
    └── expected_plan_shape.yaml
```

空气质量预测应断言：

- 识别“宽表转长表”。
- 识别“缺失值前向填充”和“连续缺失 >6h 标记”。
- 识别“严禁 `train_test_split` 随机切分”。
- 识别“按时间顺序 70/15/15 切分”。
- 识别交付物：自包含 HTML Dashboard、FastAPI `app.py`、`requirements.txt`。
- 不应生成 API Key 型 `supply_halt`。

公交网络分析应断言：

- 识别高德 API Key 是人工补给资源。
- `supply_halt.kind=api_key`。
- `obtain_steps` 非空。
- 识别 GCJ-02 到 WGS-84 坐标转换。
- 识别 NetworkX Space-P 模型。
- 识别交付物：HTML、CSV、GEXF。

### L5：P5-P8 最小集成测试

完整调用 LLM 做端到端测试成本高、波动大，不适合作为默认 CI。建议先做“合成 artifact 集成测试”：手写最小 `spec/resource_plan/verifiability_report/plan`，再验证后续阶段可消费。

这层测试不要求存在预置检查原子。对于每个合成场景，只要求 P5/P6 的现场检查产出满足统一证据格式，并且 auditor 能基于磁盘事实独立得出结论。

建议新增集成场景：

#### 场景 A：全自动本地数据

输入：

- 一个小 CSV fixture。
- 一个 `plan.yaml`，包含 `etl`、`analyze`、`render_html` 三个 node。
- 简单可执行代码 fixture 或 stub executor。

断言：

- P5 trace 写入。
- P5 trace 中包含现场检查意图、脚本或命令、输入、实测值和 PASS/FAIL 规则。
- P6 checklist 全 green。
- P6 不是直接复制 P5 结论，而是保留独立复审 evidence。
- P7 facts 记录真实文件 path、sha256、size。
- P8 delivery 包含 code/doc/traces/_meta。

#### 场景 B：外部 API Key 缺失

输入：

- `resource_plan.yaml` 声明 `api_key_required`。
- `verifiability_report.yaml` 产生 `supply_halt`。

断言：

- P3 后 `state.yaml` 进入 `PAUSED`。
- 生成用户可读补给清单。
- 未伪造 API 数据。
- resolve 后可继续进入下一阶段。

#### 场景 C：默认降级

输入：

- 一个允许 `A(default_trade)` 的 visual node。

断言：

- 默认产物被显式标记为 `source=default_trade`。
- P7 计算 AI 占比时扣除 default_trade。
- P8 `PROVENANCE.yaml` 标记 `ai_generated_default_trade`。

#### 场景 D：缺失产物阻断打包

输入：

- `facts.json` 引用不存在的交付物。

断言：

- P7 或 P8 报错。
- `delivery/<course>/_meta/deliverable_gaps.yaml` 被写入。
- 不标记 `COMPLETED`。

### L6：安全与交付完整性测试

这部分应尽早加入，因为作业管线会处理 API Key、数据和最终 delivery。

重点用例：

- delivery 中不包含 `.env`、真实 API Key、token 字段。
- 代码中的 `AMAP_API_KEY = "real-key"` 会被替换为 `os.environ.get(...)` 或被阻断。
- `PROVENANCE.yaml` 必须存在。
- `REPRODUCE.md` 必须包含 Python 版本和依赖安装命令。
- `checksums.sha256` 中的文件都真实存在。
- `_meta` 中必须包含 `spec.yaml`、`resource_plan.yaml`、`verifiability_report.yaml`、`plan.yaml`。

## 测试数据策略

### 使用小而真的 fixture

测试数据不应太大，但要真实覆盖格式陷阱：

- 空气质量 CSV 应保留宽表结构、多个 pollutant、多个站点列、缺失值。
- 公交网络 fixture 应包含站点重复、线路 path、GCJ-02 坐标、环线样例。
- HTML fixture 应包含 Plotly 自包含和非自包含两种。
- requirements fixture 应包含锁定和未锁定两种。

### 避免默认测试访问网络

默认 CI 不应依赖 Tavily、WebSearch、真实 API 或 pip 网络安装。所有外部依赖测试分为：

- 默认离线测试：使用 fixture 和 mock 响应。
- 可选 live 测试：显式设置环境变量后才运行，例如 `RUN_LIVE_API_TESTS=1`。

### 固定时间与路径

`run_id` 使用日期生成。测试中应通过 monkeypatch 或 helper 固定时间，避免日期导致 snapshot 波动。

Windows/Linux 路径差异应统一走 `Path`，snapshot 中尽量使用 run 根相对路径。

## 覆盖率指标

短期不要追求百分比覆盖率，而应追求风险覆盖率。建议分阶段设定目标：

### 第一阶段

- 状态机核心函数覆盖率达到 80% 以上。
- 所有 CLI 命令至少有一个 happy path 和一个 error path。
- `supply_halt` 数据字段完整性有专门测试。

### 第二阶段

- 核心 artifact schema 都有 valid/invalid fixture。
- 两个 test-cases 都有黄金回归断言。
- agent prompt contract 测试覆盖所有 agent 文件。
- P5/P6 现场检查报告格式有 fixture 覆盖。

### 第三阶段

- P5-P8 至少有 4 个合成集成场景。
- delivery 完整性和 secret 防泄漏测试进入默认 CI。
- 每个新增 bug 修复都补对应回归测试。

## CI 建议

建议默认 CI 分三档：

```bash
uv run pytest -q
uv run ruff check .
uv run python -m unittest tests.test_orchestrator_state_smoke -v
```

后续可扩展 marker：

```bash
uv run pytest -q -m "not live"
uv run pytest -q -m "integration"
uv run pytest -q -m "live"
```

其中：

- `unit`：默认必跑，纯本地、快速。
- `contract`：schema 和 prompt contract，默认必跑。
- `golden`：课程黄金回归，默认必跑。
- `integration`：合成 P5-P8，可在 PR 跑。
- `live`：真实外部 API 和网络探针，只手动触发。

## 推荐实施路线

### 第一批：补状态机确定性测试

优先新增：

- `test_mark_entering_idempotent`
- `test_resolve_supply_halt_partial_then_all`
- `test_add_supply_halt_from_executor_pauses`
- `test_manual_resolve_node_records_source`
- `test_multiple_runs_increment_ids`
- `test_cli_argument_errors`

这批测试成本最低，能快速提高信心。

### 第二批：建立 artifact schema 测试

先定义最小 schema，不追求一次覆盖所有字段。优先保证：

- `supply_halt` 必填字段。
- `plan.final_dag` 拓扑引用。
- `facts.artifacts` 路径存在性。
- `PROVENANCE.origin` 枚举。

### 第三批：建立黄金回归

基于现有两个课程用例，手写 expected fixture。先断言关键事实，不要求完整 snapshot 一字不差。

### 第四批：P5-P8 合成集成

通过手工 artifact 和小 fixture 模拟执行后半段，优先测试 facts 和 packer 的“不能造假”能力。

这批测试应验证现场检查协议，而不是验证某个固定检查函数库。

### 第五批：安全和 live 测试

加入 secret scanner、外部 API live marker、网络探针 fixture，并确保默认 CI 不依赖外部网络。

## 近期最小可行动作

建议下一步直接实现以下测试：

1. 扩展 `tests/test_orchestrator_state_smoke.py` 或拆出 `tests/test_breakpoints.py`，覆盖 `resolve_supply_halt`、`add_supply_halt`、`manual_resolve_node`。
2. 新增 `tests/test_agent_prompt_contracts.py`，用文本断言保护 agent prompt 的关键契约。
3. 新增 `tests/fixtures/golden/`，先为两个课程用例写关键事实 fixture。
4. 新增一个 `validate-artifact` 原型，只校验 `verifiability_report.breakpoints_summary.supply_halt` 字段完整性。

这四项可以在不引入复杂外部依赖的情况下，显著提高当前原型的测试覆盖质量。
