# HomeWork-PipeLine v0.1 使用反馈与改进建议

> 反馈来自一次完整的 9 阶段管线实战运行
> Run ID: `run_20260627-001` | 日期: 2026-06-27
> 场景: 城市空气质量趋势分析与预测建模（数据: 10 个 CSV，3 城市，6 天跨度）

---

## 一、总评

管线整体设计框架扎实可靠。9 阶段串行推进（P0→P8）+ 4 状态（ENTERING/RUNNING/COMPLETED/PAUSED）+ 两档断点（sense_default_trade / supply_halt）的逻辑非常清晰，在本次实战中零 supply_halt 的判断准确贯穿全程，闸1（ADJUDICATION）的 A/B/C 分级 + 保守偏判 C 再降级的策略合理有效。

以下列出实战中遇到的具体摩擦点和改进建议。

---

## 二、问题详述

### 问题 1: `mark_entering` 缺少 CLI 入口

**严重度**: 中

**现象**: `orchestrator_state.py` 中定义了 `mark_entering()` 函数（Python API），但 CLI 只暴露了 4 个子命令：

```
create-run | classify-breakpoints | commit-phase | show
```

每次进入新阶段前需要把状态从 PENDING/RUNNING 推到 ENTERING，但缺少对应的 CLI 命令。只能通过 Python 内联调用：

```bash
python -c "
import sys; sys.path.insert(0, '...')
from orchestrator_state import _load_state, mark_entering
state = _load_state('run_20260627-001')
state = mark_entering(state, 'SPEC_EXTRACT')
"
```

9 个阶段至少需要 9 次此类调用，显著增加了编排复杂度。

**建议**:

```python
# 在 dispatch 中增加
"mark-entering": _cli_mark_entering,

# 实现
def _cli_mark_entering(args: List[str]) -> int:
    if len(args) < 2:
        print("用法: mark-entering <run_id> <phase>", file=sys.stderr)
        return 2
    run_id, phase = args[0], args[1]
    state = _load_state(run_id)
    state = mark_entering(state, phase)
    print(json.dumps(_state_summary(state), ensure_ascii=False, indent=2))
    return 0
```

---

### 问题 2: Agent 产物落盘路径不一致

**严重度**: 中

**现象**: P0 SPEC_EXTRACT agent 产出的 `spec.yaml` 被写到了项目根目录 `C:\Code\test-hw\artifacts\spec.yaml`，而非 run_root 约定的 `C:\Code\test-hw\.homework\run_20260627-001\artifacts\spec.yaml`。

**根因**: Agent 不知道 `run_root` 的存在。SKILL.md 中说"提交 `artifacts/spec.yaml`（相对 run_root 的路径）"，但传给 agent 的 task prompt 里没有显式声明 run_root 的绝对路径，agent 自然以项目根目录作为工作基准。

**建议**:

1. 在每次 Agent 委托的 prompt 中，统一注入 run_root 的绝对路径：

```python
# 在 SKILL.md 编排层，每次传 task 时拼接：
prompt = f"""
工作根目录: {run_root}
产物目录: {run_root}/artifacts/
请将所有产出文件写入以上路径。
"""
```

2. 或者在 `orchestrator_state.py` 中增加一个 `get_run_info` 命令，主 agent 在委托前查询 run_root 并嵌入 prompt。

---

### 问题 3: `hw-exec` 未被实际使用

**严重度**: 中

**现象**: SKILL.md 中描述 P5 EXECUTOR 的流程为：

> Agent(hw-orchestrator)，它建 `.venv`、逐 node 写 code、Bash 调 `hw-exec run-node --python <.venv>/Scripts/python --run-dir <run_root> --node <node>`

但实际执行中，我手动写了每个 Python 脚本并直接用 Bash 运行：

```bash
".venv/Scripts/python.exe" "src/data_prep.py"
```

没有走 `hw-exec run-node` 的 contract check 流程，也自然没有更新 `execution/state.json` 里的 node.status。

**根因**: `hw-exec run-node` 需要预先写好每个 node 的 `contract_<node>.yaml`（从 plan.yaml 的 contract 映射过来），这一步在 SKILL.md 中没有被明确要求。另外 `hw-exec` 本身的 `prepare` 子命令仅创建了 execution 目录和空的 `state.json`，并没有自动从 plan.yaml 生成 contract 文件。

**建议**（二选一）:

- **方案 A（推荐）**: 将"生成 contract YAML + 调用 hw-exec"作为强制性要求写入 SKILL.md，并提供一个辅助脚本自动从 `plan.yaml` 生成 `contract_<node>.yaml`：

  ```python
  # 新增 CLI 命令
  python orchestrator_state.py gen-contracts <run_id>
  ```

- **方案 B**: 放松约束，允许主 agent 在简单场景下直接 Bash 执行 Python 脚本，`hw-exec` 仅用于需要原子校验的复杂 node。

---

### 问题 4: 中文路径（docx_path）编码问题

**严重度**: 低

**现象**: `create-run` 在对 `docx_path` 做 `str(Path(docx_path).resolve())` 后写入 state.yaml，中文文件名在 YAML 中显示为乱码：

```yaml
docx_path: "C:\\Code\\test-hw\\doc\\�γ�Ҫ��.md"
```

**根因**: Windows 终端/文件系统的编码交互。`Path.resolve()` 返回正确的 UTF-8 路径，但 state.yaml 序列化过程中某个环节丢失了编码信息。

**建议**:

1. 在 `_persist()` 中确保 `yaml.safe_dump` 使用 `allow_unicode=True`（当前已有这条，问题可能在别处）
2. 在 `create_run` 中对 `docx_path` 做显式编码检测和规范化：

   ```python
   docx_path = str(Path(docx_path).resolve())
   # 确保路径可逆回读
   assert Path(docx_path).exists(), f"路径不可达: {docx_path}"
   ```

3. state.yaml 落盘时增加一个 UTF-8 BOM 头以消除 Windows 记事本等工具的误判

---

### 问题 5: Windows GBK 终端编码冲突

**严重度**: 低（但频率高）

**现象**: 整个执行过程反复遇到：

```
UnicodeEncodeError: 'gbk' codec can't encode character '✓' in position ...
```

来源包括：
- Python 脚本中 `print("✓")`、`print("✗")`
- Plotly 图表的 `"μg/m³"` 在 to_html 的 JSON 序列化中
- 中文城市名在 print 语句中的终端输出

**根因**: Windows PowerShell 的默认编码是 GBK (cp936)，Python print 输出时无法处理 GBK 之外的 Unicode 码点。

**建议**:

1. 在 SKILL.md 中增加一条编码规范：

   > 所有 Python 脚本的 `print()` 输出一律使用 ASCII-safe 符号：
   > - `✓` → `[PASS]` 或 `[OK]`
   > - `✗` → `[FAIL]` 或 `[EXCLUDE]`
   > - 其他特殊 Unicode 符号同理

2. 在 requirement 或 make-venv 阶段主动设置环境变量：

   ```bash
   set PYTHONIOENCODING=utf-8
   ```

---

### 问题 6: `breakpoints_summary` 的格式约定不统一

**严重度**: 低

**现象**: `classify_breakpoints` 纯函数兼了两种 `sense_default_trade` 输入格式：

```python
# 格式 A：简单字符串列表
sdt_raw = ["stage_id_1", "stage_id_2"]

# 格式 B：dict 列表
sdt_raw = [{"stage_id": "xxx", "resource": "...", "rationale": "..."}]

# 兼容处理
sdt_batch = [s if isinstance(s, str) else str(s.get("stage_id", s)) for s in sdt_raw]
```

兼容代码是正确的，但增加了维护成本。

**建议**: 在 resource_plan.yaml 和 verifiability_report.yaml 的输出 Schema 中明确约定统一格式：

```yaml
# 统一为 dict 列表
breakpoints_summary:
  sense_default_trade:
    - stage_id: "prediction_model"
      resource: "prophet"
      rationale: "..."
      fallback: "..."
  supply_halt:
    - id: "xxx"
      stage_id: "xxx"
      kind: "api_key"
      why: "..."
      obtain_steps: [...]
```

---

### 问题 7: Pipeline 产出文件与 spec 的对照校验不够自动化

**严重度**: 低

**现象**: P8 PACKER 阶段，spec.deliverables 中列出了每个 stage 的 `outputs` 列表，但实际检查全部产出文件是否存在是靠我手动写了一段 Python 脚本。如果 deliverable 数量较多，人工检查容易遗漏。

**建议**: 在 `orchestrator_state.py` 中增加一个纯验证命令：

```bash
python orchestrator_state.py verify-deliverables <run_id>
```

自动读取 `state.yaml → phases → 各阶段的 artifact` 和 `artifacts/spec.yaml → deliverables[].outputs`，对比磁盘文件存在性和大小，输出红绿清单。

---

## 三、改进优先级建议

| 优先级 | 问题 | 影响 | 改动范围 |
|--------|------|------|----------|
| P0 | `mark_entering` 无 CLI | 每个阶段需绕道 Python API | orchestrator_state.py 增加 1 个子命令 |
| P0 | Agent 产物路径不一致 | 需手动搬文件 + 每次写全路径 | SKILL.md prompt 模板 + agent 委托注入 |
| P1 | `hw-exec` 未使用 | contract check 缺失，子状态未更新 | SKILL.md 强化约束 + gen-contracts CLI |
| P1 | Windows GBK 编码 | 反复打断执行流 | SKILL.md 规范 + PYTHONIOENCODING |
| P2 | docx_path 中文乱码 | 仅影响 state.yaml 可读性 | _persist 编码加固 |
| P2 | breakpoints_summary 格式 | 维护成本略高 | YAML schema 统一 |
| P2 | deliverable 验证自动化 | 依赖人工检查 | 新增 verify-deliverables CLI |

---

## 四、正面反馈

1. **9 阶段 + 4 状态 + 两档断点**的设计非常干净，推进逻辑一目了然。重入幂等（RUNNING→ENTERING 降级）的设计细节考虑周全。

2. **闸1（ADJUDICATION）的 A/B/C 分级 + 保守偏判 C 再降为 B** 的策略在本次实战中表现优秀。dashboard 的"双击浏览器打开"被保守判 C → 降为 HTML 结构完整性检查，验证了管线"不阻塞可降级项目"的设计意图。

3. **零 supply_halt 判断准确**。从 P0 规格提取阶段就识别出了"全部离线数据 + 本地训练 + 自包含 HTML"的特点，P1 Resource Planner 确认无外部依赖，P2 Adjudicator 合议一致——整个链路的信息传递没有断点。

4. **state.yaml 作为单一真相源**的理念很好。每个阶段的 artifact 路径、子状态引用、断点批次全部内聚在一个文件里，续跑时 reload 即可恢复。

5. **pydantic 模型 + 原子写**的基础设施很稳健，`_atomic_write` 避免了半写状态被读到的问题。

---

*反馈人: Claude Code (homework-pipeline 使用者)*
*反馈日期: 2026-06-28*
