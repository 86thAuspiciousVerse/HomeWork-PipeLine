"""verifiers 包 —— HomeWork-PipeLine 小执行器的 A 级 verify 子系统。

定位（DESIGN.md §11.3.1）：A 级 verify（assert / tool / presence）= 执行器内的
纯机器零 LLM 子系统，是 hw-exec 的一部分，对 P6 auditor subagent 暴露三个接口：
    run_assert / run_tool / run_presence
（非 subagent、非 skill，被 hw-exec 与 auditor 经确定函数调用）。

每个 A 级 verify 只产结构化 Verdict（见 check_atoms.Verdict），不返散文。
A 级 verify 失败两类语义（DESIGN.md §11.3.2 retarget 标识，否则混淆一次性预算）：
    verify_fail            → 改【作业代码】重跑（retarget: homework_code）
    verifier_runtime_error → 改【verifier 脚本】或换 probe（retarget: verifier_script）

公共工具：原子写、YAML 读写（优先 PyYAML，缺失退回 JSON）、GBK/UTF-8 编码探测
（直击空气质量 pitfalls：中文 Windows 下 Excel 用 GBK 打开 CSV pandas 须 encoding=utf-8）。

依赖：仅 Python 标准库 + pydantic（plugin-venv）。YAML/parquet/pandas 均做能力探测
优雅降级（见 _load_yaml / read_tabular）。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# YAML 读写层（与 orchestrator_state.py 同一约定，重复实现以解耦）
# ---------------------------------------------------------------------------

try:  # pragma: no cover - import 探测
    import yaml as _yaml  # type: ignore

    _HAS_YAML = True
except Exception:  # pragma: no cover
    _HAS_YAML = False


def atomic_write(path: Path, text: str) -> None:
    """原子写：先写临时文件再 os.replace（避免半写被读到）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def dump_yaml(data: Dict[str, Any], path: Path) -> None:
    """落盘 YAML；无 PyYAML 时退化为 JSON 写入同扩展名（保冒烟可用）。"""
    if _HAS_YAML:
        text = _yaml.safe_dump(
            data, sort_keys=False, allow_unicode=True, default_flow_style=False
        )
    else:
        text = "# !! PyYAML 不可用，本文件实际为 JSON 兜底格式 !!\n" + json.dumps(
            data, ensure_ascii=False, indent=2
        )
    atomic_write(path, text)


def load_yaml(path: Path) -> Dict[str, Any]:
    """从盘读回 dict；无 PyYAML 时按 JSON 解析（跳过兜底注释行）。"""
    raw = path.read_text(encoding="utf-8")
    if _HAS_YAML:
        loaded = _yaml.safe_load(raw)
    else:
        raw_strip = raw
        if raw_strip.startswith("# !! PyYAML 不可用"):
            raw_strip = "\n".join(raw_strip.splitlines()[1:])
        loaded = json.loads(raw_strip)
    return loaded if isinstance(loaded, dict) else {}


# ---------------------------------------------------------------------------
# 编码探测（直击空气质量 pitfall：中文 Windows 默认 GBK，Excel 下 CSV 乱码）
# ---------------------------------------------------------------------------

# 探测顺序：UTF-8 优先（pandas 读中文 CSV 的推荐编码），失败回退 GBK/cp936。
_PROBE_ENCODINGS: Tuple[str, ...] = ("utf-8", "gbk", "gb18030", "utf-8-sig")


def read_text_with_probe(path: Path) -> Tuple[str, Optional[str]]:
    """多路编码探测读取文本，返回 (文本, 命中编码)。

    设计取舍：空气质量 CLAUDE.md 反复警告 Excel/GBK 下中文 CSV 乱码——故 verifier
    不硬编码单编码，按 UTF-8 → GBK → GB18030 → UTF-8-SIG 顺序探测。命中即返回，
    全失败抛 UnicodeDecodeError（交审计 retarget: verifier_script 处理，不静默吞）。
    """
    last_err: Optional[Exception] = None
    for enc in _PROBE_ENCODINGS:
        try:
            return path.read_text(encoding=enc), enc
        except UnicodeDecodeError as e:
            last_err = e
            continue
    raise last_err  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 对审计暴露的三接口（运行时由各 runner 模块提供实现，包级再导出便于 from ... import）
# ---------------------------------------------------------------------------

# 真正实现见 assert_runner.run_assert / tools_runner.run_tool / presence.run_presence。
# 这里延迟 import 避免循环，仅在调用时解析。
def run_assert(spec: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """执行 A 级 type=assert verify（DESIGN.md §11.3.1）。

    调用方式（auditor / hw-exec 内部）：
        from . import run_assert
        verdict = run_assert(constraint["verify"], context_dict)
    返回结构化 Verdict dict（verdict.passed / verdict.error_kind / ...）。
    """
    from .assert_runner import run_assert as _impl

    return _impl(spec, ctx)


def run_tool(spec: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """执行 A 级 type=tool verify（subprocess 看 exitcode + combine all/any）。"""
    from .tools_runner import run_tool as _impl

    return _impl(spec, ctx)


def run_presence(spec: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """执行 A 级 type=presence verify（文件存在 + 正则 + GBK 编码探测）。"""
    from .presence import run_presence as _impl

    return _impl(spec, ctx)