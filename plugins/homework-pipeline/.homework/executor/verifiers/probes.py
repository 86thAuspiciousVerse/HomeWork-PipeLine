"""probes.py —— presence 域探测策略（DESIGN.md §11.3.1 presence_domains）。

每个 presence 域定义"判断某类产物/配置是否齐备"的确定性逻辑。本模块用纯 Python
hash 表承载域定义（非外部 yaml，避免 import PyYAML 在 verifier 子系统形成硬依赖——
状态层 orchestrator_state.py 才用 yaml）。扩展新域在此登记即可。

直击空气质量 pitfalls 的域：
  - converted_md：CLAUDE.md 反复引用但文件不存在 → probe 直接判 fail（verify_fail），
    交主 agent 翻译 supply_halt（DESIGN.md §8 文档-文件脱节案例）。
  - requirements_and_ci：验 requirements.txt 存在 + 版本锁定（CODE_STYLE 配套域）。

probe 返回 {ok: bool, detail: str, verifier_error?: bool}：
  - ok=false 且 verifier_error=False → verify_fail（改作业代码补产物）
  - ok=false 且 verifier_error=True  → verifier_runtime_error（改 probe/verifier 脚本）
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict

from . import read_text_with_probe


def _probe_converted_md(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """空气质量 converted.md 域：文件须存在（CLAUDE.md 引用但常缺 → 触发挡下）。"""
    run_dir = Path(ctx["run_dir"])
    cand = run_dir / "converted.md"
    if cand.exists():
        return {"ok": True, "detail": f"converted.md 存在: {cand}"}
    # 也可能在 doc/ 子目录
    alt = run_dir / "doc" / "converted.md"
    if alt.exists():
        return {"ok": True, "detail": f"converted.md 存在: {alt}"}
    return {"ok": False, "detail": "converted.md 不存在（文档-文件脱节，转 supply_halt）"}


def _probe_requirements_and_ci(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """CODE_STYLE 配套域：requirements.txt 存在且每行有版本锁定（==/>=/~=/>=）。"""
    run_dir = Path(ctx["run_dir"])
    req = None
    for cand in (run_dir / "requirements.txt", run_dir / "doc" / "requirements.txt"):
        if cand.exists():
            req = cand
            break
    if req is None:
        return {"ok": False, "detail": "requirements.txt 不存在"}
    try:
        text, enc = read_text_with_probe(req)
    except UnicodeDecodeError as e:
        return {"ok": False, "detail": f"requirements.txt 编码探测失败: {e}",
                "verifier_error": True}
    # 跳过注释/空行，要求依赖行含版本约束
    dep_lines = [
        ln.strip() for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    unpinned = [
        ln for ln in dep_lines
        if not re.search(r"(==|>=|<=|~=|!=|>)", ln) and not ln.startswith(("-", "git+", "http"))
    ]
    if unpinned:
        return {"ok": False, "detail": f"未锁版本依赖: {unpinned}"}
    return {"ok": True, "detail": f"requirements.txt 存在且版本锁定（共 {len(dep_lines)} 行）"}


def _probe_data_source(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """DATA_SOURCE 可达性域（pre_flight 重型）：探测数据目录是否非空。

    仅看目录存在 + 非空，不做网络可达（网络探测交 Resource Planner，避免 verifier
    触发外部副作用）。空 → verify_fail（数据未下载，可能转 supply_halt）。
    """
    run_dir = Path(ctx["run_dir"])
    data_dir = run_dir / "data"
    if not data_dir.exists() or not any(data_dir.iterdir()):
        return {"ok": False, "detail": "data/ 目录不存在或为空（数据未就绪）"}
    return {"ok": True, "detail": "data/ 非空"}


# 域注册表（presence_domains）：纯函数 hash 表，扩展在此登记
_PRESENCE_DOMAINS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "converted_md": _probe_converted_md,
    "requirements_and_ci": _probe_requirements_and_ci,
    "data_source": _probe_data_source,
}


def probe_domain(domain: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """按域名分派探测策略。未知域 → verifier_runtime_error（probe 自身缺定义）。"""
    fn = _PRESENCE_DOMAINS.get(domain)
    if fn is None:
        return {"ok": False, "detail": f"未知 presence 域: {domain}", "verifier_error": True}
    return fn(ctx)


def list_domains() -> Dict[str, bool]:
    """枚举已注册域（status/probe 反查用）。"""
    return {name: True for name in _PRESENCE_DOMAINS}