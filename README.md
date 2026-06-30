# HomeWork-PipeLine

> Claude Code 全局插件。把你的课程要求 docx 扔进去，全自动产出可交付的课程设计作业。
> 正在开发中，目前为技术原型

## 安装

```bash
# 添加 marketplace
claude plugin marketplace add 86thAuspiciousVerse/HomeWork-PipeLine

# 安装插件
claude plugin install homework-pipeline@homework-dev
```

## 使用

把课程要求的 `.docx` 或 `.md` 文件放在你的作业目录里，然后：

```
cd ~/my-homework/
/hw doc/课程要求.docx
```

管线会自动推进：抽取课程约束 → 裁决哪些可自动验证 → 规划技术方案 → 生成代码 → 真实执行 → 机器校验 → 打包交付。最终产物在 `delivery/` 目录下。

## 设计哲学

**将任务约束到 LLM 能力框架内。** 每个环节先判能否机器验证或语言等价重述，不能则诚实降级——发待人工补给清单，不假装能自动完成。

## OpenSpec

仓库已引入 OpenSpec，当前只用于约束**插件本身**的代码规范、目录职责和说明边界，主 spec 位于 `openspec/specs/plugin-governance/spec.md`。

这里刻意**不**把 OpenSpec 作为 P0-P8 执行管线、`spec.yaml/plan.yaml` 等运行时产物的主定义来源；这些仍以插件 prompt、实现代码和测试为准。

P0-P4 的运行时 artifact 契约由插件实现拥有：prompt 负责要求 `spec.yaml`、`resource_plan.yaml`、`verifiability_report.yaml`、`plan.yaml` 输出场景中立字段，`plugins/homework-pipeline/.homework/artifact_contracts.py` 负责校验必填字段与跨文件引用。OpenSpec 只描述这些行为要求，不复制或替代运行时 schema。

当前审计与语义回归层依赖已归档的 `formalize-generalization-contracts` change：P0-P4 产物必须先满足通用约束、资源闭包、可验证性分层和 DAG 契约，然后再检查 `supply_halt`、`default_trade`、人工补给和 provenance 的完整性。

审计来源的确定性出口在 `plugins/homework-pipeline/.homework/orchestrator_state.py export-provenance <run_id>`；P7/P8 可从该摘要收编 default fallback、pending supply、human-provided、manual completion 和 unresolved work，不读取或落盘密钥明文。代表性 fixture 的语义期望文件位于 `test-cases/<case>/expected/semantic_expectations.yaml`，测试侧匹配器位于 `tests/semantic_expectations.py`，只执行 YAML 明示的通用路径/资源/补给事实检查。当课程 fixture 的预期行为有意变化时，同步更新该 YAML、对应的 `tests/test_semantic_regressions.py` 样例事实，以及受影响的 prompt/validator 约束。

## 当前状态

技术原型阶段。

## 更新

```bash
claude plugin update homework-pipeline@homework-dev
```

## 开发

```bash
uv run python -m unittest tests.test_orchestrator_state_smoke -v
uv run pytest tests/test_artifact_contracts.py -q
uv run pytest tests/test_semantic_regressions.py -q
```
