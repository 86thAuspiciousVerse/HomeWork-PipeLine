# HomeWork-PipeLine 设计文档（v0.3）

> 一句话：Claude Code 全局插件。学生 cd 到作业目录 → `/hw <需求docx>` → 插件在当前目录做作业。
> **本文档是开发者设计文档**——不参与运行时。运行时逻辑全在 `.claude/skills/hw/SKILL.md`（自包含编排指令）和各 subagent prompt（`.claude/agents/*.md`）中。

---

## 0. 部署模型（先读这个）

本插件装到全局 Claude Code 后，学生在自己的作业目录里运行 `/hw`。

```
学生终端：
  cd ~/my-data-science-homework/
  /hw doc/课程要求.docx

运行后该目录下会出现：
  .homework/run_20260627-001/state.yaml   （管线状态）
  .homework/run_20260627-001/artifacts/   （中间 yaml）
  .homework/run_20260627-001/code/        （LLM 生成的代码——也是交付物的一部分）
  .homework/run_20260627-001/execution/   （stdout/截图）
  delivery/北京公交网络分析/              （最终交付物目录，含代码+venv+产物+文档）
```

**谁参与运行时**（装在全局插件目录）：
- `.claude/skills/hw/SKILL.md` — `/hw` 入口，自包含完整编排指令
- `.claude/agents/*.md` — 8 个薄 subagent
- `.homework/hw-exec.py` — 小执行器
- `.homework/orchestrator_state.py` — 确定性状态机
- `plugin-venv/` — hw-exec 自身 Python 依赖（pydantic/pyarrow/pandas），与学生作业 venv 隔离

**谁不参与运行时**（只在开发仓库）：
- `DESIGN.md` — 本文档，开发者设计文档
- `CLAUDE.md` — 开发本插件时的 Claude Code 记忆
- `公交网络分析/`、`空气质量预测/` — 测试夹具

**关键事实**：学生目录里没有 DESIGN.md。`/hw` skill 是唯一入口，它的 SKILL.md body 自包含全部编排规则。主 agent 通过 skill 指令推进管线，通过 Agent 调用把 schema + 任务传给 subagent。

---


## 1. 能力边界定理（系统的根本公理）

### 1.1 定理陈述

推论：
- 闭环全部落在可机器验证环节内的作业 → 可端到端自动化。
- 任一必经环节拿不到机器反馈信号、且无法被降级为可机器验证等价路径、且无可用默认产物替代 → 该作业**诚实降级**为"骨架 + 人工断点"，系统不假装完成它。

### 1.2 可验证性三档

| 档 | 判据 | 典型 | 系统行为 |
|----|------|------|---------|
| **A 强可验证** | 有确定 pass/fail 断言，机器秒判，无语义判断 | 数据量≥1GB、PEP8、requirements 版本锁定、构成文件齐全、时间序列按时间切片(70/15/15)、R² 落在区间、单元测试通过 | 全自动 |
| **B 弱可验证** | 仅能用 LLM-judge / 结构化准则近似勾对 | 报告"论证展开"、代码"结构清晰"、方案"答辩站得住"、生成的前端"对标设计准则勾对" | 全自动（带留痕） |
| **C 需人感官** | 机器拿不到反馈信号，闭环在此断裂 | 浏览器内像素级视觉对齐/文字不重叠的感官确认；领取 API key 需人机验证/短信的浏览器交互 | 降级处理 |

### 1.3 关键反直觉点：C 不是"类别判定"，是"穷举降级失败的残留"

裁决器判一个环节为 C，**不是**因为它属于前端/音乐这类标签，而是**穷举过所有"把该环节转译为语言可描述等价方法"的降级路径后仍无可验证方案**才判 C。

> 反例（你举过的"听音乐判感情"）：表面是 C（非音频模型做不到），但存在降级路径"查这首歌资料 + 读评论区估算感情"，后者**是 A/B**。于是该环节按降级路径判为可达，不判 C。

**重要**：找降级路径主要靠 **LLM 自行推理重述任务**（"这条任务能否被改写为仅用文字/表格/代码就能定义并验证的等价形式？"），**而非上网搜"怎么把听音乐变成文字"这种笨查网**。网搜仅在某个候选降级路径**本身需要外部信息才能成立**时才触发一次（如选定"查这首歌评论区"后真的需要去读评论），不是判定降级时的默认动作。

判定流程对每个环节 E 执行四步：

```
Step 1  E 能拿到机器 pass/fail 反馈信号?            → 是 → A
Step 2  退一步，E 能用 LLM-judge / 结构化准则验证?   → 是 → B
Step 3  LLM 自行枚举把 E 重述为"语言可描述且可验证"的等价候选 E'：
          对每个候选用 LLM-judge 验其是否可达可验证；候选依赖外部信息才补一次网搜
          找到且 E' 可验证 → 按 E' 判 (A/B)
          枚举穷尽后仍无任何可语言化等价方法 → 真·不可达 C
Step 4  落 C 时:约束是否允许给默认产物(默认样式 HTML/示例数据)?
          允许 → 放行，降记为"默认产物贸易"档 (实质按 A 处理但标注来源)
          不允许(如 API key/账号/外部权威数据没有可用默认) → 停止，发供给清单
```

**保守优先**：枚举降级不确定时，宁可偏判 C（给默认/发供给），也勿乐观判 A/B 在闭环外烧 token。【已定】

**降级推理预算（已定）**：每环节 LLM 自行枚举降级候选上限 **2 轮**；每轮内对每个候选用 LLM-judge 验证 **1 轮**；网搜只在某候选自身依赖外部信息才触发 **1 次**（非默认、非每环节都有）。预算甩尽仍无解默认偏判 C。

---

## 2. 第一版范围与边界

### 2.1 第一版"成"的线

从课程资源输入 → 产出以下**五件**可交付物即"成"：

1. **能力可达性裁决报告**：对作业每个必经环节标 A/B/C，附自推理降级留痕与背理由。
2. **约束驱动的方案推荐**：候选方案按 A 约束自动过滤，输出推荐 + 淘汰理由（即原作业里那段删除线决策表的形式化、自动化版本）。
3. **待人工供给清单**：把所有"无默认值可兜底"的外部依赖列成清单（API key 申请步骤、外部数据下载链接与步骤），发用户补给。
4. **真执行产物 + 留痕截图**：P5 EXECUTOR 真实跑代码（子进程 `python main.py`），抓 stdout/exitcode，按 A 准则校验产物（行数/列数/文件存在/表达式断言），term2img 自动截终端图。代码由 LLM 在 P5 阶段按 plan.yaml DAG 逐 node 生成，`hw-exec` 负责子进程驱动 + 机器校验——**LLM 写代码，执行器跑代码**。
5. **派生交付文档**：基于单一事实源 `facts.json`（含真实跑出来的 metrics）派生 README / 实验报告 / 答辩稿 / ppt，消灭"同一数字散落多份手动同步"导致的脱节。**事实来自真实执行结果，不是推测**。

### 2.2 第一版显式不做（留给 v2）

- **全自动化端到端**（无人值守跑完所有阶段）。v1 需要人工处理 supply_halt 断点（API key 申请等）——系统会在对话里列出需要什么，等用户直接粘贴 key/账号/数据后继续推进。v2 可通过预配 vault 或凭据注入实现零人工。
- **完整文档渲染**。v1 的文档派生产出 Markdown outline + 模板渲染草稿——排版、格式微调、最终 PDF 转换留 v2。
- **多课程类型全覆盖**。v1 只验证数据科学/网络分析类作业（两份样本覆盖的类型）。前端/Django/嵌入式等其他类型作业的 spec schema 扩展留 v2。

但**v2 所需的所有数据结构在 v1 spec 中必须已存在**，否则 v2 要回头改 schema。【已定】

---

## 3. 双闸门架构

执行前的两道闸，把"AI 死磕改不动 bug"这类失败挡在执行**之前**。

```
课程资源输入(第一输入)
        │
        ▼
┌──────────────────────────┐
│ Spec 抽取器               │  → spec.yaml (结构化约束/交付物/陷阱)
│ (第一版轻量, 人辅/LLM 抽) │
└──────────────────────────┘
        │
        ▼
┌──────────────────────────┐
│ Resource Planner          │  → resource_plan.yaml (补充资源设需)
│ (LLM 思考:去哪下数据/要啥 │     AI 能找到的语言可描述部分全靠它
│  API/怎么申请/技术栈候选)   │
└──────────────────────────┘
        │
        ▼
┌──────────────────────────┐   闸 1
│ 可验证性裁决器            │  → verifiability_map + 降到留痕
│ (四步判定 + 自推理重述agent)│
└──────────────────────────┘
        │
        ▼
┌──────────────────────────┐   闸 2
│ 资源就绪闸门              │  → 供给清单 / 放行 / default 贸易
│ (两档断点分类)            │
└──────────────────────────┘
        │
        ▼
        │ （仅 A/B 闭环内、闸门已过的世界）
        ▼
┌──────────────────────────┐
│ 约束驱动方案筛选          │  → 方案推荐 + 淘汰理由（留痕）
└──────────────────────────┘
        │
        ▼
┌──────────────────────────┐
│ Facts 派生                │  → facts.json → 文档派生
└──────────────────────────┘
        │
        ▼ (v1 终止于此线)
   可交付四件套产出
```

**性格刻画**："宁可慢、宁可多问一轮，也不在拿不到反馈的墙上烧 token。"【已定】

---

## 4. spec.yaml：系统的单一契约入口

Spec 抽取器把课程资源 docx/pdf + 任何用户附带的参考代码抽成结构化 `spec.yaml`。**抽取方式已定:纯 LLM 抽**(用户扔进课程要求即走,不再要人工填字段,以兑现"扔进去全自动"初心)。但课程输入常残缺(用户删过头、附件缺失、截图抽不出),纯 LLM 抽有"无声抽歪"风险——故配 §4.1 完备性自检 + 保守兜底,把抽漏的风险内化处理、不打扰用户。以下是字段定义,已用真实作业(空气质量预测 CLAUDE.md)反向校验——见 §8。

```yaml
# spec.yaml
version: 0.1
course:
  name: 城市空气质量预测
  course_id: "#13"           # 若来自选题库
  source_files: [converted.md]  # 原始输入路径(可能缺失)
  extraction_confidence: high   # high/medium/low——见 §4.1 自检
  missing_signals: []           # 自检发现的"原文有线索但 spec 未落字段"清单

constraints:
  hard:                      # A 级，可机判
    - id: DATA_VOLUME
      rule: "结构化数据 ≥ 1GB"
      verify: {type: assert, expr: "size_gb(data/raw) >= 1"}
    - id: DATA_FRESHNESS
      rule: "数据须为 2023 年后"
      verify: {type: assert, expr: "min_date(data) >= 2023-01-01"}
    - id: TS_SPLIT
      rule: "严禁 train_test_split 随机切分，按时间切片 70/15/15"
      verify: {type: assert, check: timeseries_split_respected}
    - id: CODE_STYLE
      rule: "PEP8 + 版本锁定 requirements.txt"
      verify: {type: tool, tool: ruff/version-pin-check}
    - id: STACK_REQUIRED
      rule: "须包含 CI/CD + PyEcharts/FastAPI"   # 注:课程要求的栈 ≠ 最终选定栈
      verify: {type: presence, in: requirements_and_ci}
  soft:                      # B 级，LLM-judge
    - id: REPORT_DEPTH
      rule: "实验报告论证须展开,非流水账"
      verify: {type: llm_judge, rubric: "..."}
  bonus:                     # 加分项,B 级
    - id: IMPUTED_FLAG
      rule: "连续缺失>6h 标记 is_imputed 列(数据质量意识)"

deliverables:                # 交付物清单 + 每项的必经路径环节
  - id: DASH_HTML
    type: interactive_html
    path: dashboard/air_quality_mega_dashboard.html
    stages: [etl, feature, model, visualize]
  - id: REPORT_DOCX
    type: docx_report
    path: doc/实验报告.docx
  - id: DEFENSE_PPT
    type: html_slides
    path: doc/ppt演示.html

pitfalls:                    # 陷阱,执行时绕路用(来自原 CLAUDE.md "关键约束与陷阱"段)
  - "中文 Windows 上 Excel 用 GBK 打开 CSV 乱码,须 pandas encoding='utf-8'"
  - "1269 个 CSV 全加载内存溢出,须分块批处理"
  - "Prophet 包名是 prophet 非旧名 fbprophet"

tech_constraints:           # 课程指定的技术栈约束(可能与最终选定不同——见方案筛选)
  required: [FastAPI, "CI/CD"]
  suggested: [PyEcharts]      # 课程要求,但可被方案筛选淘汰(留淘汰理由)
  forbidden: []
```

### 4.1 输入完备性自检 + 保守兜底（不打扰用户）【已定】

兑现"纯 LLM 抽不抽歪"的关键机制,完全系统内部行为,不唤用户:

1. **纯 LLM 抽**:对用户给的任何残缺输入照抽,抽到多少算多少(全自动)。
2. **自检**:扫输入中"明显指向某类约束但 spec 未生成对应字段"的迹象(例:原文出现"2023 年后"但 `DATA_FRESHNESS` 未生成 → 高概率漏抽),记入 `course.missing_signals` 并降 `extraction_confidence`。
3. **保守兜底**而非"中断叫用户填":对没把握的硬约束一律按**最严档**假设其存在来跑。例:不确定有没有"按时间切片"硬约束 → 默认当有、按时间切片跑(在时间序列作业里按时间切片永不会错,最坏是白做了一点额外约束)。代价是可能多做一点不必要工作,但作业**不会因漏抽缺评分点**,且用户**没被叫起来**。
4. **唯真·无解残缺才走供给清单**:只有连"原文存不存在、有没有这条约束"都无从补救时,才进 §6 的 `supply_halt`——而那是用户已接受的"系统真拿不到必须用户给"断点,非"系统懒得抽让用户填",不违初心。

> 反向验证:公交课设指导说明被作者删 + 空气质量 `converted.md` 不存在——纯 LLM 抽到此会 confidence=low、missing_signals 非空→系统按该课程类型的"已知常见硬约束全集"做最严档兜底假设,而非抛回用户。

**字段够不够的校验**：原空气质量 CLAUDE.md 中"时间序列/内存管理/缺失值/Python 环境"四节陷阱、课程达标检查四项硬指标、技术栈表，**全部可落进上述 schema 而无遗漏**，证明字段集对数据类作业充分。（前端/Django 类作业待第二阶段补 `ui_deliverable` 子结构。）【已定字段集进入第一版骨架】

---

## 5. 闸 1：可验证性裁决器

### 5.1 输入输出契约

```
输入: spec.yaml + resource_plan.yaml
输出: verifiability_report.yaml
```

```yaml
# verifiability_report.yaml
verifiability_map:
  - stage_id: etl
    deliverable: DASH_HTML
    tier: A
    rationale: "宽表转长表后行列数可断言,可机判"
    downgrade_attempts: []          # 无需降级
  - stage_id: visualize
    deliverable: DASH_HTML
    tier: B
    rationale: "图表语义正确可 LLM-judge 苹图"
    downgrade_attempts:
      - path: "默认 Plotly 样式可接受否?"
        result: spec 约束未提视觉要求 → 视为允许默认样式 → 降记 default_trade
        triggered_search: false      # 此候选不依赖外部信息,未网搜
    resolved_tier: A (default_trade)   # 降级后实质档
  - stage_id: web_listen_music       # 你举的反例
    tier_after_search: B
    rationale: "原任务'听音乐判感情'不可达,但降级路径'查资料+读评论区估感情'可达且可 LLM-judge"
    downgrade_attempts:
      - path: "非音频模型直听"
        result: 闭 C
        triggered_search: false
      - path: "查该歌曲资料+读评论区感情估测(重述为文本感情分类任务)"
        source: "LLM 自我重述枚举(非网搜发现)"   # 说明该候选是 LLM 推理想出来的
        result: 可达 B
        triggered_search: true         # 此候选成立需读真实评论,故触发 1 次网搜
        search_query: "<歌曲名> 评论 听后感"
  - stage_id: amap_api_register       # 公交作业真实坑
    tier_after_search: C_irreducible
    rationale: "领取高德 key 需浏览器人机验证/短信 nonzero 默认值可替"
    downgrade_attempts:
      - path: "公开 mock 地理数据替"   # 结果:与 AcademicIntegrity 冲突,弃
        triggered_search: false
      - path: "用系统域内默示 key"     # 结果:无可用默认,不成
        triggered_search: false
    breakpoint: {type: human_supply, target: amap_api_key}
breakpoints_summary:
  sense_default_trade: [visualize]    # 给默认继续跑
  supply_halt: [amap_api_register]    # 停下发清单
auto_mode: full                       # 若 supply_halt 非空实为 scaffold_with_breakpoints
decision_trace: "..."                 # 给答辩用(方案验选复用)
```

### 5.2 裁决器实现形态【已定】

**自推理重述型多轮 agent**（非上网穷举、非一次 prompt 定论）。核心是 LLM **自己**:对每个环节重述任务、枚举"能否改成纯语言可定义可验证的等价形式":
- 多轮 "自我重述枚举降级候选 → 对每候选 LLM-judge 验是否可达可验证 → 必要时单次网搜补外部信息 → 判"。预算见 §1.3。
- 全程留痕每条降级候选及其来源(LLM 重述 vs 网搜发现)、是否触发网搜、结果。
- **保守优先**:穷举不确定时偏判 C。
- **网搜是例外不是默认**:仅在自枚举出的某候选本身依赖外部信息才成立时才触发一次。
- 理由:闭环内作业误判保守可补,误判乐观烧 token 还交不出东西。

---

## 6. 闸 2：资源就绪闸门（两档断点分类）【已定】

C 类断点按"是否有可用默认产物兜底"分两档，系统行为不同：

| 断点类型 | 可兜底? | 典型 | 第一版系统行为 |
|---------|--------|------|--------------|
| `sense_default_trade` 感官型-给默认 | 是 | 可视化样式(默认 Plotly/OSM 样式)、能用但欠打磨的前端 | 给默认产物继续跑,记 trade 标签 |
| `supply_halt` 供给型-停等人 | 否 | API key 申请(浏览器交互/短信)、外部权威数据下载、需实名的账号 | **停下**,生成《待人工供给清单》(含步骤),等用户补给后重启 |

**"supply_halt" 与 §1 题选的"断点给默认产物继续跑"不冲突**：后者管 `sense_default_trade` 档,前者管 `supply_halt` 档。两档都进 `breakpoints` 但 type 不同、行为不同。这正是公交流水线里那个 `term2img` 之外最重的体力活被自动的部分。

供给清单格式：
```yaml
# supply_checklist.yaml
items:
  - id: amap_api_key
    kind: api_key
    why: "爬取公交站点经纬度必需;裁决已确认无默认值可替且无闭外降级路径"
    steps:
      - "前往 https://lbs.amap.com 注册开发者账号(需手机验证)"
      - "控制台创建应用,获取 Web 服务 API key"
      - "填入 config.py 的 AMAP_API_KEY (或环境变量)"
    when_provided: "重跑 pipeline 阶段即可续行"
```

---

## 7. 闸门之后：约束驱动的方案筛选 + Facts 派生

### 7.1 方案筛选

输入 `spec.yaml.constraints + resource_plan + verifiability_report`，输出方案 DAG：

```yaml
# plan.yaml
candidate_stack: [prophet, linear_regression, xgboost, lstm]
decisions:
  - candidate: prophet
    verdict: REJECT
    reason: "Prophet 对年均值无超额,且数据为可线性趋势(Spec 不要求复杂周期)"
    evidence: "原作业技术路线第七节关键决策记录"
  - candidate: lstm
    verdict: REJECT
    reason: "趋势+季节已解释 63%,深度学习边际收益低于成本与本课程范围"
  - candidate: linear_regression
    verdict: ADOPT
    reason: "指数衰减/线性拟合外推至 2030,R² 0.74-0.91 兑现约束且最简"
  - candidate: xgboost
    verdict: ADOPT(辅助)
    reason: "残差修正 + 特征重要性替代 SHAP"
final_dag:
  nodes: [fetch, clean_chunked, feature_57dim, pca, trend_fit, decomposition, build_dashboard]
  edges: ...
decision_trace_preserved: true   # 是答辩用产物之一,非副产物
```

### 7.2 Facts 派生（消灭脱节）【已定】

**单一事实源 `facts.json`**：所有数字、结论、图表路径、R² 集中存储。README / 报告 / 答辩稿 / ppt 全部由模板 `{{ facts.x }}` 渲染、**只引用不重写**。改一处全处同步。

> 解决真实痛点：空气质量作业里文档声称的交付物 `air_quality_mega_dashboard.html` 实际不存在,`build_mega_dashboard.py` 未跑出。根因是同一事实被改写多份、手动同步导致漏网。Facts 派生从结构上杜绝。

```json
// facts.json (节选)
{"lines": 760, "stops": 5577, "edges": 181352, "rings": 106,
 "r2_no2_bj": 0.912, "pca_pc1_ratio": 0.34,
 "deliverables": {"dashboard_html": "dashboard/air_quality_mega_dashboard.html"}}
```

派生时模板若引用的 `facts.deliverables.dashboard_html` 路径检查不存在 → **渲染期报错而非生成假文档**。这就是把"脱节"从"事后发现"变成"渲染期挡下"。

---

## 8. 反向验证：用两份真实作业校验本文档

| 真实痛点 | 本文档对应规则 |
|---------|--------------|
| 公交作业文档列了 `大数据课程设计自主学习指导说明.doc` 但已删 / 空气质量 CLAUDE.md 反复引用 `converted.md` 但不存在 | §4 spec.yaml 保留 `source_files` 字段,缺失即标红,裁决器据此识别人工输入残缺 |
| 空气质量 CLAUDE.md 技术栈栏写的是已废弃的 Prophet/LSTM/SHAP/PyEcharts,与实际 LinearRegression/Plotly 脱节 | §4 `tech_constraints.suggested` ≠ 最终选定;§7.1 方案筛选负责在二者间产出带淘汰理由的决策;`decision_trace` 留痕是答辩素材 |
| 空气质量 `air_quality_mega_dashboard.html` 文档列出但实际不存在 | §7.2 Facts 派生渲染期路径检查挡下 |
| 公交作业 `.claude/settings.local.json` 白名单了 `term2img.py`,5 个脚本逐个渲染 PNG 手工嵌入报告 | §7.2 文档派生附带"运行留痕自动捕获"接口(v1 预留),v2 的执行沙箱统一产出截图据 facts 路径嵌入 |
| 公交作业 GCJ-02→WGS-84 坐标转换、API 配额限速;空气质量 13230 CSV 内存溢出 | §4 `pitfalls` 字段由 Spec 抽取器从"关键约束与陷阱"段落抽数据,执行阶段据此绕路 |
| 领取高德 key 需浏览器人机验证/短信——AI 架构外 | §1.3 Step 4 + §6 supply_halt,停下发清单 |
| "听音乐判感情"看似不可达但有降级路径 | §1.3 Step 3 穷举降级,按可达路径判 |
| 同类作业随约束跨档:公交作业接受默认 Plotly 样式→A;若要求获奖级视觉→B 或局部 C | §1.3 动态判定不查类型表,§5.1 downgrade_attempts 记录降级决策 |

---

## 9. 设计待定项（均已敲定）

1. **Spec 抽取器抽取方式** → **已定:纯 LLM 抽**(用户扔进课程要求即走,不唤人工填,兑现"扔进去全自动"初心)。配 §4.1 完备性自检 + 保守兜底处理纯 LLM 抽的"无声抽歪"风险 → 见 §4.1。

2. **裁决器降级推理预算** → **已定:每环节 LLM 自枚举降级候选上限 2 轮,每轮内对每候选 LLM-judge 验证 1 轮,网搜仅在自枚举出的候选依赖外部信息才触发 1 次**(非默认)。预算甩尽仍无解默认偏判 C → 见 §1.3。

> §9 不再有阻塞项。可按 §10 启动。

---

## 10. 第一版动手顺序（§11.8 已全定，可启动）

> **v1 包含真执行**——顺序已据此重排。核心原则：让执行器尽快可用，因为 subagent 的 prompt 质量需要通过"真跑→看报错→改 prompt→再跑"来迭代。先写能跑的东西，再写能看的东西。

### 阶段 A：基础设施（先建跑道）

1. **落 `orchestrator_state.py` + `state.yaml` pydantic schema**。这是所有阶段的共同依赖——没有 state.yaml 就没有 run_id，没有 run_id 就没有产物落盘路径。先让 `create_run(docx)` 能跑通。
2. **落 `.claude-plugin/plugin.json`**。插件元数据骨架——name/version/description。让整个仓库是一个有效（尽管空壳）的 Claude Code 插件。
3. **落 `hw-exec` CLI 骨架**。五个 verb 的 CLI 入口（prepare/run-node/verify-node/commit-facts/status）+ check 原子集的前三个（file_exists/row_count/col_set）。**不需要完整实现所有 check，够验证第一个代码样本就行。**
4. **落 `.homework/` 目录结构**。run 根目录、artifacts/、execution/traces/ 的创建逻辑。

### 阶段 B：逻辑层 subagent prompt（先写最难的）

5. **写 `spec-extractor.md` prompt**。内嵌 §4 spec.yaml schema + §4.1 自检逻辑。拿空气质量 `CLAUDE.md` 做固定输入，断言产出的 `spec.yaml` 字段完整。
6. **写 `adjudicator.md` prompt**。内嵌 §1 能力边界定理 + §5 四步判定。这是最难写的 prompt——拿两份样本的每个 stage 逐条验证 A/B/C 判定是否合理。
7. **写 `plan-selector.md` prompt**。内嵌 §7.1 方案筛选——依赖 spec + resource_plan + verifiability_report 三个输入。
8. **写 `resource-planner.md` prompt**。内嵌 §11.1 资源桩规约。注意：Resource Planner 在管线执行顺序上排在裁决器（P2）之前（P1），写 prompt 时排在裁决器之后是因为需要"裁决器会怎么判"的前置直觉来指导 prompt 设计——但管线顺序不变。

### 阶段 C：执行闭环（让代码真正跑起来）

9. **写 `hw-orchestrator.md` prompt**。内嵌 §11.5 编排逻辑——这是主控 agent，需要知道什么时候派谁、断点怎么处理。**P5 阶段的代码生成由 hw-orchestrator 自己做**（它是 LLM subagent，可以 Write `.py` 文件），`hw-exec` 只负责子进程驱动 + 机器校验。
10. **端到端跑通一份简单样本**（空气质量预测的 ETL 环节）。从 spec 抽取 → 资源规划 → 裁决 → 方案 → 生成 ETL 代码 → `hw-exec` 真跑 → verify → auditor → facts → 打包。**这是第一块里程碑。**
11. **写 `auditor.md` prompt**。内嵌 §11.3 B 级 judge 逻辑 + 三时点——此时已有真实执行产物可以 judge。
12. **写 `facts-deriver.md` prompt**。内嵌 §7.2 facts.json 合并 + 模板渲染——此时已有真实 metrics 可以写入 facts.json。
13. **写 `packer.md` prompt**。内嵌 §11.4 打包规则——此时已有完整产物可以打包。

### 阶段 D：完善与回归

14. **补全 `hw-exec` 所有 check 原子**。col_range / dup_key / json_path / file_size_min / stdout_assert / exit_match / assert_expr。
15. **term2img 集成**。`hw-exec run-node` 完成后自动调 `/term2img` 截终端图。
16. **两份样本全链路回归**。对标 §8 痛点表逐条验证——每条都必须有对应的真实产物或明确断点。

> 原则：每一块都用真实作业样本驱动，不凭空造。判据对不对拿 §8 表逐条勾对。

---

## 11. 执行段最终设计（从输入到输出全链路,整合设计稿）

> 本节由"编排设计(5 块并行设计 → 内部自洽审查 → 整合)"产出,已应用自洽审查发现的所有 P0/P1 矛盾修法。§11.1–§11.5 为五块设计,§11.6 为插件落地映射,§11.7 为矛盾修法一览,§11.8 为仍开放的待定项。
> 本节对 §1–§7 的改动均为"加字段不推翻已定语义"(§11.0 已列)。本节落地后,系统"从输入到输出"全链路设计完整,可照着开码。

### 11.0 本次设计覆盖范围与对 DESIGN.md 的增改说明

**覆盖范围**:
- §11.1 Resource Planner:资源桩 + 获取事实桩(逻辑 subagent)。
- §11.2 执行沙箱 + 小执行器:唯一自写代码层。
- §11.3 Auditor 达标自检:verify DSL 执行 + B 级 judge。
- §11.4 Packer 打包交付:归档 + 诚信标注 + 复现说明。
- §11.5 端到端状态机:9 阶段串行与两类断点。
- §11.6 插件落地映射:每块对应 Claude Code 的 subagent / skill / 小执行器。
- §11.7 P0/P1 矛盾修法应用一览。

**对已定逻辑层的增改(均为加字段不推翻已定语义)**:
1. §5.1 字段增订(P1-5):`verifiability_map[]` 统一为每条带 `resolved_tier`(A/B/C/C_irreducible/default_trade)为唯一最终档字段;保留 `initial_tier`/`tier_after_search` 作推理留痕;`breakpoints_summary` 由"两纯列表"增订为带结构记录的列表(折叠 Resource Planner 的 closure/default_available 事实,使闸2成为纯函数)。
2. §7.1 plan.yaml 增订(P1-4):新增 `relaxed_verify[]`(被方案筛选 REJECT 的栈对应的 verify 块标 skip,不改 spec 原件) + `contract.tier_source` + `default_artifact`。
3. §7.2 facts.json 写权收归(P0-3):facts.json 唯一合并写者是 P7 Facts 派生层;执行器只产 `facts_patch` 分片、Auditor 只产 `red_green_checklist.yaml`,均不得直接 `json.dump` 进 facts.json;子结构命名统一为 `metrics/artifacts/checklist/provenance`。
4. §6 supply_checklist.items[] 必填字段定死(P0-2):`id/kind/why/steps/when_provided` 五项必填;多源合并缺省字段由闸2补齐再落盘。
5. 新增断点回写统一协议(P0-4):闸2/执行器/Auditor 任一阶段可产出 supply_halt item 追加进 `state.yaml.breakpoints.supply_halt.batch`,每阶段进入前统一断言 batch 全 resolved。
6. 新增续跑状态单一真相源:`state.yaml` 为顶层唯一真相,执行器 `state.json` 与 Auditor 子状态作为其子节点内容(`substate_ref`/`substate`),主 agent 只读顶层。
7. run 根目录统一(P1-2):权威根 `.homework/run_<id>/`;执行器 `--run-dir` 指向它;traces 统一落 `.homework/run_<id>/execution/traces/`。

**不增改、仅澄清对齐**:§1.3 降级预算原公式不变(本设计把计量单位显式化);§3 双闸门链路顺序不变;§4 spec.yaml 字段集不变(P0 后 spec 冻结只读)。

### 11.1 Resource Planner（逻辑层 subagent,非执行器）

#### 11.1.1 用例 / 接口契约

**位置**:Spec 抽取器(§4/P0)之后、闸1裁决器(§5/P2)之前。纯 LLM 推理,不执行、不判 A/B/C、不下 ADOPT/REJECT、不下断点档位。本块只产"资源桩 + 获取闭环外性"事实桩,为闸2两档分类提供必要(非充分)事实输入。

**主产物 `resource_plan.yaml`**(字段级):

```yaml
resource_plan.yaml:
  version: 0.1
  metadata:
    spec_ref: spec.yaml
    source_files_consumed: [converted.md]
    planning_confidence: high | medium | low
    missing_resource_signals: []
  resources:                       # 资源桩主产物
    - id: <STABLE_ID>             # 形如 QUOTSOFT_AQ_CSV / AMAP_API_KEY / GCJ02_TOOLKIT
      kind: dataset|api_key|api_endpoint|account|library|reference_doc|compute_env|credential_file
      stage_id: <etl|fetch|...>    # 关联 spec.deliverables[].stages
      serves_constraints: [DATA_VOLUME]
      acquisition:
        mode: programmatic|human_in_loop|human_supply
        supply_needed: true|false  # true=获取动作在 AI 闭环外(→ 闸2 supply_halt 种子)
        closure: inside|outside    # outside=获取无法在纯代码+机验信号下闭环
        closure_reason: "..."      # outside 的依据(人机验证/短信/实名/付费/线下/图形验证)
      programmatic:                # mode=programmatic 时填,否则省略
        url: "https://..."
        method: http_get|http_post|scraping|git_clone|pip_install|cli
        auth: none|bearer|basic|hmac
        rate_limit: "{1000/天, 1 req/s}"
        expected_volume_gb: 2.12
        file_count: 13230
      constants:                   # 新增(P2-5b):供 plan_selector 写 contract check 数值的静态量
        - name: wgs84_lng_window
          value: {lo: 119.0, hi: 121.0}
          for_constraint: COORD_CONVERT
          rationale: "青岛站点真实经度边界,取自站点列表.csv 范围"
      obtain_steps:                # 人读步骤,供 §6 supply_checklist 渲染
        - "前往 <URL> 注册开发者账号(需手机验证)"
        - "控制台创建应用,获取 Web 服务 API key"
        - "填入 config.py 的 AMAP_API_KEY (或环境变量)"
      when_provided: "重跑 01_fetch_data.py 阶段即可续行"
      default_available:           # 客观事实,不做业务判定
        has_default: true|false
        default_note: "..."
      rationale: "..."
      source: spec.tech_constraints.required|llm_inferred|search_verified
      triggered_search: false
      search_query: ""             # 仅 triggered_search=true 才填
  tech_candidates:                 # 供 §7.1,候选+rationale,不下 ADOPT/REJECT
    role: trend_model
    candidates:
      - name: linear_regression
        base_stack: [pandas, numpy, scikit-learn]
        resource_deps: [QUOTSOFT_AQ_CSV]
        feasibility_note: "..."
        role_in_dag: primary|alternate
    shortlisted: [linear_regression, prophet, xgboost]
    decision_trace_to_plan: true
  self_check:
    coverage:
      - stage_id: etl
        resources_found: [QUOTSOFT_AQ_CSV]
        gaps: []
    planning_confidence: high
```

**字段消费关系**:
| 本块字段 | 下游 | 用途 |
|---|---|---|
| `resources[].stage_id` | §5 裁决器 | 取该环节资源桩做四步判定 |
| `resources[].acquisition.{supply_needed,closure}` + `default_available.has_default` | §5 裁决器(折叠进 breakpoints_summary) | 闸2两档分类的事实输入 |
| `resources[].constants[]` | §7.1 plan_selector | 写 contract check 的 op/value/lo/hi |
| `resources[].programmatic.{url,rate_limit}` | 执行器 + spec.pitfalls | 配额避坑 |
| `tech_candidates` | §7.1 `plan.yaml.candidate_stack + decisions` | 候选+rationale 复用 |

**与 §6 supply_checklist 映射**(逐字段):`id→id, kind→kind, rationale→why, obtain_steps→steps, when_provided→when_provided`,触发条件 `acquisition.supply_needed==true`。本块只给"获取动作闭环外"必要条件;"无闭外降级路径"充分条件由闸1穷举降级后补进 `why`(闸2拼接,本块不越界)。

#### 11.1.2 对应 Claude Code 形态

- **`.claude/agents/resource-planner.md`**:纯 LLM 多轮自推理 subagent。tools = 内置 Read/Edit/Bash(只读无副作用:HEAD 探测 URL、`rg` 核验文件存在) + Tavily(单次补外部信息,非默认) + Github(查参考仓)。保守准则内置:不确定偏 `supply_needed:true`、网搜非默认、不下 A/B/C 判、不下 ADOPT/REJECT、不执行下载/申领 key。

### 11.2 执行沙箱 + 小型自写执行器

> **§11.2.0 新增——v1 真执行后"谁写代码、谁跑代码"的职责划分（上一版缺失）**

P5 执行段分两层，由两个不同角色承担：

| 层 | 谁做 | 是什么 | 做什么 |
|---|---|---|---|
| **代码生成** | `hw-orchestrator`（LLM subagent） | Claude Code subagent，有 Write/Bash 工具 | 创建 venv → 读 plan.yaml DAG → 逐 node 生成 `.py` 代码文件 → 调 `hw-exec run-node` |
| **代码执行 + 产物校验** | `hw-exec`（确定性 CLI） | Python 子进程驱动，零 LLM | 用作业 venv 的 Python 跑 `subprocess.run(python <script>)` → 抓 stdout/exitcode → 按 contract check 原子校验产物 → 落 `facts_patch` |

**全流程（P5 内部循环）**：

```
P4 产出 plan.yaml（DAG: [fetch, clean, feature, model, dashboard]）
         │
         ▼
hw-orchestrator 进入 P5：
  │
  ├─ 0. 创建 venv（作业隔离环境）：
  │     python -m venv .homework/run_<id>/.venv
  │     .homework/run_<id>/.venv/Scripts/pip install -r requirements.txt
  │     （requirements.txt 从 plan.yaml 的 tech stack 拼接 + 版本锁定）
  │     注意：此 venv 与学生全局环境隔离，后续打包进交付物保证复现
  │
  ├─ 对 DAG 每个 node：
  │   ├─ 1. 生成代码：读该 node 的 contract + resource_plan + spec.pitfalls
  │   │     用 Write 工具写 <node>.py 到 .homework/run_<id>/code/
  │   │
  │   ├─ 2. 调用执行器：Bash 跑 `hw-exec run-node --python <venv_python> --run-dir ... --node <node>`
  │   │     hw-exec 内部：subprocess.run([python, "code/<node>.py"])  # 使用 venv 的 Python
  │   │     ├─ exit 0 + 产物符合 contract → node.status = passed (A级) 或 passed_pending_b_judge (B级)
  │   │     ├─ exit ≠ 0 或产物不符合 contract → node.status = failed
  │   │     └─ 自动调 /term2img 截终端图，落 execution/traces/<node>__attempt<n>.png
  │   │
  │   ├─ 3. 若 failed：
  │   │     读 stdout/stderr → LLM 分析原因 → 改 .py 代码 → 回到步骤 2（≤ fix:3 次）
  │   │     若 3 次仍失败 → give_up → 进 supply_halt 或 sense_default_trade
  │   │
  │   └─ 4. 若 passed：hw-exec commit-facts 落 facts_patch_<node>.json 分片
  │        继续下一个 node
```

**关键职责边界**：
- `hw-orchestrator` **生成代码、修代码**（LLM 推理）
- `hw-exec` **只跑子进程 + 机器校验**（确定性）
- `hw-exec` **不判 B 级**——tier=B 的 node 标 `passed_pending_b_judge`，真过由 P6 auditor subagent 判
- 代码错误是 **LLM 的 bug**，不是执行器的 bug——`hw-exec` 永远不会"修代码"，只报告"第几行什么 check 没通过"

#### 11.2.1 用例 / 接口契约

**定位**:唯一自写代码层。不推理、不生成代码、不改代码、不判对错(只按 A 准则机器判定)。坏代码回 LLM 改,它只跑子进程 + 抓 stdout/exitcode + 按契约机器校验产物 + 状态落盘。

**CLI 形态**(子进程,主 agent 经 Bash 调用,拿回严格 JSON):
```
hw-exec <prepare|run-node|verify-node|commit-facts|status> --python <venv_python> --run-dir <run_dir> [...]
```
- `--python`：指向作业 venv 的 python.exe（如 `.homework/run_<id>/.venv/Scripts/python.exe`），`run-node` 用此 Python 跑作业代码。hw-exec 自身用 `plugin-venv/` 的 Python（shebang 指向），与作业代码环境隔离。
- `--run-dir`：统一指向 `.homework/run_<id>/`。五个 verb 输出严格 JSON,exit 0=执行器自身正常,非 0=执行器自身故障。

**阶段契约 schema**(所有权:方案权产生,本层只读只校验):

```yaml
contract:
  contract_id: ct_etl
  tier: A
  tier_source: inherited_from_stage|overridden_by_planability
  runtime: {mem_limit: "2GB", wall_s: 300}
  artifacts:
    - path: output/etl_long.parquet
      checks:
        - {id: row_min, type: row_count, op: ">=", value: 2000}
        - {id: cols, type: col_set, expected: [datetime, station, pollutant, value]}
        - {id: no_dup, type: dup_key, keys: [datetime, station, pollutant]}
        - {id: size, type: assert_expr, expr: "size_gb('output/etl_long.parquet') >= 0.05"}
  stdout_asserts:
    - {id: chunked, pattern: "分块", required: true}
  exit_must_be: 0
  default_artifact:               # 新增(P2-7):sense_trade 默认产物来源
    kind: placeholder_plotly|static_template
    generator: orchestrator_llm|preset_file
    path: output/default_basemap.png
```

**check 原子集**(A 准则、机器秒判):`row_count / col_set / col_range / dup_key / json_path / file_exists / file_size_min / stdout_assert / exit_match / assert_expr`(白名单函数 `size_gb/min_date/row_count/col_range`)。

**node.status 枚举**(新增 P0-5b `passed_pending_b_judge` 显式态):
`pending | running | retriable | passed | passed_pending_b_judge | failed | given_up | supply_needed`
- `passed`:tier=A 且全部 check 过。
- `passed_pending_b_judge`:tier=B(无机器 contract),本层只跑+留痕,"真过"由 P6 B 级 judge 判。主 agent 据此在 P5→P6 间不当完全 passed 推进。
- `supply_needed`:某 check 依赖外部资源(如高德 key 未配)→ 不计 retry 预算、不假装配 key、转 supply_halt 回写 state.yaml。

**commit-facts 改写权(P0-3)**:执行器**不直接写 `facts.json`**。`commit-facts` verb 把每个 passed node 的 `facts_patch`(数字 + 产物 digest + trace PNG 路径)落为 `<run_dir>/execution/facts_patch_<node>.json` 分片。P7 Facts 派生层是 facts.json 唯一合并写者,从所有分片合并并校验 schema。

**term2img 留痕**(执行器自动,非侵入):`run-node` 子进程结束、契约校验前,执行器调 `term2img` skill 把 stdout 渲染成 PNG 落 `.homework/run_<id>/execution/traces/<node>__attempt<n>.png`。失败不判 node 挂,仅记 `term2img.ok=false`。trace 路径写进该 node 的 `facts_patch`,由 P7 收编进 `facts.artifacts.<node>.trace_png`。

**重试预算(P1-3 分维度)**:
```
EXECUTOR retry (per node): {cold: 1, fix: 3}   # 共 4 次尝试
确定性循环防护: 同一 node 同一 failed_check 连续2次相同 → detected_loop → give_up
```
give_up 后主 agent 据 §6 两档:有默认 → sense_default_trade + `run-node --force-adopt-default`(标 `source:default_trade` 进 facts,诚信标注);无默认 → supply_halt 回写 state.yaml。

#### 11.2.2 对应 Claude Code 形态

- **小执行器**:`C:\Code\HomeWork-PipeLine\.homework\hw-exec` 单文件 Python CLI(`subprocess` + `pyarrow`/`pandas` 读产物 + check 原子 + `os.replace` 原子状态)。**非 subagent、非 skill**——被主 agent 经 Bash 当工具调用的确定性进程。hw-exec 自身的 Python 依赖（pydantic、pyarrow、pandas）装在插件根 `plugin-venv/`，shebang 指向 `plugin-venv/Scripts/python`，与学生作业 venv 完全隔离。
- **作业 venv**：由 hw-orchestrator 在 P5 入口创建（`.homework/run_<id>/.venv/`），根据 plan.yaml 的 tech stack 拼接 requirements.txt 并 pip install。`hw-exec run-node --python <venv_python>` 用此 Python 跑作业代码。venv 随交付物打包以保证复现。
- **term2img skill**:现成 `/term2img` skill,执行器内部当工具调(非 LLM 调)。
- **B 档边界**:`tier:B` 节点执行器不机器判,标 `passed_pending_b_judge`,真过交 P6 的 auditor subagent(LLM 实例本身判)。

### 11.3 Auditor 达标自检

#### 11.3.1 用例 / 接口契约

**定位(混合体,切两半)**:A 级 verify(assert/tool/presence)= 执行器内 verifier 子系统,纯机器零 LLM;B 级 verify(llm_judge)+ 编排汇总 = 逻辑 subagent。

**verify DSL**(对齐 §4 `spec.constraints[].verify`,逐 type 一句可跑)。三种 A 级 type:`assert`(受限 namespace 求值 / `check` 映射 `check_<name>.py`)、`tool`(subprocess 看 exitcode + combine all/any)、`presence`(文件存在 + 正则匹配,GBK 编码探测直击空气质量 pitfalls)。每条 A 级 verify 只产结构化 `Verdict`,不返散文。

**B 级 llm_judge(P0-5a 预算自洽)**:auditor subagent 即 LLM 实例本身判,输入 `rubric + artifacts`(Read/markitdown 转 md 再读),输出结构化 JSON。
- `mode: single`(默认):判 1 次。当 `|total - pass_threshold| < dispute_margin`(落争议带)→ 升级 `majority_3`,3 个独立 judge(同模型不同温度/seed)取多数。
- `mode: majority_N`(默认 N=3):固定判 3 次取多数。
- 单 B 项总调用上限 = 3(single 路径判 1 次,进争议带补 2 次凑满 3;或直接 majority_3 = 3 次)。甩尽仍 disputed → 按 §1.3 保守优先**偏判 fail** 进红格,三判 rationale 全存 evidence。
- 网搜默认关闭,仅某 rubric 条需外部参照时单次网搜。
- **B 级 fail ≠ 机器 fail**:语义"该 soft/bonus 未拿留痕勾对",进黄/红格,不阻断主交付(hard 才是闸)。

**rubric 来源**:§4 Spec 抽取器抽 soft/bonus 时自动展开(单句→3-5 条带 weight/scale 的 criterion),不算二次人工输入(沿用 §4.1 纯 LLM 抽不扰用户)。

**红绿清单 + facts 镜像(P0-3,不直接写 facts)**:
- 独立清单:`red_green_checklist.yaml`(完整 evidence/rationale/多判留痕,答辩可拷产物)。
- 不直接 `json.dump` 进 facts.json。Auditor 产 `audit_patch.json`(每条 `id+status` + 分档统计 + 清单文件路径),交 P7 合并进 `facts.checklist.<constraint_id>.{status,evidence}` 与 `facts.provenance.checklist_path`。
- 清单路径进 `facts.artifacts.audit_checklist.path`(与 `facts.artifacts.dashboard_html` 同为"路径引用",命名空间收编)。

**Auditor→§6 供给桥(P0-2 字段补齐)**:pre_flight 的 `block_points[]`(A 级 verify 失败、属缺外部资源者)翻译成 supply item 时**必须补齐五项** `id/kind/why/steps/when_provided`(kind 由 verdict 推 dataset/source,steps 写"检查/重新提供 X",when_provided 写"重跑对应 stage"),不得半成品落 supply_checklist。每项带 `stage_id` 与 `trigger: auditor_pre_flight`,与闸2触发的(`trigger: gate2`)、执行器触发的(`trigger: executor`)区分但 resolved 语义一致。

**Auditor→方案筛选桥(P1-4 不回灌改 spec)**:`plan.yaml.relaxed_verify[]` 标记被 REJECT 栈对应的 verify 块为 `skip`。Auditor 读 `plan.relaxed_verify`,遇 `relaxed: rejected_in_plan` 则跳过该 verify 并备注 `plan.decisions[...]`。spec.yaml 在 P0 后冻结只读,不被 plan 回灌改写。

**状态机三时点**(由 auditor subagent 编排,落盘可重建):
| 时点 | 跑哪些 | fail 处置 |
|---|---|---|
| pre_flight | presence/tool 不依赖中间产物者、DATA_SOURCE 可达性 | 缺外部资源→翻译 supply_halt 回写 state.yaml;代码风格→回执行器改码 |
| inline | 与 DAG node 产物映射的 assert/check(TS_SPLIT↔split产物、R²↔model产物) | fail→执行段选择1:喂 stdout 给 LLM 改 node 重跑(per node fix≤3) |
| post_run | 全量复跑 + B 级 llm_judge + 汇总清单 | hard A fail→`blocked_delivery:true`,阻断正式交付 |

**续跑状态**：Auditor 不再独立写 `auditor_state.yaml` 为顶层真相。其检查进度作为 state.yaml 的子节点内联，主 agent 只读顶层 state.yaml。在同一对话内，auditor subagent 据子状态只补未跑项，不重跑已 pass 项。

#### 11.3.2 对应 Claude Code 形态

- **`.claude/agents/auditor.md`**:逻辑 subagent,读 §4 verify 块 + §7.1 plan.relaxed_verify + §5 verifiability_report;调执行器暴露的 A 级 verifier 工具接口 `run_assert/run_tool/run_presence`;跑 B 级 llm_judge(LLM 实例自身判);汇 `red_green_checklist.yaml` + `audit_patch.json`;缺外部资源型 fail 翻译 supply_halt 回写 state.yaml。
- **小执行器内 verifier 子系统**:`.homework\executor\verifiers\`(`assert_runner.py/tools_runner.py/presence.py/probes.py/check_*.py/tool_registry.yaml/presence_domains.yaml`)。是 `hw-exec` 的一部分,3 个工具接口对 auditor subagent 暴露。非 subagent。
- **A 级 verifier 失败两类语义**(用 retarget 标识,否则混):`verify_fail`(产物不满足约束)→ 改**作业代码**重跑;`verifier_runtime_error`(pyarrow 解析/GBK 异常)→ 改**verifier 脚本**或换 probe。两类都 ≤3,但用 `retarget: homework_code|verifier_script` 标识。

### 11.4 Packer 打包交付

#### 11.4.1 用例 / 接口契约

**定位**:系统末端。消费 `facts.json` + 文档派生产物 + LLM 生成的代码 + 数据产物 + 作业 venv，汇入 `delivery/<course>/` 目录即为最终交付物。

**v1/v2 边界(P2-6 显式分版)**:
- v1:汇入"派生文档 + spec/五件契约快照 + LLM 生成的代码 + 作业 venv + 数据产物 + 执行留痕"到 delivery 目录。
- v2:增加完整排版渲染文档交付。
- v1 不因 `facts.artifacts.dashboard_html.path` 不存在(DASH_HTML 在 v1 未构建)而常态触发挡下——v1 的 deliverable 核对走"v1 仅核对 outline 类产物存在",完整渲染产物核对留 v2。避免把"v1 不做执行"误升为"v1 必断点"。

**产出**:`delivery/<course>/`（目录即交付物，学生直接提交此目录给老师）。不需要额外打 zip——文件夹本身结构清晰、可直接查看、老师也方便逐文件批改。

**汇入 delivery 目录的内容**:
- LLM 生成的代码（从 `.homework/run_<id>/code/` 复制）——这是学生提交的核心，老师要看的
- 文档派生产物（README / 实验报告 / 答辩稿 / ppt 模板渲染结果）
- **作业 venv**（`.homework/run_<id>/.venv/` → `delivery/<course>/venv/`——老师打开目录后直接 `venv/Scripts/python main.py` 可跑）
- 已校验数据产物（parquet/gexf，附 `.manifest.json`：行数/列数/SHA256/生成命令）
- 文档引用的图（路径不存在→打包期挡下）
- 五件 spec 契约快照（老师可对照原始要求核查）
- 执行留痕（term2img 截图、stdout/exitcode——证明代码真的跑过）
- `README_FIRST.md`（说明 venv 用法、"一键运行"命令、环境说明）
- `PROVENANCE.yaml`（学术诚信标注：哪些 AI 生成、哪些人工提供）

**不汇入（留获取脚本）**:
- 大原始数据可脚本下载者（空气质量 13230 CSV/2.12GB 只留 `download_data.py` + `data/README.md`）
- 含真实密钥的文件（占位化处理，key 替换为 `os.environ.get(...)`）

> **venv 大小说明**：典型数据科学 venv（pandas + numpy + scikit-learn + matplotlib）约 300-500 MB。交付目录根放 `README_FIRST.md` 说明"直接运行 `venv/Scripts/python main.py`"。

**密钥占位化**:`config.py` 汇入时把 `AMAP_API_KEY = "e80a..."` 占位化为 `os.environ.get("AMAP_API_KEY", "<见 REPRODUCE.md>")`。替换键集来自 `supply_checklist.items[]` 中 `kind=api_key`。

**学术诚信标注 `PROVENANCE.yaml`**(机械可判):
```yaml
integrity_summary:
  ai_generated_share: 0.96        # 结构计数:ai_generated* 项 / 全 deliverables(机械可复算)
  human_supplied_items: [amap_api_key]
  default_trade_items: [visualize]
deliverables:
  - id: DASH_HTML
    path: report/.../dashboard.html
    origin: ai_generated|ai_generated_default_trade|human_supplied|human_revised
    tool_chain: ["01_fetch_data.py", "04_network_build.py"]
    facts_refs: [stops, edges, rings]
    default_trade: false
runtime_evidence:
  - stage: fetch
    stdout_hash: "<sha256>"
    exit_code: 0
    screenshot: runtime_artifacts/screenshots/term_01_fetch.png
```
`human_revised` 仅当用户显式声明(policy:默认不信人改)。诚信声明块由模板引擎注入每文档首段,引用 `facts.provenance.ai_generated_share`(路径缺失→渲染期挡下,不写假数字)。

**REPRODUCE.md 模板**:环境锁定（指向自带 venv 的 python）+ 数据脚本(断点续传) + 密钥步骤(从 supply_checklist 复制) + 每脚本产物校验 + 方案决策留痕(节选 plan.decision_trace)。简介：用 `venv/Scripts/python main.py` 直接运行，无需 pip install。

**与 spec.deliverables 对齐核对(缺即挡,沿用 §7.2 渲染期挡下)**:
```
1. 读 spec.deliverables → 期望集 D_exp
2. 对每个 d: 文件在磁盘→checksum 入 manifest;不在→missing_deliverables
3. 报告/图中每个 facts 引用→校验引用 path 存在(复用 §7.2 渲染期检查结果)
4. missing_deliverables 非空→退出码非零,落 deliverable_gaps.yaml,不标 COMPLETED,输出断点清单
5. 核对通过→delivery 目录完整,标 COMPLETED
```
对空气质量痛点:`air_quality_mega_dashboard.html` 文档列但文件不在→全期挡下落 `deliverable_gaps.yaml`,与 §7.2 渲染期路径检查形成双保险。

**默认产物来源(P2-7)**:sense_trade 节点的 contract `default_artifact`(§11.2.1)给 `kind/generator/path`,使默认产物有可机验 `file_exists` check。

**退出码**:0=全对齐;非零=缺交付物,落 `deliverable_gaps.yaml` + `packer_status.json`,提示"检查 <stage> 为何未落 <path>"。

#### 11.4.2 对应 Claude Code 形态

- **`.claude/agents/packer.md`**:末端 subagent。用 `shutil.copytree`/`os.rename` 把各产物汇入 `delivery/<course>/`。读 facts.json/spec/verifiability_report/supply_checklist/plan + 文档派生产物 + LLM 生成的代码 + 数据产物 + 执行留痕目录 + 作业 venv。落盘 `delivery/<course>/`（目录）、`PROVENANCE.yaml`、`REPRODUCE.md`、`README_FIRST.md`、`_meta/{manifest.yaml,checksums.sha256,deliverable_gaps.yaml,packer_status.json}`。

### 11.5 端到端状态机

#### 11.5.1 用例 / 接口契约

**9 阶段串行**(对齐 §3,顺序不变):
```
P0 SPEC_EXTRACT → P1 RESOURCE_PLANNER → P2 ADJUDICATION(闸1)
  → P3 SUPPLY_GATE(闸2) → P4 PLAN_SELECTOR → P5 EXECUTOR
  → P6 AUDITOR → P7 FACTS_DERIVE → P8 PACKER → COMPLETED
```

**每阶段 4 状态**：`ENTERING | RUNNING | COMPLETED | PAUSED`。`PAUSED` 状态表示遇到 supply_halt——主 agent 打印待补给清单，在对话中等待用户提供（API key / 账号 / 数据路径），用户提供后继续从当前阶段推进。`RUNNING` 不可信（进程崩了）——重新进入阶段时降级回 `ENTERING` 做幂等重跑。

**v1/v2 line（已定: v1 包含真执行）**:P5 EXECUTOR / P6 AUDITOR / P8 PACKER 三关状态机形态所有版本一致；v1 内部内容：P5 真执行（LLM 生成代码 → `hw-exec` run-node 子进程跑 → 抓 stdout/exitcode → verify-node 机器校验 → term2img 截图留痕）、P6 全量 A 级机器自检 + B 级 single 轻 judge、P8 打包完整产物 zip + PROVENANCE + REPRODUCE。v2 增加：无人值守全自动（supply_halt 零人工介入）、完整文档渲染（PDF 排版）、多课程类型 spec 扩展。

**状态文件单一真相源 `state.yaml`**:
```yaml
state.yaml:
  version: 0.1
  run_id: 20260627-busnet-001
  docx_path: "..."
  current_phase: ADJUDICATION        # P0..P8
  phase_status: ENTERING
  attempt: 2
  phases:
    SPEC_EXTRACT: {status: COMPLETED, artifact: artifacts/spec.yaml, schema_pass: true}
    RESOURCE_PLANNER: {status: COMPLETED, artifact: artifacts/resource_plan.yaml}
    ADJUDICATION:
      status: ENTERING
      attempt: 2
      budget_used:                   # P1-3 分维度
        enum_rounds: 0              # §1.3 ≤2
        judge_per_candidate: 0      # §1.3 ≤1
        web_searches_triggered: 0   # §1.3 ≤1(非默认)
    SUPPLY_GATE: {status: PENDING}
    PLAN_SELECTOR: {status: PENDING}
    EXECUTOR:
      status: PENDING
      substate_ref: execution/state.json   # 执行器子状态指针(非顶层真相)
    AUDITOR:
      status: PENDING
      substate: {pre_flight_done: [], inline_done: {}, post_run_done: []}  # 内联非独立文件
    FACTS_DERIVE: {status: PENDING}
    PACKER: {status: PENDING}
  breakpoints:
    sense_default_trade:            # 出生即 resolved=true,不停机
      batch: [visualize]
      resolved: true
      rationale_ref: artifacts/verifiability_report.yaml#breakpoints_summary.sense_default_trade
    supply_halt:                     # P0-4 多源统一 batch
      batch:
        - id: amap_api_register
          stage_id: fetch
          trigger: gate2             # gate2|executor|auditor
          kind: api_key
          resolved: false            # 出生=false,等用户在对话中提供后变 true
          supplied_items:
            - id: amap_api_key
              provided_at: null
              provided_value_ref: env:AMAP_API_KEY   # 不存明文
  retry_budget:                      # P1-3 分维度
    SPEC_EXTRACT:   {phase_attempts: 3}
    RESOURCE_PLANNER: {phase_attempts: 2}
    ADJUDICATION:   {enum_rounds: 2, judge_per_candidate: 1, web_searches: 1}   # 对齐 §1.3
    PLAN_SELECTOR:  {phase_attempts: 3}
    EXECUTOR:       {per_node: {cold: 1, fix: 3}}
    AUDITOR:        {phase_attempts: 2, verify_fail: {per_node_fix: 3, retarget: homework_code}, verifier_error: {per_node: 3, retarget: verifier_script}, b_judge: {max_calls: 3}}
    FACTS_DERIVE:   {phase_attempts: 2}
    PACKER:         {phase_attempts: 1}
  auto_mode: full                    # supply_halt 非空时实为 scaffold_with_breakpoints
  decision_trace_log: logs/decision_trace.md
```

**两类断点精确语义**：

| 维度 | sense_default_trade | supply_halt |
|---|---|---|
| 谁给答案 | 系统给默认产物 | 用户给真实值 |
| 是否暂停 | **不停**（resolved 出生 true） | **暂停**（phase_status=PAUSED，打印清单，等用户在对话中提供） |
| 用户交互 | 无 | 用户直接在对话里粘贴 key/路径/数据，主 agent 收到后继续 |
| 状态机 | 标注+放行，不停留 | PAUSED，等用户回复后→ENTERING→RUNNING→COMPLETED |

**断点产生多源统一协议(P0-4)**：闸2 / 执行器 / Auditor 任一阶段可产出 supply_halt item 追加进 `breakpoints.supply_halt.batch`(每项带 `stage_id + trigger`)。主 agent 在推进到依赖该资源的阶段前统一检查 batch。`supply_needed` 类失败不计 retry 预算，直接转 supply_halt。

**闸2分类事实来源(P0-1 方案A)**:裁决器把 Resource Planner 的 `closure/default_available` 事实**折叠进 `verifiability_report.breakpoints_summary` 每条记录**(如 `supply_halt: [{stage_id: amap_api_register, closure: outside, has_default: false}]`)。闸2纯函数 `classify_breakpoints()` 只读 verifiability_report,不回读 resource_plan.yaml。

**事实源(P0-3,P7 唯一写者)**:
```
facts.json:
  metrics: {lines, stops, edges, rings, r2_no2_bj, pca_pc1_ratio, ...}
  artifacts:
    <deliverable_id>: {path, digest, trace_png}
    dashboard_html: {path: "dashboard/air_quality_mega_dashboard.html"}
    audit_checklist: {path: "red_green_checklist.yaml"}
  checklist:
    <constraint_id>: {status, evidence}
  provenance:
    ai_generated_share: 0.96
    human_supplied_items: [amap_api_key]
    python_version: "3.11"
```

**编排机制**：
- 主 agent（Claude Code 自身）= 编排器。`/hw` SKILL.md 自包含全套编排指令（推进顺序、断点处理、重试规则）。
- `orchestrator_state.py`（确定性函数）：`create_run`（生成 run_id + 空 state.yaml）、`classify_breakpoints`（闸2分档）、`commit_phase`（写阶段完成状态）。纯 pydantic，无 daemon。
- 遇 supply_halt：主 agent 打印清单 → 对话暂停等用户提供 → 用户回复后主 agent 从 state.yaml 知道断点在哪 → 继续推进。不退出进程，不跨会话。

**失败重试 vs 断点暂停**：
- 失败重试：`phase_status=RUNNING` 时 node 失败，同进程内 `attempt<budget` → 修代码重跑。不退进程、不需用户介入。
- 断点暂停：`phase_status=PAUSED`，主 agent 在对话里等用户给供给。用户提供后 → 回 RUNNING 继续。整个在一个对话里完成。

#### 11.5.2 对应 Claude Code 形态

- **`.claude/skills/hw/SKILL.md`**：`/hw` 入口，自包含完整编排指令。
- **小执行器 `orchestrator_state.py`**：确定性状态机外壳（create_run / classify_breakpoints / commit_phase），纯函数 + pydantic，无 daemon。

### 11.6 插件落地映射总览

> **§11.6 已根据 Claude Code 插件实际机制（v2.1+）修正。** 关键差异：`commands/` 目录已废弃，slash command 改用 `skills/` 实现；插件需 `.claude-plugin/plugin.json` 元数据清单；subagent 的 system prompt 须自包含（不继承主 agent 上下文）；可利用 hooks、`background`、`isolation: worktree` 等机制。

#### 11.6.1 仓库结构（marketplace 格式）

本仓库是一个 Claude Code **marketplace**——根目录有 `.claude-plugin/marketplace.json`，`plugins/homework-pipeline/` 是插件实体。

```
HomeWork-PipeLine/                   # 仓库根 = marketplace
├── .claude-plugin/
│   └── marketplace.json             # marketplace 清单（name/version/plugins[]）
├── plugins/
│   └── homework-pipeline/           # 插件实体（参与运行时）
│       ├── .claude-plugin/
│       │   └── plugin.json          # 插件元数据（name/version/description）
│       ├── .claude/
│       │   ├── agents/              # 8 个薄 subagent 定义（Markdown + YAML frontmatter）
│       │   │   ├── spec-extractor.md
│       │   │   ├── resource-planner.md
│       │   │   ├── adjudicator.md
│       │   │   ├── plan-selector.md
│       │   │   ├── auditor.md
│       │   │   ├── facts-deriver.md
│       │   │   ├── packer.md
│       │   │   └── hw-orchestrator.md
│       │   └── skills/
│       │       └── hw/
│       │           └── SKILL.md     # /hw 入口 skill
│       ├── .homework/               # 自写代码层（确定性 CLI + 状态机 + verifier）
│       │   ├── hw-exec
│       │   ├── orchestrator_state.py
│       │   └── executor/
│       │       └── verifiers/
│       └── plugin-venv/             # hw-exec 自身 Python 依赖，与学生作业 venv 隔离
├── DESIGN.md                        # 开发者设计文档（不参与运行时）
├── CLAUDE.md                        # 项目记忆（不参与运行时）
├── test-cases/                      # 精简测试用例（开发阶段验证用）
│   ├── 公交网络分析/doc/课程要求.md
│   └── 空气质量预测/doc/课程要求.md + data/
├── 公交网络分析/                     # 测试样本/夹具（只读，学生真实完成的作业）
└── 空气质量预测/                     # 测试样本/夹具（只读，学生真实完成的作业）
```

**安装方式**（开发阶段）：
```bash
# 1. 注册本地 marketplace
claude plugin marketplace add C:\Code\HomeWork-PipeLine

# 2. 安装插件（文件被复制到 ~/.claude/plugins/cache/，独立于仓库）
claude plugin install homework-pipeline@homework-dev

# 3. 更新（改代码后）
claude plugin marketplace update homework-dev
claude plugin update homework-pipeline
```

插件安装后文件位于 `~/.claude/plugins/cache/homework-dev/homework-pipeline/`——**与开发仓库完全独立**。仓库推 GitHub 后其他人只需 `claude plugin marketplace add <repo-url>` 即可安装。

#### 11.6.2 组件映射表（v1 精简版）

| 块 | Claude Code 形态 | 实体路径 | 性格 |
|---|---|---|---|
| **Marketplace 元数据** | `.claude-plugin/marketplace.json` | `.claude-plugin/marketplace.json`（已建） | JSON 清单 |
| **插件元数据** | `.claude-plugin/plugin.json` | `plugins/homework-pipeline/.claude-plugin/plugin.json`（已建） | JSON 清单 |
| **主编排** | **主 agent 自己**（无独立 subagent） | 通过 `/hw` SKILL.md 自包含编排指令 | LLM 推理，skill 内嵌全部管线规则 |
| Spec 抽取器(P0) | subagent（薄 prompt） | `plugins/homework-pipeline/.claude/agents/spec-extractor.md`（待建） | LLM 推理,schema 由主 agent 在 task 中传递 |
| Resource Planner(P1) | subagent（薄 prompt） | `plugins/homework-pipeline/.claude/agents/resource-planner.md`（待建） | LLM 推理,只读核验 |
| 裁决器(P2) | subagent（薄 prompt） | `plugins/homework-pipeline/.claude/agents/adjudicator.md`（待建） | LLM 推理+Tavily 例外,预算数字写死 |
| 闸2分类(P3) | 小执行器函数 | `plugins/homework-pipeline/.homework/orchestrator_state.py::classify_breakpoints` | 纯函数,无 LLM |
| 方案筛选(P4) | subagent（薄 prompt） | `plugins/homework-pipeline/.claude/agents/plan-selector.md`（待建） | LLM 推理,不改 spec |
| 执行沙箱(P5) | subagent(代码生成 + venv) + 小执行器 CLI | `plugins/homework-pipeline/.claude/agents/hw-orchestrator.md` + `plugins/homework-pipeline/.homework/hw-exec`(Bash 调) | LLM 写代码+创建 venv,机器跑代码 |
| 作业 venv(P5 内) | hw-orchestrator 创建 | 学生目录 `.homework/run_<id>/.venv/`，汇入交付目录 | 每作业独立环境,保证复现 |
| term2img 留痕(P5 内) | skill | 现成 `/term2img`,由 hw-exec 内部调 | 工具 |
| Auditor(P6) | subagent（薄 prompt）+ 执行器 verifier | `plugins/homework-pipeline/.claude/agents/auditor.md` + `plugins/homework-pipeline/.homework/executor/verifiers/*.py` | LLM 编排 B 级 + 机器校验 A 级 |
| Facts 派生(P7) | subagent（薄 prompt） | `plugins/homework-pipeline/.claude/agents/facts-deriver.md`（待建） | LLM 推理 + 模板渲染 |
| Packer(P8) | subagent（薄 prompt） | `plugins/homework-pipeline/.claude/agents/packer.md`（待建） | LLM + copytree/rename |
| 触发入口 | 1 个 skill | `plugins/homework-pipeline/.claude/skills/hw/SKILL.md`（待建） | `/hw <docx>` 启动，遇到断点在对话里等用户补给后继续 |
| 项目记忆 | CLAUDE.md | `CLAUDE.md`（已存在，不参与运行时） | 开发者文档 |

**总形态**：编排 = **主 agent 自己**（`/hw` SKILL.md 自包含全部指令）；逻辑层(Spec/Resource Planner/裁决器/Auditor B级/方案筛选/Facts 派生/Code Orchestrator/Packer) = 8 个**薄 subagent**；A 级机器判定 + 子进程驱动 = 小执行器(`.homework/hw-exec.py` + `orchestrator_state.py` + `executor/verifiers/`)；留痕 = 现成 `/term2img` skill；入口 = 1 个 skill(`/hw`)；分发 = marketplace（`.claude-plugin/marketplace.json` + `plugins/homework-pipeline/.claude-plugin/plugin.json`）。

#### 11.6.3 关键修正说明（对比初版设计）

| 初版假设 | 修正后 | 原因 |
|---|---|---|
| `commands/` 目录放 slash command | `skills/` 目录放 SKILL.md | Claude Code v2.1+ 已将 commands 机制合并进 skills，`commands/` 已废弃 |
| 无需插件元数据 | 需 `.claude-plugin/marketplace.json` + `plugins/<name>/.claude-plugin/plugin.json` | marketplace 分发标准格式 |
| subagent 可依赖主 agent 上下文 | subagent prompt 必须自包含 | Claude Code subagent 启动时不继承主 agent system prompt，只拿到自己的 frontmatter + body + 任务描述 + 基本环境信息 |
| 未使用 hooks | 利用 hooks 做自动化校验 | `PreToolUse` hook 可在 hw-exec 调用前校验 state.yaml；`SessionStart` 可注入项目约定 |
| 未利用 `background`/`isolation` | P5 执行段可用 `background: true` + `isolation: worktree` | 多个 node 可并行后台跑；git worktree 隔离避免文件冲突 |

#### 11.6.4 Subagent Prompt 设计总则（必读）

Claude Code 中每个 subagent 启动时**不继承主 agent 的完整 system prompt**（包括 CLAUDE.md、DESIGN.md）。Subagent 只收到：
1. 其 `.md` 文件的 YAML frontmatter 配置
2. 其 `.md` 文件的 Markdown body（= system prompt）
3. 主 agent 委托时给的任务描述
4. 基本环境信息（工作目录、平台）

**因此每个 subagent 的 prompt 必须自包含**——把该阶段所需的所有 DESIGN.md 规约、schema 定义、判定规则、预算约束都写进 body 里。各 agent prompt 设计要点见 §12。

### 11.7 P0/P1 矛盾修法应用一览

| 编号 | 矛盾 | 修法 | 落地处 |
|---|---|---|---|
| P0-1 | 闸2分类事实来源未进 verifiability_report | 方案A:裁决器折叠 closure/default_available 进 `breakpoints_summary` 每条记录,闸2纯函数只读 verifiability_report | §11.5 breakpoints_summary + §11.0 增订 §5.1 |
| P0-2 | supply_checklist.items[] 多源字段不齐 | 5 项必填 `id/kind/why/steps/when_provided`,auditor block_points 补齐 + 带 stage_id/trigger | §11.3.1 Auditor→§6 桥 |
| P0-3 | facts.json 多写者 + 命名冲突 | facts.json 唯一合并写者 = P7;执行器产 facts_patch 分片、auditor 产 audit_patch;子结构统一 `metrics/artifacts/checklist/provenance` | §11.2.1 commit-facts、§11.3.1、§11.5 |
| P0-4 | supply_halt 多源触发但门只查闸2 | 多源统一 batch + 带 stage_id/trigger;每阶段进入前统一 assert resolved | §11.5 断点多源协议 + state.yaml breakpoints |
| P0-5a | auditor B 判预算自相矛盾 | 统一"单 B 项总调用≤3",删除"判1+复判3=上限3轮"含糊 | §11.3.1 B 级预算自洽 |
| P0-5b | B 档节点中间态衔接空缺 | node.status 增 `passed_pending_b_judge` | §11.2.1 node.status 枚举 |
| P0-5c | state_machine v1 与 auditor v1 B 判口径不一 | 统一 v1 line:P6 v1 跑 single 轻 judge+A 级静态自检,v2 完整 | §11.5 v1/v2 line |
| P1-1 | tier 来源不在一处 | contract.tier 增 `tier_source` 留痕(inherited/overridden) | §11.2.1 contract schema |
| P1-2 | runtime_artifacts/run 根三处不一 | run 根统一 `.homework/run_<id>/`,traces 统一 `execution/traces/` | §11.2.1、§11.5 |
| P1-3 | retry budget 单位混用 | 分维度 budget(phase_attempts/per_node/per_candidate/web),auditor 失败带 retarget | §11.5 retry_budget schema |
| P1-4 | plan 回灌改 spec 违反 P0 冻结 | 不改 spec,plan 增 `relaxed_verify[]`,auditor 读 plan 跳过 | §11.3.1 Auditor→方案筛选桥 |
| P1-5 | verifiability_report tier 三键并存 | 统一 `resolved_tier` 为唯一最终档,initial_tier/tier_after_search 留痕 | §11.0 增订 §5.1 |
| 续跑根 | 状态文件多根无主从 | state.yaml 为顶层唯一真相,exec state.json/auditor 子状态为指针/内联 | §11.5 state.yaml substate_ref/substate |
| P2-5b | contract 数值来源互相推诿 | resource_plan 增 `constants[]`,plan_selector 据此写 check op/value | §11.1.1 constants 字段 |
| P2-6 | packer v1 越界打包完整文档 | v1/v2 显式分版,v1 打 outline+快照 | §11.4.1 v1/v2 边界 |
| P2-7 | sense_trade 默认产物来源未定义 | contract 增 `default_artifact`(kind/generator/path),可机验 file_exists | §11.2.1 default_artifact |

### 11.8 仍待用户拍板的开放问题

1. **未覆盖的 4 个逻辑层块的内部设计**:本次 5 块不含 `spec_extractor`(P0)、`adjudicator`(P2 多轮自推理重述实现)、`plan_selector`(P4,contract check 数值来源 ↔ Resource Planner `constants[]` 的对账约定)、`facts_deriver`(P7,facts.json 唯一合并写者 + 渲染期路径检查的真执行)。§11 已为它们留位并定义接口契约,但块内设计需另补。
2. **`auto_mode` 字段消费方**:现仅 state_machine 产、除答辩留痕外无人消费。若需运行态分支(supply_halt 非空时自动切部分自动模式),需明示消费方。
3. **B 级"独立 judge"实现**:首轮用同模型+温度/seed 抖动 vs 真多实例——成本/稳定性取舍待定(不阻塞开码,majority_3 路径两者皆可)。
4. **presence domain 别名表 / tool registry 谁维护**:`executor/verifiers/presence_domains.yaml` 与 `tool_registry.yaml` 别名失配=审计盲区,schema 校验归谁(建议归 spec_extractor 在抽 verify 块时校验 `in`/`tool` 名在 registry)待定。
5. **v1 是否真跑 P5 执行** → **已定：v1 包含真执行**。LLM 生成代码 → `hw-exec` 子进程跑 → 机器校验产物 → term2img 截图。P5/P6/P8 全开，不推迟到 v2。对应 DESIGN.md 改动见 §2.1（五件可交付物，新增真执行产物）、§2.2（v2 内容缩减为无人值守/完整文档渲染/多课程类型）、§11.5（v1/v2 line 更新）。

> 注:本节 §11.8 之后仍有以下文档级一致性需在开码时同步落地——§5.1 的 `tier/tier_after_search/resolved_tier` 字段统一为 `resolved_tier`(见 §11.0 第1条)、`breakpoints_summary` 增折叠字段(见 §11.0 第1条+§11.7 P0-1)。建议开 §10 第4步裁决器时即按 §11.0 修法落到 `verifiability_report.yaml` schema。

---

## 12. Subagent Prompt 设计（精简版）

> **架构决策（v1 修正）**：主 agent 本身就是编排器。用户运行 `/hw` 后，主 agent（有 CLAUDE.md → DESIGN.md 在 context 里）负责全程编排——读 state.yaml、决定下一步、派 subagent、处理结果、推进管线。**Subagent 是"干活的工人"而非"独立的思考者"**：每个 subagent 的 prompt 只写它的职责 + 输出格式 + 硬约束；主 agent 在每次委托时把具体的 schema、上下文、要求写入任务描述。Subagent 的核心价值是**保持主 agent 上下文干净**——把噪声（大文件读取、网搜、代码执行）隔离在独立 context 里，主 agent 只收回结果摘要。

### 12.1 设计原则（三条）

1. **薄 prompt，厚委托**：Subagent prompt 10-30 行足矣。具体要做什么、产出的 schema 长什么样、边界条件是什么——主 agent 在每次 `Agent` 调用的 task description 里给。Subagent prompt 只管"你是谁"和"你不能做什么"。
2. **Subagent 不知道管线**：Subagent 不知道 P0-P8 的阶段顺序、不知道前序阶段的产物、不知道后续阶段的存在。它只收到主 agent 给的输入文件路径 + 任务描述 + 输出路径。
3. **Schema 随任务传递**：主 agent 从 DESIGN.md 里取对应阶段的 schema 定义，嵌入 task description。Subagent prompt 自身不硬编码 schema（除非是极其稳定的核心 schema）。

### 12.2 八个 Subagent 的精简定义

#### `spec-extractor.md`
```
你是 Spec 抽取器。输入课程文档(docx/md)，输出 spec.yaml。
职责：从课程要求中抽结构化约束——硬约束(A级可机判)、软约束(B级 LLM-judge)、交付物清单、陷阱、技术栈要求。
硬约束：不确定的约束按最严档假设。禁止问用户"你有没有 XX 约束"——不确定就走保守兜底。
输出完整性自检：扫原文中"明显指向某类约束但 spec 未生成对应字段"的信号，记入 missing_signals 并降 extraction_confidence。
工具：Read, Bash(markitdown), Grep
```

#### `resource-planner.md`
```
你是 Resource Planner。输入 spec.yaml，输出 resource_plan.yaml。
职责：分析每个环节需要什么资源——数据在哪、API 怎么拿、要不要人参与。产出资源桩(不执行下载/申领)。
你做的事：判 acquisition.mode(programmatic/human_in_loop/human_supply)、判 closure(inside/outside)、提取 constants[]。
你不做的事：不判 A/B/C(那是裁决器)、不下 ADOPT/REJECT(那是方案筛选)、不执行任何下载或 key 申领。
保守准则：不确定时偏 supply_needed:true。网搜非默认——仅资源自身依赖外部信息确认才触发 1 次。
工具：Read, Bash(HEAD 探测 URL), Grep, Tavily(例外触发)
```

#### `adjudicator.md`
```
你是可验证性裁决器。输入 spec.yaml + resource_plan.yaml，输出 verifiability_report.yaml。
对每个 deliverable 的每个 stage，严格执行四步判定——不可跳步：

Step 1: E 能拿机器 pass/fail 反馈？→ 是 → A
Step 2: E 能用 LLM-judge / 结构化准则验证？→ 是 → B
Step 3: LLM 自行枚举把 E 重述为"语言可描述且可验证"的等价形式。
        枚举上限 2 轮，每轮每候选 LLM-judge 1 轮。
        Tavily 仅在某候选自身依赖外部信息时触发 1 次（非默认）。
        找到可验证路径 → 按路径判(A/B)；穷尽仍无 → C
Step 4: C 时能否给默认产物？能 → default_trade；不能 → supply_halt

保守优先：枚举不确定时偏判 C。
resource_plan 的 supply_needed/closure 是输入事实——你的工作是穷举降级路径绕开它，绕不开才入断点。
工具：Read, Tavily(例外触发)
```

#### `plan-selector.md`
```
你是方案筛选器。输入 spec.yaml + resource_plan.yaml + verifiability_report.yaml，输出 plan.yaml。
职责：候选技术栈 → 逐栈评估(硬约束过滤→软约束排序→最简优先)→DAG 节点设计→每节点 contract。
你必须为每个 REJECT 的候选给出淘汰理由(evidence 字段)——这些是答辩素材。
不改写 spec.yaml(spec 冻结只读)。被 REJECT 栈的 verify 块标 relaxed_verify。
contract 的 check op/value 从 resource_plan.constants[] 取。
工具：Read
```

#### `auditor.md`
```
你是 Auditor。A 级机器校验走执行器的 verifier 子系统(Bash 调 hw-exec run_assert/run_tool/run_presence)。你负责编排 A 级检查 + 执行 B 级 LLM judge。
三时点：pre_flight(不依赖中间产物的检查)→inline(与 DAG node 产物映射)→post_run(全量复跑+汇总)。
B 级 judge 预算：单 B 项总调用 ≤3。默认 single(1 次)，落争议带升级 majority_3(3 次取多数)。甩尽仍 disputed → 保守偏判 fail 进红格。
B 级 fail ≠ 机器 fail——不阻断主交付(hard 才是闸)。
pre_flight 缺外部资源→翻译 supply_halt(五项必填)回写 state.yaml。读 plan.relaxed_verify 跳过 REJECT 栈的 verify。
不直接写 facts.json——只产 red_green_checklist.yaml + audit_patch.json。
工具：Read, Bash(调 hw-exec verifier 接口)
```

#### `hw-orchestrator.md`
```
你是 Code Orchestrator（P5 执行段主控）。输入 plan.yaml + resource_plan.yaml + spec.pitfalls + run_id。
你的完整职责：
1. 创建作业 venv：python -m venv .homework/run_<id>/.venv → pip install -r requirements.txt
   （requirements.txt 从 plan.yaml 的 tech stack 拼接，版本锁定）
2. 按 DAG 顺序遍历每个 node：
   a. 读 node contract + resource_plan + pitfalls
   b. 用 Write 工具生成 code/<node>.py
   c. Bash 调 `hw-exec run-node --python <.venv python> --run-dir ... --node <node>`
   d. 读 hw-exec 返回的 JSON
   e. passed → commit-facts → 继续下一个 node
   f. failed → 读 stdout/stderr → 分析原因 → 改 .py 代码 → 回到 c（per node 最多 fix 3 次）
   g. 3 次仍 failed → give_up → 回写 state.yaml（sense_default_trade 或 supply_halt）
   h. passed_pending_b_judge → 继续下一个 node，真过由 P6 Auditor 判
3. 全部 node 完成后报告 P5 COMPLETED
你不做的事：不判 A/B/C、不判 B 级验证、不直接写 facts.json（只产 facts_patch 分片）。
工具：Write, Bash(调 hw-exec + pip), Read
```

#### `facts-deriver.md`
```
你是 Facts 派生器。你是 facts.json 的唯一合并写者。
输入：各 node 的 facts_patch_<node>.json 分片(来自 P5)+audit_patch.json(来自 P6)+spec.deliverables。
输出：facts.json(metrics/artifacts/checklist/provenance 四子结构)+派生文档(README/实验报告/答辩稿/ppt)。
渲染期路径检查：facts 引用的产物路径若文件不存在→渲染期报错，不生成假文档。
facts 与产物不一致→标记差异不静默覆写。
工具：Read, Write, Bash(校验文件)
```

#### `packer.md`
```
你是 Packer。输入 facts.json + 所有产物文件，汇入 delivery/<course>/ 目录即为最终交付物。
汇入规则：
- LLM 生成的代码（`.homework/run_<id>/code/` → `delivery/<course>/code/`）——核心交付物，老师要看
- 文档派生产物（README/实验报告/答辩稿/ppt）
- 作业 venv（`.homework/run_<id>/.venv/` → `delivery/<course>/venv/`，保证开箱可跑）
- 已校验数据产物（附 manifest.json）+ 执行留痕截图 + spec 契约快照
- PROVENANCE.yaml + REPRODUCE.md + README_FIRST.md
不汇入：大原始数据可脚本下载者（留 download_data.py）、含真实密钥的文件（先占位化）。
对齐核对：spec.deliverables vs 磁盘 → 缺即挡下(deliverable_gaps.yaml)，不标 COMPLETED。
不需要打 zip——delivery/<course>/ 目录本身就是最终交付物。
工具：Read, Write, Bash(copytree/rename)
```

### 12.3 Skill：hw
```markdown
---
name: hw
description: 启动 HomeWork-PipeLine。输入课程要求文档，在当前目录全自动产出可交付作业。
---

当用户运行 /hw <docx> 时：

1. 用 markitdown 将 docx 转为 Markdown
2. 调 orchestrator_state.create_run(docx) 创建 .homework/run_<id>/state.yaml
3. 按以下顺序逐阶段推进（P0 到 P8）：
   P0: Agent(spec-extractor) 抽取 spec.yaml
   P1: Agent(resource-planner) 规划资源
   P2: Agent(adjudicator) 裁决可验证性
   P3: Bash(orchestrator_state classify_breakpoints)
   P4: Agent(plan-selector) 选方案+DAG+写contract
   P5: Agent(hw-orchestrator) 创建venv→生成代码→hw-exec run-node→看结果→修→重跑
   P6: Agent(auditor) 达标自检
   P7: Agent(facts-deriver) 合并 facts.json
   P8: Agent(packer) 打包交付
4. 每阶段完成后调 orchestrator_state.commit_phase 更新 state.yaml

遇到 supply_halt（缺少 API key/数据/账号）时：
  系统：不可自动获取。需要你提供（清单）：
  <列出逐条待办，含为什么需要、怎么获取、提供了放哪>
  请逐一提供后我继续推进。
关键：不要退出进程。在对话里等用户回复后继续从当前阶段推进。
全部 COMPLETED 后打印交付物位置。
```