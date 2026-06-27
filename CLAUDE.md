# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 这是什么仓库

`HomeWork-PipeLine`：一个 Claude Code **全局插件**。学生 cd 到作业目录 → `/hw <需求docx>` → 插件在当前目录做作业。**本仓库是开发仓库**——装全局后，`.claude/agents/*.md` + `.claude/skills/hw/SKILL.md` + `.homework/*.py` 参与运行时，DESIGN.md 和 CLAUDE.md 不参与运行时。

**系统终态已锁（DESIGN.md §11.6）= Claude Code marketplace 插件**：仓库根是 marketplace（`.claude-plugin/marketplace.json`），插件实体在 `plugins/homework-pipeline/` 下。8 个**薄 subagent**（`.claude/agents/*.md`，10-30 行 prompt——只写职责+硬约束，主 agent 在 task 中传 schema）；自写代码 = `hw-exec.py` + `orchestrator_state.py` + `executor/verifiers/`；留痕 = `/term2img` skill；入口 = 1 个 skill（`/hw <docx>`）；安装 = `claude plugin marketplace add <repo> && claude plugin install homework-pipeline@<marketplace>`。**主 agent 自己是编排器**（`/hw` SKILL.md 自包含完整编排指令）。遇 supply_halt 不退出——在对话里暂停等用户提供 API key/数据/账号，用户给了就继续。详见 DESIGN.md §12（Subagent 精简设计）、§11.6（marketplace 结构）、§10（动手顺序）。

## 关键事实（非显然，必读）

1. **`DESIGN.md` 是系统设计的唯一真相源**。能力边界定理(§1)、双闸门(§3)、`spec.yaml`(§4)、裁决器(§5)、供给闸门(§6)、方案筛选(§7.1)、Facts 派生(§7.2)、**执行段全链路设计(§11,含 §11.6 插件落地映射表)** 全在那里。改动任一系统行为前先读 `DESIGN.md`，它用 `【已定】`/`【待定】` 标注取舍。开码前尤其先读 §11.6(每块对应 Claude Code 的什么形态)和 §11.7(P0/P1 矛盾已如何消解)。
2. **`公交网络分析/` 与 `空气质量预测/` 是只读的测试样本/夹具，不是被开发对象**。它们是学生用 AI 手动完成的真实作业,用来驱动和反向校验系统(见 DESIGN.md §8 痛点映射表)。不要改它们的代码或文档;各自有独立 `venv`,互不相通。
3. **`test-cases/` 是从样本中提取的精简测试用例**，用于开发阶段验证。每个用例只包含：课程要求（`doc/课程要求.md`）+ 必需的数据（空气质量有 10 个样本 CSV + 站点列表；公交有 API key 需求无本地数据）。**对公交用例，系统应学会去高德 API 注册页面查文档获取 API key**（这是测试设计意图）。开发验证时应以这些用例为输入，而非直接跑 `公交网络分析/` 或 `空气质量预测/` 的完整代码。
3. **第一版"成"线 = 端到端真执行**（DESIGN.md §2.1 + §11.2.0）：从课程 docx → 方案 → 裁决 → **LLM 生成代码 → 创建作业 venv → `hw-exec` 真跑 → 机器校验产物 → term2img 截图 → auditor 达标检查 → facts.json 合并 → 汇入交付目录**。v1 已包含真执行——不是"只生成代码不跑"。代码生成由 `hw-orchestrator`（LLM subagent）负责，代码执行 + 产物校验由 `hw-exec`（确定性 CLI）负责。二者职责严格分离：LLM 写代码/修代码，执行器只跑子进程 + 机器判定。**作业 venv 在 P5 入口创建（`.homework/run_<id>/.venv/`），汇入交付目录保证复现。LLM 生成的代码也是交付物核心——老师要看的。** 落码按 DESIGN.md §10 四阶段顺序推进（基础设施 → subagent prompt → 执行闭环 → 完善回归）。

## 运行测试样本（验证用，非系统构建）

两个样本各自独立运行，必须先进对应目录、用其各自的 `venv`：

- **公交网络分析**：`cd 公交网络分析`；`pip install -r requirements.txt`；分析全流程 `python main.py --analyze`；也可逐脚本 `python script/01_fetch_data.py … 05`。需要高德 Web 服务 API key（见 `config.py` 的 `AMAP_API_KEY`）。最终交付物是 `output/bus_network_analysis.html`。
- **空气质量预测**：`cd 空气质量预测`；该子目录有自带 `CLAUDE.md`（数据格式/陷阱/达标检查），是 `spec.yaml` 抽取的最佳真实样本；FastAPI 服务 `python app.py`（`/docs` 看 Swagger）；仪表盘由 `dashboard/build_mega_dashboard.py` 构建（**注意该样本文档称产出 `air_quality_mega_dashboard.html` 但文件实际不存在、构建脚本未在本机跑出——这正是 Facts 派生旨在消灭的"文档-文件脱节"案例，校验素材而非 bug**）。

## 处理样本中的中文文档/二进制

按全局指令：读 `.docx`/`.pdf` 等先用 `markitdown` 转 Markdown 再读（中文 Windows 默认 GBK，优先 `-c UTF-8`）。`公交网络分析/doc/实验报告.docx` 与 `空气质量预测/doc/实验报告.docx` 均按此处理。样本中的中文 CSV 在 Excel/GBK 下会乱码，pandas 读时用 `encoding='utf-8'`。

## 开发守则

- 每块新代码都用两个真实作业样本驱动，不凭空造；判据对不对拿 DESIGN.md §8 表逐条勾对。
- 裁决器（DESIGN.md §5）必须自推理重述枚举降级路径并留痕、**保守优先**（不确定偏判 C），勿一次 prompt 定论，勿在闭环外烧 token。降级预算见 §1.3(每环节自枚举候选 ≤2 轮、每轮每候选 LLM-judge ≤1 轮、网搜仅候选依赖外部信息触发 1 次)。
- 供给型断点（API key/账号/外部权威数据，无默认值可兜）必须停下发清单、不能给假默认值跑（与学术诚信冲突）。两档断点(sense_default_trade 给默认继续 / supply_halt 停等人补)见 §6,多源统一回写见 §11.5 P0-4。
- facts.json **唯一合并写者是 P7 Facts 派生层**(§11.7 P0-3);执行器只产 `facts_patch` 分片、Auditor 只产 `red_green_checklist.yaml` + `audit_patch.json`,都不得直接写 facts.json。
- 任何文档派生只引用 `facts.json` 不重写数字；模板引用的产物路径缺失要在**渲染期报错**而非生成假文档(§7.2)。
- 续跑靠 `.homework/run_<id>/state.yaml` 单一真相源(§11.5);执行器/auditor 子状态是它的指针/内联,不是独立真相。