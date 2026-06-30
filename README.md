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

## 当前状态

技术原型阶段。

## 更新

```bash
claude plugin update homework-pipeline@homework-dev
```

## 开发

```bash
uv run python -m unittest tests.test_orchestrator_state_smoke -v
```
