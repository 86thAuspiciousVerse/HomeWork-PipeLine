"""tools_runner.py —— A 级 type=tool verify 的执行器（DESIGN.md §11.3.1）。

形态：{type: tool, tool: "ruff/version-pin-check", combine?: "all"|"any", args?: [...]}
  - subprocess 跑该工具，看 exitcode（0=过、非0=不过）。
  - combine=all（默认）：多项 tool 全过才算过；combine=any：任一过即过。
  - tool 名视作可执行/已安装工具，由 ctx 注入的 plugin-venv PATH 解析。

对审计暴露接口：run_tool(spec, ctx) -> Verdict dict。

安全取舍：tool 名必须在白名单内（防任意命令执行），白名单默认含常见代码风格/
版本锁定检查工具；越界 → verifier_runtime_error（retarget: verifier_script）。
"""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List, Optional

from .check_atoms import verdict

# 工具白名单（防 type=tool 被滥用跑任意命令）。扩展需在此显式登记。
_TOOL_WHITELIST = {
    "ruff": ["ruff", "check"],
    "version-pin-check": ["pip", "check"],
    "black": ["black", "--check"],
    "mypy": ["mypy"],
    "pytest": ["pytest", "-q"],
}


def run_tool(spec: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """执行 type=tool verify，返回结构化 Verdict。

    spec 形如：
        {"type": "tool", "tool": "ruff", "combine": "all"}
        或 {"type": "tool", "tools": ["ruff", "version-pin-check"], "combine": "any"}
    ctx 含 {run_dir, plugin_venv_path?}。
    """
    vid = spec.get("id", spec.get("tool") or "tool")
    tools: List[str] = []
    if "tool" in spec:
        tools = [spec["tool"]]
    elif "tools" in spec:
        tools = list(spec["tools"])
    if not tools:
        return verdict(vid, "tool", False, "tool verify 缺 tool/tools 字段",
                       error_kind="verifier_runtime_error")
    combine = spec.get("combine", "all")
    if combine not in ("all", "any"):
        return verdict(vid, "tool", False, f"未知 combine: {combine}",
                       error_kind="verifier_runtime_error")

    results: List[Dict[str, Any]] = []
    for t in tools:
        results.append(_run_single_tool(vid, t, spec, ctx))

    passed_flags = [r["passed"] for r in results]
    if combine == "all":
        ok = all(passed_flags) and len(passed_flags) > 0
    else:
        ok = any(passed_flags)
    detail = "; ".join(f"{r['tool']}: exit={r['exit_code']}" for r in results)
    # 任一 verifier_runtime_error 整体记 verifier_runtime_error
    err = "verifier_runtime_error" if any(r.get("error_kind") == "verifier_runtime_error" for r in results) else (
        None if ok else "verify_fail"
    )
    return verdict(vid, "tool", ok, detail, value=results, error_kind=err)


def _run_single_tool(vid: str, tool_name: str, spec: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """跑单个白名单工具，返回 {tool, exit_code, passed, error_kind?}。"""
    if tool_name not in _TOOL_WHITELIST:
        return {"tool": tool_name, "exit_code": -1, "passed": False,
                "error_kind": "verifier_runtime_error",
                "detail": f"工具未在白名单: {tool_name}"}
    base_cmd = _TOOL_WHITELIST[tool_name]
    extra_args: List[str] = list(spec.get("args", []))
    cmd = base_cmd + extra_args
    cwd = str(ctx.get("run_dir", "."))
    env_extra = ctx.get("env")
    import os
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=env,
            capture_output=True, text=True, timeout=int(spec.get("timeout", 120)),
        )
        passed = proc.returncode == 0
        return {"tool": tool_name, "exit_code": proc.returncode, "passed": passed,
                "error_kind": None if passed else "verify_fail",
                "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]}
    except FileNotFoundError as e:
        # 工具未安装 → verifier 脚本/环境层问题，不是作业代码错
        return {"tool": tool_name, "exit_code": -1, "passed": False,
                "error_kind": "verifier_runtime_error", "detail": f"工具未安装: {e}"}
    except subprocess.TimeoutExpired:
        return {"tool": tool_name, "exit_code": -1, "passed": False,
                "error_kind": "verify_fail", "detail": "tool 超时"}
    except Exception as e:  # noqa: BLE001
        return {"tool": tool_name, "exit_code": -1, "passed": False,
                "error_kind": "verifier_runtime_error", "detail": str(e)}