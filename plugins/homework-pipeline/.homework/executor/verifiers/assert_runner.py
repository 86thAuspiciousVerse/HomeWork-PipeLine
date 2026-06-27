"""assert_runner.py —— A 级 type=assert verify 的执行器（DESIGN.md §11.3.1）。

两种 assert 子形态：
  1. expr 形： {type: assert, expr: "size_gb('data/raw') >= 1"} —— 受限 namespace 求值
     （安全边界见 check_atoms.eval_assert_expr：AST 白名单 + __builtins__={} 双保险）。
  2. check 映射形：{type: assert, check: <name>} —— 映射 check_<name>.py 模块的
     run(ctx) -> bool。check_<name>.py 是用户/方案可选的领域校验脚本（如
     timeseries_split_respected），放在 verifier 目录下，import 成功即调，失败回
     verifier_runtime_error（retarget: verifier_script）。

对审计暴露接口：run_assert(spec, ctx) -> Verdict dict（见 __init__.run_assert）。

Verdict.error_kind：
  - verify_fail: assert 不通过 → 重跑作业代码
  - verifier_runtime_error: check 模块缺失/语法错/受限 namespace 越界 → 改 verifier 脚本
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any, Dict, Optional

from . import check_atoms
from .check_atoms import verdict


def _resolve_check_module(name: str):
    """动态加载 check_<name>.py 模块（同 verifier 包内）。

    安全取舍：仅允许加载本包内名字以 check_ 开头的模块——通过 importlib 在固定
    包路径内解析，不接受任意路径（禁任意 import）。
    """
    mod_name = f"check_{name}"
    full = f"{__package__}.{mod_name}" if __package__ else mod_name
    try:
        return importlib.import_module(full)
    except ModuleNotFoundError:
        # 包内不存在该 check_*.py
        return None


def run_assert(spec: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """执行 type=assert verify，返回结构化 Verdict（不返散文）。

    spec 形如：
        {"type": "assert", "expr": "size_gb('data/raw') >= 1"}
        或 {"type": "assert", "check": "timeseries_split_respected"}
    ctx 至少含 {run_dir, stdout, exit_code, node_artifact}。
    """
    vid = spec.get("id", spec.get("check") or "assert")

    # 子形态 1：expr 受限 namespace
    if "expr" in spec:
        v = check_atoms.check_assert_expr({"id": vid, "type": "assert_expr", "expr": spec["expr"]}, ctx)
        # 统一 type 标 assert
        v["type"] = "assert"
        return v

    # 子形态 2：check_<name>.py 映射
    if "check" in spec:
        name = spec["check"]
        mod = _resolve_check_module(name)
        if mod is None:
            return verdict(vid, "assert", False,
                           f"check 模块不存在: check_{name}.py",
                           error_kind="verifier_runtime_error")
        run_fn = getattr(mod, "run", None)
        if not callable(run_fn):
            return verdict(vid, "assert", False,
                           f"check_{name}.py 缺 run(ctx)->bool 函数",
                           error_kind="verifier_runtime_error")
        try:
            result = run_fn(ctx)
        except Exception as e:  # noqa: BLE001 — verifier 脚本本身出错
            return verdict(vid, "assert", False, f"check_{name}.py 执行异常: {e}",
                           error_kind="verifier_runtime_error")
        passed = bool(result)
        return verdict(vid, "assert", passed, f"check_{name}.run -> {passed}",
                       error_kind=None if passed else "verify_fail")

    return verdict(vid, "assert", False, "assert verify 缺 expr 或 check 字段",
                   error_kind="verifier_runtime_error")


def list_check_modules() -> Dict[str, Any]:
    """枚举包内所有 check_*.py 模块（供 status/probe 反查可用 check 集）。"""
    if not __package__:
        return {}
    out: Dict[str, Any] = {}
    for m in pkgutil.iter_modules(__path__ if hasattr(__import__(__package__), "__path__") else []):  # type: ignore[arg-type]
        if m.name.startswith("check_"):
            out[m.name[len("check_"):]] = True
    return out