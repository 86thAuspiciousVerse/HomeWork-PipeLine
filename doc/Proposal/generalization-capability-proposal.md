# HomeWork-PipeLine 泛化能力提升提案

## 背景

HomeWork-PipeLine 当前定位是一个开发中的课程作业自动交付管线。现有设计已经具备较清晰的确定性外壳：9 阶段串行推进、`state.yaml` 单一真相源、`supply_halt` 人工补给断点、`default_trade` 降级路径、执行留痕、审计和最终打包。

当前核心优势不是“盲目全自动”，而是先判断哪些约束能被机器验证、哪些只能由语言近似验证、哪些必须人工补给，然后在可验证边界内推进。这一方向是正确的。

主要短板是：大量关键协议仍停留在 agent prompt 的自然语言约定中，例如 `spec.yaml`、`resource_plan.yaml`、`verifiability_report.yaml`、`plan.yaml`、`facts.json` 等产物的结构、字段和质量标准没有完全下沉为可执行 schema 与回归测试。因此，泛化能力目前较依赖模型是否稳定遵守提示词，而不是依赖工程化契约。

## 目标

提高泛化能力的目标不是让管线硬吃所有作业，而是让它在更多任务类型下能稳定完成以下动作：

1. 准确抽取课程约束、资源需求、交付物和关键陷阱。
2. 稳定判断任务是否可闭环验证、是否需要默认降级、是否必须人工补给。
3. 基于任务要求现场生成可执行 DAG，而不是绑定某个固定题型模板或长期维护的领域包。
4. 保留 LLM 现场生成验证脚本的灵活性，同时用结构化验收、独立复审和执行留痕降低不确定性。
5. 对失败、降级、人工补给和默认产物给出可追溯 provenance。
6. 用回归用例持续验证管线行为，避免 prompt 修改造成隐性退化。

## 当前能力判断

### 已经具备的基础

- 状态机外壳明确：P0 到 P8 阶段顺序固定，支持阶段提交、暂停、恢复和终态。
- 断点机制合理：`sense_default_trade` 不停机，`supply_halt` 暂停等待真实补给。
- 执行链路完整：需求抽取、资源规划、可验证性裁决、方案选择、代码执行、审计、事实派生、打包交付均已定义。
- 学术诚信意识较强：默认产物、人工补给、手动补完和 AI 生成占比都有记录设计。
- 测试用例覆盖了两种关键场景：本地数据闭环的空气质量预测，以及依赖外部 API Key 的公交网络分析。

### 当前主要风险

- 关键 artifact schema 未工程化，字段漂移后不容易及时发现。
- P5/P6 的验证能力主要依赖 LLM 现场写脚本，这一方向应保留；当前不足是缺少统一的现场检查协议、证据格式和独立复审约束。
- 当前测试只覆盖状态机 smoke path，尚未覆盖 P0-P4 的语义产物质量。
- 领域差异尚未被结构化描述，例如数据科学、API 采集、GIS 网络、Dashboard、Web 服务等任务缺少轻量任务画像，导致后续审计和回归难以聚类。
- 执行环境假设偏 Windows/Python，对 Linux、Node、R、Jupyter、Docker、长期运行服务等支持不足。
- `supply_halt` 机制存在，但用户侧补给清单和恢复体验还可以更产品化。

## 改进方向

### 1. 正式化产物 schema

为以下核心产物建立 Pydantic 模型和 JSON Schema：

- `spec.yaml`
- `resource_plan.yaml`
- `verifiability_report.yaml`
- `plan.yaml`
- `red_green_checklist.yaml`
- `facts.json`
- `PROVENANCE.yaml`

每个阶段完成后统一执行 `validate-artifact`。校验内容不仅包括字段存在，还应包括跨文件引用关系，例如：

- `plan.final_dag.nodes[].tier` 必须能追溯到 `verifiability_report`。
- `supply_halt.obtain_steps` 不能为空。
- `facts.artifacts[].path` 必须真实存在，除非明确标记 `pending_supply`。
- `packer` 中的交付物必须能对应 `spec.deliverables`。

这一步是最高优先级，因为它能把“模型听话程度”转化为“机器可拒绝的契约”。

### 2. 结构化验收标准，但不固定检查原子

当前 `plan.yaml` 里的验收标准主要是自然语言，适合 LLM 理解，但不利于审计和回归。建议改为结构化验收描述，但不要引入固定的检查原子库。检查脚本仍由 LLM 在现场根据任务生成，结构化字段只负责说明要证明什么、证据在哪里、失败如何判定。

```yaml
acceptance_text: >
  产物 output/etl.parquet 至少包含 2000 行，列必须包含 datetime、station、pollutant、value。
evidence_required:
  artifacts:
    - output/etl.parquet
  invariants:
    - 行数 >= 2000
    - 必须包含 datetime、station、pollutant、value 四列
  verifier_expectation: >
    P5/P6 现场生成脚本读取该文件并打印实测行数、列名和 PASS/FAIL。
  failure_policy: >
    文件不存在、无法读取、行数不足或列缺失均为 FAIL。
```

`acceptance_text` 保留给 LLM 做语义理解，`evidence_required` 约束现场检查必须给出的证据。这样不需要维护不断膨胀的原子检查库，也能避免“只凭感觉说通过”。

### 3. 建立现场检查协议

管理侧明确不希望维护验证原子库，这是合理的。作业类型会持续扩散，固定原子只会越写越多，最后变成另一个需要长期维护的框架。更合适的方向是让 LLM 保持现场检查能力，但把检查过程协议化。

建议规定每次 P5/P6 现场检查必须产出以下内容：

- `verifier_intent`：这次检查要证明哪个验收点。
- `verifier_script`：现场生成的脚本或命令，保存到 `execution/verifiers/` 或 trace 中。
- `inputs`：读取了哪些真实文件、URL、环境变量或进程。
- `observed_values`：实测行数、列名、状态码、文件大小、图节点数等。
- `pass_fail_rule`：本次判定 PASS/FAIL 的明确规则。
- `stdout/stderr/exit_code`：命令真实输出。
- `verifier_self_check`：说明脚本本身可能失效的前提，例如文件格式不符、依赖缺失。
- `auditor_recheck`：P6 不复用 P5 结论，必须独立读验收标准并重写或复核检查。

这相当于复用“检查方法论”，而不是复用一组不断膨胀的检查函数。

### 4. 使用任务画像标签，不建设领域包

管理侧同样不希望维护领域包，这也是合理的。领域包容易从“少量模板”演变成大量半成品方案，覆盖越多越难维护。建议只保留轻量任务画像标签，用于提示 LLM 注意风险、辅助回归聚类和预算决策，不内置默认 DAG、不内置固定实现。

初始任务画像标签可以包括：

- `data_science`：数据清洗、特征工程、建模、评估、报告。
- `time_series`：时间切分、滞后特征、滚动统计、预测窗口。
- `api_collection`：API Key、分页、限流、缓存、探针。
- `gis_network`：坐标转换、站点去重、NetworkX、GEXF、地图可视化。
- `dashboard`：Plotly、HTML 自包含、图表完整性。
- `fastapi_service`：接口、Swagger、启动探针、端口检查。
- `report_only`：纯文档、语言等价验证、引用和格式审计。

这些标签只作为上下文，不提供模板包。DAG 仍由 plan-selector 根据 `spec/resource_plan/verifiability_report` 现场生成。标签的价值在于让后续测试和审计能回答：“这次任务属于哪些风险族，是否触发了对应的检查意识？”

### 5. 强化 Resource Closure 模型

当前资源规划已经有 `inside/outside`、`supply_needed`、`obtain_steps` 等概念。建议细化资源闭包类型：

- `local_provided`：本地已提供，可直接闭环。
- `public_download`：公开 URL 可程序化下载。
- `api_key_required`：需要用户提供 Key。
- `account_required`：需要注册账号。
- `identity_or_phone_required`：需要实名、短信、人机验证。
- `paid_or_quota_limited`：付费或额度不确定。
- `time_sensitive`：依赖实时或近期数据。
- `human_judgement_required`：需要人工评价或主观素材。

P2 裁决器应基于这些类型稳定生成 `A/B/default_trade/supply_halt`，减少凭直觉判断。

### 6. 建立 P0-P4 黄金回归集

当前测试主要验证状态机。下一步应为每个测试用例保存黄金期望：

- `expected_spec_constraints.yaml`
- `expected_resource_breakpoints.yaml`
- `expected_verifiability_summary.yaml`
- `expected_plan_shape.yaml`

测试不需要要求文本完全一致，但需要断言关键事实：

- 空气质量预测必须抽到“宽表转长表”“时间顺序切分”“FastAPI”“HTML Dashboard”。
- 空气质量预测不应产生 API Key 型 `supply_halt`。
- 公交网络分析必须识别高德 API Key 为人工补给项。
- 公交网络分析必须生成 CSV、GEXF、HTML 三类交付物。

这类回归能直接度量泛化稳定性。

### 7. 抽象 Runner 和执行环境

P5 当前偏向 Python + Windows venv。建议引入 Runner 抽象：

- `python_script_runner`
- `fastapi_runner`
- `notebook_runner`
- `node_runner`
- `r_runner`
- `docker_runner`

Runner 负责环境创建、依赖安装、启动命令、健康检查、日志捕获和清理。P5 只需要根据 plan node 的 runtime 类型选择 Runner。

这能让管线从“Python 课程设计生成器”扩展成更通用的作业交付管线。

### 8. 建立历史经验检索库

每次成功运行后，把以下信息脱敏后沉淀为经验样本：

- 原始课程要求摘要。
- 任务类型标签。
- 最终 `spec/resource_plan/plan`。
- 执行失败和修复记录。
- 通过的验证脚本。
- 最终 `facts.json` 和 provenance 摘要。

后续相似任务先检索历史样本，再由 LLM 改写，而不是从零规划。这样泛化能力会随着真实运行次数增长。

### 9. 产品化人工补给流程

`supply_halt` 不应只存在于对话里。建议每次暂停时生成：

- `SUPPLY_REQUIRED.md`：用户需要提供什么、为什么需要、去哪获取。
- `supply_request.yaml`：机器可读补给项。
- `resume.md`：补给后如何恢复。
- `.env.example`：需要的环境变量名，不含真实值。

用户补给后，通过统一命令登记：

```bash
python orchestrator_state.py resolve-supply-halt <run_id> <item_id> env:<ENV_NAME>
```

这样外部 API、账号、数据文件等人工环节会更可控。

### 10. 加强 provenance、安全和交付可信度

最终交付应明确区分：

- AI 生成。
- AI 生成但属于 default_trade。
- 人工提供。
- 人工修改。
- 未完成但有 pending supply。

同时增加：

- Secret scanner，防止 API Key 进入 delivery。
- 外部 URL manifest，记录所有下载和 API 来源。
- checksums，保证产物未被静默替换。
- 数据 lineage，说明每个结果来自哪些输入文件。
- default_trade 水印或显式说明，避免默认产物被误认为真实分析结果。

## 推荐实施路线

### 第一阶段：稳定协议

优先完成：

- 核心 artifact schema。
- `validate-artifact` 命令。
- P0-P4 黄金回归测试。
- `supply_halt` 字段完整性测试。

这一阶段目标是让管线“少漂移、能回归、能拒绝坏输出”。

### 第二阶段：稳定现场验证协议

优先完成：

- 结构化验收标准。
- P5/P6 现场检查报告格式。
- `execution/verifiers/` 或 trace 中保存现场生成的检查脚本。
- Auditor 独立复审规则：不直接信任 P5 的 PASS，必须读取产物重新判断。

这一阶段目标不是消灭临场写验证脚本，而是让临场检查可追踪、可复审、可失败。

### 第三阶段：任务画像泛化

优先完成：

- 任务画像标签。
- 标签与 `spec`、`resource_plan`、`verifiability_report` 的交叉核对。
- 用现有两个 test-cases 做端到端回归。

这一阶段目标是让新课程被稳定描述和审计，而不是通过预置领域包生成方案。

### 第四阶段：执行环境泛化

优先完成：

- Runner 抽象。
- Windows/Linux 路径兼容。
- FastAPI 服务生命周期管理。
- Docker/Notebook 可选支持。

这一阶段目标是减少环境差异导致的失败。

### 第五阶段：经验沉淀

优先完成：

- 成功 run 的经验样本导出。
- 相似任务检索。
- 验证思路、失败模式和 DAG 设计理由复用。

这一阶段目标是让管线随着运行次数持续变强。

## 近期最小可行动作

建议从以下三项开始：

1. 为 `spec.yaml`、`resource_plan.yaml`、`verifiability_report.yaml`、`plan.yaml` 建 Pydantic schema。
2. 为现有两个测试用例建立 P0-P4 黄金回归断言。
3. 定义 P5/P6 现场检查报告格式，要求记录检查意图、现场脚本、输入、实测值、PASS/FAIL 规则和输出。

这三项投入不大，但能显著提升当前原型的工程稳定性和泛化上限。
