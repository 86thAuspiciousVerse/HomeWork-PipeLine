"""orchestrator_state.py — HomeWork-PipeLine 确定性状态机外壳。

本文件落地 DESIGN.md §11.5.1 的 state.yaml 全量结构 + 闸2 纯函数 + 阶段提交函数。
设计要点：
- 9 阶段串行：P0 SPEC_EXTRACT → P1 RESOURCE_PLANNER → P2 ADJUDICATION →
  P3 SUPPLY_GATE → P4 PLAN_SELECTOR → P5 EXECUTOR → P6 AUDITOR →
  P7 FACTS_DERIVE → P8 PACKER → COMPLETED
- 每阶段 4 状态：ENTERING | RUNNING | COMPLETED | PAUSED
- 两类断点：sense_default_trade（出生 resolved=true，不停机） /
            supply_halt（出生 resolved=false，phase_status=PAUSED）
- 纯函数 + pydantic，无 daemon。
- 续跑单一真相源：state.yaml。

依赖：仅 Python 标准库 + pydantic。YAML 优先 PyYAML，缺失退 JSON 落 .yaml。

v2 simplified：executor/verifiers/ 与 hw-exec 已删除。验证由 LLM 在现场自写脚本完成。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import datetime as _dt
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# YAML 读写层：优先 PyYAML，缺失则 fallback 到 JSON（仍以 .yaml 扩展名落盘）。
# ---------------------------------------------------------------------------

try:  # pragma: no cover - import 探测，无副作用
    import yaml as _yaml  # type: ignore

    _HAS_YAML = True
except Exception:  # pragma: no cover
    _HAS_YAML = False


def _dump_yaml(data: Dict[str, Any], path: Path) -> None:
    """把 dict 落盘为 YAML；无 PyYAML 时退化为 JSON 写入同扩展名。"""
    if _HAS_YAML:
        text = _yaml.safe_dump(
            data,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    else:
        # fallback：JSON 落 .yaml，文件头注明这是 JSON 兜底。
        text = "# !! PyYAML 不可用，本文件实际为 JSON 兜底格式 !!\n" + json.dumps(
            data, ensure_ascii=False, indent=2
        )
    _atomic_write(path, text)


def _load_yaml(path: Path) -> Dict[str, Any]:
    """从盘读回 dict；无 PyYAML 时按 JSON 解析（跳过兜底注释行）。"""
    raw = path.read_text(encoding="utf-8")
    if _HAS_YAML:
        loaded = _yaml.safe_load(raw)
    else:
        raw_strip = raw
        if raw_strip.startswith("# !! PyYAML 不可用"):
            # 去掉首行 JSON 兜底注释
            raw_strip = "\n".join(raw_strip.splitlines()[1:])
        loaded = json.loads(raw_strip)
    return loaded if isinstance(loaded, dict) else {}


def _atomic_write(path: Path, text: str) -> None:
    """原子写：先写临时文件再 os.replace，避免半写状态被读到。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


# ---------------------------------------------------------------------------
# 阶段枚举与常量
# ---------------------------------------------------------------------------

# 9 阶段（DESIGN.md §11.5.1），顺序即推进顺序。COMPLETED 为终态占位非阶段名。
PHASES: List[str] = [
    "SPEC_EXTRACT",        # P0
    "RESOURCE_PLANNER",    # P1
    "ADJUDICATION",        # P2 闸1
    "SUPPLY_GATE",         # P3 闸2
    "PLAN_SELECTOR",       # P4
    "EXECUTOR",            # P5
    "AUDITOR",             # P6
    "FACTS_DERIVE",        # P7
    "PACKER",              # P8
]
PHASE_SET = set(PHASES) | {"COMPLETED"}

PhaseStatus = Literal["ENTERING", "RUNNING", "COMPLETED", "PAUSED"]
# 各阶段记录的 status 在 4 状态之外还含 PENDING（§11.5.1 phases.X.status: PENDING）。
PhaseRecordStatus = Literal["PENDING", "ENTERING", "RUNNING", "COMPLETED", "PAUSED"]
TriggerKind = Literal["gate2", "executor", "auditor"]

# ---------------------------------------------------------------------------
# 断点子结构（DESIGN.md §11.5.1 breakpoints / §6 / §11.7 P0-4 多源协议）
# ---------------------------------------------------------------------------


class SuppliedItem(BaseModel):
    """supply_halt.batch[].supplied_items[]：用户已补给的条目（不存明文值）。"""

    id: str
    provided_at: Optional[str] = None     # ISO8601 字符串，未提供时为 null
    provided_value_ref: Optional[str] = None  # 例 "env:AMAP_API_KEY"，不存明文


class SupplyHaltBatchItem(BaseModel):
    """supply_halt.batch[] 每项（§11.5.1 + §11.7 P0-4 多源协议 + §6 五项必填）。

    多源协议：闸2/执行器/Auditor 任一阶段都可追加 item，故带 trigger 标注来源；
    每阶段进入前主 agent 统一断言 batch 全 resolved。

    §6 + P0-2 五项必填（id/kind/why/steps/when_provided）原设计稿散落在 supply_checklist.yaml，
    但本系统不产 supply_checklist.yaml 这个独立文件——供给事实的唯一持久化落点就是本结构
    （被打入 state.yaml breakpoints.supply_halt.batch[]）。故把 why/obtain_steps/when_provided
    显式建模进来，避免 pydantic 在 model_validate 时静默丢弃这些字段（reload 后凭空消失）。
    obtain_steps 用 strings[] 承接（§6 steps 的语义），命名取 obtain_steps 与 resource_plan.yaml
    的 obtain_steps 字段对齐，便于 resource-planner / auditor / executor 产 item 时复用同一口径。
    """

    id: str
    stage_id: str          # 关联的 spec.deliverables[].stages
    trigger: TriggerKind = "gate2"  # gate2 | executor | auditor
    kind: str = "api_key"  # api_key|dataset|account|credential_file|...
    # §6 五项必填中的三项人读字段（id/kind 已在上）：
    why: Optional[str] = None            # 为什么必需（含"裁决已确认无默认值可替且无闭外降级路径"）
    obtain_steps: List[str] = Field(default_factory=list)  # 人读获取步骤
    when_provided: Optional[str] = None  # 补给后续行方式（如"重跑 fetch 阶段即可续行"）
    resolved: bool = False
    supplied_items: List[SuppliedItem] = Field(default_factory=list)


class SenseDefaultTrade(BaseModel):
    """感官型断点：给默认产物继续跑（出生 resolved=true，不停机）。"""

    batch: List[str] = Field(default_factory=list)  # stage_id 列表（轻量标记）
    resolved: bool = True
    rationale_ref: Optional[str] = None
    # 例 "artifacts/verifiability_report.yaml#breakpoints_summary.sense_default_trade"


class SupplyHalt(BaseModel):
    """供给型断点：停等人补（出生 resolved=false，phase_status=PAUSED）。"""

    batch: List[SupplyHaltBatchItem] = Field(default_factory=list)
    resolved: bool = False


class Breakpoints(BaseModel):
    """顶层 breakpoints（§11.5.1）。"""

    sense_default_trade: SenseDefaultTrade = Field(default_factory=SenseDefaultTrade)
    supply_halt: SupplyHalt = Field(default_factory=SupplyHalt)


# ---------------------------------------------------------------------------
# retry_budget 子结构（DESIGN.md §11.5.1 + §1.3 降级预算 + P1-3 分维度）
# ---------------------------------------------------------------------------


class AdjudicationBudget(BaseModel):
    """P2 ADJUDICATION 对齐 §1.3：枚举降级候选上限 2 轮、每轮每候选 judge 1 轮、
    网搜仅在候选依赖外部信息才触发 1 次（非默认）。"""

    enum_rounds: int = 2           # §1.3 ≤2
    judge_per_candidate: int = 1   # §1.3 ≤1
    web_searches: int = 1          # §1.3 ≤1（非默认）


class PhaseAttemptsBudget(BaseModel):
    """通用阶段预算：按阶段重试次数封顶。"""

    phase_attempts: int = 2


class ExecutorBudget(BaseModel):
    """P5 EXECUTOR：per_node 分 cold（冷启 1 次）/ fix（修码重跑 3 次）。
    P5 已简化——hw-orchestrator (LLM) 自己跑+验证+修码，不再调 hw-exec。"""

    per_node: Dict[str, int] = Field(default_factory=lambda: {"cold": 1, "fix": 3})


class RetargetBudget(BaseModel):
    """带 retarget 的失败预算：先在 target 上重试，再回溯改源。"""

    per_node: int = 3
    per_node_fix: int = 3
    retarget: str = "unknown"  # 例 "homework_code" / "verifier_script"


class AuditorBudget(BaseModel):
    """P6 AUDITOR：分 verify_fail / verifier_error / b_judge 三维度。"""

    phase_attempts: int = 2
    verify_fail: Dict[str, Any] = Field(
        default_factory=lambda: {
            "per_node_fix": 3,
            "retarget": "homework_code",
        }
    )
    verifier_error: Dict[str, Any] = Field(
        default_factory=lambda: {"per_node": 3, "retarget": "verifier_script"}
    )
    b_judge: Dict[str, Any] = Field(default_factory=lambda: {"max_calls": 3})


# 各阶段RetryBudget 子结构用 Any 容器承接（schema 形状见上列子结构 + §11.5.1）。
# retry_budget 整体以 dict 承载以便不同阶段键不同，但提供 _default_retry_budget
# 出厂值，确保 create_run 写出的 state.yamI 与 §11.5.1 逐字段一致。


def _default_retry_budget() -> Dict[str, Any]:
    """出厂 retry_budget（对齐 §11.5.1 retry_budget 块逐行）。"""
    return {
        "SPEC_EXTRACT": PhaseAttemptsBudget(phase_attempts=3).model_dump(),
        "RESOURCE_PLANNER": PhaseAttemptsBudget(phase_attempts=2).model_dump(),
        "ADJUDICATION": AdjudicationBudget().model_dump(),
        "PLAN_SELECTOR": PhaseAttemptsBudget(phase_attempts=3).model_dump(),
        "EXECUTOR": ExecutorBudget().model_dump(),
        "AUDITOR": AuditorBudget().model_dump(),
        "FACTS_DERIVE": PhaseAttemptsBudget(phase_attempts=2).model_dump(),
        "PACKER": PhaseAttemptsBudget(phase_attempts=1).model_dump(),
    }


# ---------------------------------------------------------------------------
# 阶段记录 / 子状态（DESIGN.md §11.5.1 phases.*）
# ---------------------------------------------------------------------------


class PhaseRecord(BaseModel):
    """单阶段记录。字段集为所有阶段并集；缺省字段留空，写入时按需填充。"""

    status: PhaseRecordStatus = "PENDING"
    artifact: Optional[str] = None       # 该阶段产物的 run 根相对路径
    schema_pass: Optional[bool] = None   # SPEC_EXTRACT 专用：spec.yaml schema 自检
    attempt: Optional[int] = None
    budget_used: Optional[Dict[str, int]] = None  # ADJUDICATION 用：已消耗的分维度预算
    substate_ref: Optional[str] = None   # EXECUTOR 子状态指针（v2 simplifed：无独立 executor/state.json）
    substate: Optional[Dict[str, Any]] = None  # AUDITOR 内联子状态（非独立文件）


RunPhases = Dict[str, PhaseRecord]

# ---------------------------------------------------------------------------
# 顶层 RunState（state.yaml 单一真相源，DESIGN.md §11.5.1）
# ---------------------------------------------------------------------------


class RunState(BaseModel):
    """state.yaml 的顶层模型（§11.5.1）。"""

    version: str = "0.1"
    run_id: str
    docx_path: str
    current_phase: str = "SPEC_EXTRACT"   # P0..P8，初始为 P0
    phase_status: PhaseStatus = "ENTERING"
    attempt: int = 0                       # 顶层计数（每阶段另有各 phase 记录）
    phases: RunPhases = Field(default_factory=dict)
    breakpoints: Breakpoints = Field(default_factory=Breakpoints)
    retry_budget: Dict[str, Any] = Field(default_factory=_default_retry_budget)
    auto_mode: str = "full"                # supply_halt 非空时实为 scaffold_with_breakpoints
    decision_trace_log: str = "logs/decision_trace.md"
    # run_root 不进 state.yaml（它由 run_id 派生），内存里持有便于函数操作。
    run_root: Optional[str] = Field(default=None, exclude=True)

    # path 字段（运行时辅助，不落盘）
    state_path: Optional[str] = Field(default=None, exclude=True)


# 模型补定义（Py3.10 下 Literal/Dict 前向引用需显式 rebuild，否则模型未完全定义）。
AdjudicationBudget.model_rebuild()
PhaseAttemptsBudget.model_rebuild()
ExecutorBudget.model_rebuild()
RetargetBudget.model_rebuild()
AuditorBudget.model_rebuild()
SuppliedItem.model_rebuild()
SupplyHaltBatchItem.model_rebuild()
SenseDefaultTrade.model_rebuild()
SupplyHalt.model_rebuild()
Breakpoints.model_rebuild()
PhaseRecord.model_rebuild()
RunState.model_rebuild()


# ---------------------------------------------------------------------------
# 目录结构与 run_id 生成
# ---------------------------------------------------------------------------


def _homework_root() -> Path:
    """返回当前工作目录下的 .homework 根（学生作业目录所在）。"""
    return Path.cwd() / ".homework"


def _run_root(run_id: str) -> Path:
    return _homework_root() / run_id


def _gen_run_id() -> str:
    """生成 run_id：run_<YYYYMMDD>-<NNN>（§0 例 run_20260627-001）。

    NN 按当日已存在的 run 目录数 +1 递增，竞争宽松（单学生串行）。"""
    date_tag = _dt.datetime.now().strftime("%Y%m%d")
    root = _homework_root()
    n = 1
    if root.exists():
        for d in root.iterdir():
            if d.is_dir() and d.name.startswith(f"run_{date_tag}-"):
                n += 1
    return f"run_{date_tag}-{n:03d}"


def _make_run_dirs(run_root: Path) -> None:
    """创建 .homework/run_<id>/{artifacts,execution/traces,code}（DESIGN.md §0 + §11.5）。"""
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "execution" / "traces").mkdir(parents=True, exist_ok=True)
    (run_root / "code").mkdir(parents=True, exist_ok=True)
    # logs 目录给 decision_trace_log 用。
    (run_root / "logs").mkdir(parents=True, exist_ok=True)


def _init_phases() -> RunPhases:
    """各阶段初始化为 PENDING，AUDITOR 带默认子状态内联。"""
    phases: RunPhases = {}
    for p in PHASES:
        rec = PhaseRecord(status="PENDING")
        if p == "AUDITOR":
            rec.substate = {
                "pre_flight_done": [],
                "inline_done": {},
                "post_run_done": [],
            }
        elif p == "ADJUDICATION":
            rec.status = "PENDING"
            rec.budget_used = {
                "enum_rounds": 0,
                "judge_per_candidate": 0,
                "web_searches_triggered": 0,
            }
        phases[p] = rec
    return phases


# ---------------------------------------------------------------------------
# 纯函数 1：create_run
# ---------------------------------------------------------------------------


def create_run(docx_path: str) -> RunState:
    """生成 run_id，创建 run 目录树，写入空 state.yaml，返回 RunState。

    出生态：current_phase=SPEC_EXTRACT、phase_status=ENTERING、各阶段 PENDING、
    breakpoints 两档出生默认（sense_default_trade.resolved=true /
    supply_halt.resolved=false 且 batch 空）。
    """
    docx_path = str(Path(docx_path).resolve())
    run_id = _gen_run_id()
    run_root = _run_root(run_id)
    _make_run_dirs(run_root)

    state = RunState(
        run_id=run_id,
        docx_path=docx_path,
        current_phase="SPEC_EXTRACT",
        phase_status="ENTERING",
        attempt=0,
        phases=_init_phases(),
        breakpoints=Breakpoints(),
        retry_budget=_default_retry_budget(),
        auto_mode="full",
        decision_trace_log="logs/decision_trace.md",
        run_root=str(run_root),
        state_path=str(run_root / "state.yaml"),
    )
    _persist(state)
    return state


# ---------------------------------------------------------------------------
# 纯函数 2：classify_breakpoints（闸2，§11.5 P0-1 方案A）
# ---------------------------------------------------------------------------


def _load_verifiability_report(
    source: Union[str, Path, Dict[str, Any]]
) -> Dict[str, Any]:
    """接受 path 或已加载 dict，返回 reports dict。只读 breakpoints_summary。"""
    if isinstance(source, dict):
        return source
    p = Path(source)
    if not p.exists():
        raise FileNotFoundError(f"verifiability_report 不存在: {p}")
    return _load_yaml(p)


def classify_breakpoints(verifiability_report) -> Dict[str, Any]:
    """闸2 纯函数（§11.5 P0-1 方案A）。

    输入：verifiability_report.yaml 的路径，或已加载的 dict。
    只读其 `breakpoints_summary`（裁决器已折叠 Resource Planner 的
    closure/default_available 事实进每条记录），据此分两档：
      - sense_default_trade：出生 resolved=true（给默认继续跑），phase 不停。
      - supply_halt：出生 resolved=false，若非空则触发 phase_status=PAUSED。
    不回读 resource_plan.yaml（保纯函数）。不打扰用户。
    返回 dict：{
        "sense_default_trade": {"batch": [...], "resolved": True, "rationale_ref": ...},
        "supply_halt": {"batch": [...], "resolved": False},
        "phase_status": "ENTERING" | "PAUSED",
        "auto_mode": "full" | "scaffold_with_breakpoints",
    }
    """
    report = _load_verifiability_report(verifiability_report)
    summary = report.get("breakpoints_summary") or {}

    # sense_default_trade：设计稿示例里为 stage_id 字符串列表。
    sdt_raw = summary.get("sense_default_trade") or []
    sdt_batch = [s if isinstance(s, str) else str(s.get("stage_id", s)) for s in sdt_raw]

    # supply_halt：每条携带 stage_id + closure + has_default（折叠自 Resource Planner）。
    sh_raw = summary.get("supply_halt") or []
    sh_batch: List[SupplyHaltBatchItem] = []
    for item in sh_raw:
        if not isinstance(item, dict):
            continue
        stage_id = item.get("stage_id") or item.get("id") or "unknown"
        item_id = item.get("id") or stage_id
        kind = item.get("kind") or "api_key"
        # 默认 trigger=gate2（本函数为闸2入口产出的批次）。
        trigger = item.get("trigger", "gate2")
        if trigger not in ("gate2", "executor", "auditor"):
            trigger = "gate2"
        # §6 五项：why 取裁决器折叠记录里的 rationale（若裁决器给了 reasoning 饰）；
        # obtain_steps/when_provided 在闸2纯函数层不可得（要求只读 verifiability_report，
        # 不回读 resource_plan），留空由后续 executor/auditor 追加同 id item 时补齐，
        # 或由主 agent 在打印待补给清单时从 resource_plan 映射补充。
        why = item.get("rationale") or item.get("why")
        sh_batch.append(
            SupplyHaltBatchItem(
                id=str(item_id),
                stage_id=str(stage_id),
                trigger=trigger,  # type: ignore[arg-type]
                kind=str(kind),
                why=str(why) if why is not None else None,
                obtain_steps=[
                    str(s) for s in item.get("obtain_steps", []) if isinstance(s, str)
                ],
                when_provided=(
                    str(item["when_provided"])
                    if isinstance(item.get("when_provided"), str)
                    else None
                ),
                resolved=False,
                supplied_items=[],
            )
        )

    sense_default_trade = SenseDefaultTrade(
        batch=sdt_batch,
        resolved=True,  # 出生 resolved=true，不停机
        rationale_ref="artifacts/verifiability_report.yaml#breakpoints_summary.sense_default_trade",
    )
    supply_halt = SupplyHalt(batch=sh_batch, resolved=(len(sh_batch) == 0))

    # auto_mode：supply_halt 非空 → scaffold_with_breakpoints
    auto_mode = "scaffold_with_breakpoints" if sh_batch else "full"
    phase_status = "PAUSED" if sh_batch else "ENTERING"

    return {
        "sense_default_trade": sense_default_trade.model_dump(),
        "supply_halt": supply_halt.model_dump(),
        "phase_status": phase_status,
        "auto_mode": auto_mode,
    }


# ---------------------------------------------------------------------------
# 纯函数 3：commit_phase
# ---------------------------------------------------------------------------


def _load_state(run_id: str) -> RunState:
    """从盘读回 RunState（失败抛错）。"""
    run_root = _run_root(run_id)
    state_path = run_root / "state.yaml"
    if not state_path.exists():
        raise FileNotFoundError(f"state.yaml 不存在: {state_path}")
    data = _load_yaml(state_path)
    state = RunState.model_validate(data)
    state.run_root = str(run_root)
    state.state_path = str(state_path)
    return state


def _persist(state: RunState) -> None:
    """把 RunState 原子落盘为 state.yaml。"""
    if not state.state_path:
        raise ValueError("RunState.state_path 未设置")
    # exclude 运行时辅助字段（run_root/state_path 已标 exclude=True）
    data = state.model_dump(mode="json")
    _dump_yaml(data, Path(state.state_path))


def commit_phase(state: RunState, phase: str, artifact: str) -> RunState:
    """把某阶段标 COMPLETED、写 artifact 路径、原子落盘。

    推进规则（§11.5.1）：
      - ENTERING → RUNNING → COMPLETED：正常推进。本函数把目标阶段直接置 COMPLETED
        并写 artifact。调用方在阶段实际开始时应先把 status 推到 RUNNING（由主 agent
        在 SKILL.md 编排；本函数幂等，认可任何前置状态）。
      - RUNNING 不可信（进程崩前停在 RUNNING）：重入时降级回 ENTERING 做幂等重跑。
        本函数处理 COMPLETED 提交：若目标阶段已 COMPLETED 且 artifact 一致，视为幂等
        成功直接返回；若 artifact 不同，覆盖更新（显式提交最新产物）。
      - PAUSED（supply_halt 未 resolved）：禁止提交，抛错——必须先 resolve 断点。
    """
    if phase not in PHASE_SET:
        raise ValueError(f"未知阶段: {phase}（合法: {PHASES} | COMPLETED）")

    # 顶层 current_phase 推进逻辑：若提交的是 current_phase，则推进 current_phase 到下一阶段。
    cur = state.phases.get(phase)
    if phase != "COMPLETED":
        # 断点检查：PAUSED 不可提交（§11.5.1）。
        if cur is not None and cur.status == "PAUSED":
            raise RuntimeError(
                f"阶段 {phase} 处于 PAUSED（supply_halt 未 resolved），禁止 commit"
            )
        if cur is None:
            cur = PhaseRecord(status="PENDING")
            state.phases[phase] = cur
        cur.status = "COMPLETED"
        cur.artifact = artifact

        # 若提交的是当前进行中的阶段，把 current_phase 推到下一未完成阶段。
        if phase == state.current_phase:
            state.current_phase = _next_pending_phase(state)
            state.phase_status = "ENTERING"
            state.attempt = 0
    else:
        # 显式提交 COMPLETED 终态。
        state.current_phase = "COMPLETED"
        state.phase_status = "COMPLETED"

    _persist(state)
    return state


def mark_entering(state: RunState, phase: str) -> RunState:
    """辅助：把阶段从 PENDING/RUNNING 推到 ENTERING（重入幂等用）。

    RUNNING 不可信 → 降级回 ENTERING（§11.5.1）。纯粹辅助函数，主 agent 也可直接
    通过 SKILL.md 编排推进；这里提供以便冒烟与重入场景。"""
    if phase not in PHASES:
        raise ValueError(f"未知阶段: {phase}")
    rec = state.phases.get(phase) or PhaseRecord(status="PENDING")
    if rec.status == "COMPLETED":
        return state  # 已完成不动
    rec.status = "ENTERING"
    state.phases[phase] = rec
    state.current_phase = phase
    state.phase_status = "ENTERING"
    _persist(state)
    return state


def resolve_supply_halt(state: RunState, item_id: str, value_ref: str) -> RunState:
    """辅助：用户在对话中提供了某 supply_halt item 的真实值后调用（§11.5.1）。

    value_ref 例 "env:AMAP_API_KEY"，不存明文。当 batch 全 resolved 后，
    supply_halt.resolved 翻 true、phase_status 由 PAUSED 回 ENTERING 继续推进。
    """
    batch = state.breakpoints.supply_halt.batch
    now_iso = _dt.datetime.now().isoformat()
    resolved_any = False
    for b in batch:
        if b.id == item_id:
            b.resolved = True
            b.supplied_items.append(
                SuppliedItem(
                    id=item_id,
                    provided_at=now_iso,
                    provided_value_ref=value_ref,
                )
            )
            resolved_any = True
    if not resolved_any:
        raise KeyError(f"supply_halt batch 中无 id={item_id}")
    # 全 resolved → 翻 supply_halt.resolved + 解 PAUSED。
    if all(b.resolved for b in batch):
        state.breakpoints.supply_halt.resolved = True
        if state.phase_status == "PAUSED":
            state.phase_status = "ENTERING"
    _persist(state)
    return state


def _next_pending_phase(state: RunState) -> str:
    """返回 phases 中第一个未 COMPLETED 的阶段；全完成返回 COMPLETED。"""
    for p in PHASES:
        rec = state.phases.get(p)
        if rec is None or rec.status != "COMPLETED":
            return p
    return "COMPLETED"


# ---------------------------------------------------------------------------
# CLI 入口（冒烟用）
# ---------------------------------------------------------------------------


def _cli_create_run(args: List[str]) -> int:
    if not args:
        print("用法: create-run <docx_path>", file=sys.stderr)
        return 2
    state = create_run(args[0])
    print(json.dumps(_state_summary(state), ensure_ascii=False, indent=2))
    return 0


def _cli_classify_breakpoints(args: List[str]) -> int:
    if not args:
        print("用法: classify-breakpoints <verifiability_report.yaml>", file=sys.stderr)
        return 2
    result = classify_breakpoints(args[0])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cli_commit_phase(args: List[str]) -> int:
    if len(args) < 3:
        print("用法: commit-phase <run_id> <phase> <artifact>", file=sys.stderr)
        return 2
    run_id, phase, artifact = args[0], args[1], args[2]
    state = _load_state(run_id)
    state = commit_phase(state, phase, artifact)
    print(json.dumps(_state_summary(state), ensure_ascii=False, indent=2))
    return 0


def _cli_show(args: List[str]) -> int:
    if not args:
        print("用法: show <run_id>", file=sys.stderr)
        return 2
    state = _load_state(args[0])
    print(json.dumps(_state_summary(state), ensure_ascii=False, indent=2))
    return 0


def _cli_mark_entering(args: List[str]) -> int:
    """CLI: 把指定阶段推到 ENTERING 状态（幂等，COMPLETED 不动）。"""
    if len(args) < 2:
        print("用法: mark-entering <run_id> <phase>", file=sys.stderr)
        return 2
    run_id, phase = args[0], args[1]
    state = _load_state(run_id)
    state = mark_entering(state, phase)
    print(json.dumps(_state_summary(state), ensure_ascii=False, indent=2))
    return 0


def _cli_get_run_info(args: List[str]) -> int:
    """CLI: 查询 run_root / state_path 等关键路径，供主 agent 委托 subagent 时注入。"""
    if not args:
        print("用法: get-run-info <run_id>", file=sys.stderr)
        return 2
    state = _load_state(args[0])
    info = {
        "run_id": state.run_id,
        "run_root": state.run_root,
        "state_path": state.state_path,
        "docx_path": state.docx_path,
        "current_phase": state.current_phase,
        "phase_status": state.phase_status,
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def _cli_resolve_supply_halt(args: List[str]) -> int:
    """CLI: 用户提供了某 supply_halt item 的真实值后调用，逐条 resolve。
    用法: resolve-supply-halt <run_id> <item_id> <value_ref>
    value_ref 形如 env:AMAP_API_KEY，不存明文。"""
    if len(args) < 3:
        print("用法: resolve-supply-halt <run_id> <item_id> <value_ref>", file=sys.stderr)
        return 2
    run_id, item_id, value_ref = args[0], args[1], args[2]
    state = _load_state(run_id)
    state = resolve_supply_halt(state, item_id, value_ref)
    print(json.dumps(_state_summary(state), ensure_ascii=False, indent=2))
    return 0


def _state_summary(state: RunState) -> Dict[str, Any]:
    """冒烟友好的人类可读摘要。"""
    return {
        "run_id": state.run_id,
        "docx_path": state.docx_path,
        "current_phase": state.current_phase,
        "phase_status": state.phase_status,
        "attempt": state.attempt,
        "phases": {
            p: (rec.status if (rec := state.phases.get(p)) else "PENDING")
            for p in PHASES
        },
        "breakpoints": {
            "sense_default_trade": {
                "batch": state.breakpoints.sense_default_trade.batch,
                "resolved": state.breakpoints.sense_default_trade.resolved,
            },
            "supply_halt": {
                "batch": [
                    {"id": b.id, "kind": b.kind, "trigger": b.trigger, "resolved": b.resolved}
                    for b in state.breakpoints.supply_halt.batch
                ],
                "resolved": state.breakpoints.supply_halt.resolved,
            },
        },
        "auto_mode": state.auto_mode,
        "run_root": state.run_root,
        "state_path": state.state_path,
    }


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(
            "用法: python orchestrator_state.py "
            "{create-run|mark-entering|classify-breakpoints|commit-phase|resolve-supply-halt|show|get-run-info} ...",
            file=sys.stderr,
        )
        return 2
    cmd, rest = argv[0], argv[1:]
    dispatch = {
        "create-run": _cli_create_run,
        "mark-entering": _cli_mark_entering,
        "classify-breakpoints": _cli_classify_breakpoints,
        "commit-phase": _cli_commit_phase,
        "resolve-supply-halt": _cli_resolve_supply_halt,
        "show": _cli_show,
        "get-run-info": _cli_get_run_info,
    }
    fn = dispatch.get(cmd)
    if fn is None:
        print(f"未知命令: {cmd}（合法: {' / '.join(dispatch)})", file=sys.stderr)
        return 2
    return fn(rest)


if __name__ == "__main__":
    raise SystemExit(main())