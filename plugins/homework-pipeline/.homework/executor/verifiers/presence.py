"""presence.py —— A 级 type=presence verify 的执行器（DESIGN.md §11.3.1）。

形态：{type: presence, in: <domain>, paths?: [...], pattern?: 正则, encoding_hint?}
  - 文件存在 + 正则匹配内容。GBK 编码探测直击空气质量 pitfalls
    （Excel/GBK 下中文 CSV 乱码，须多编码探测而非硬编码）。
  - domain: presence_domains.yaml 中定义的"存在域"（如 requirements_and_ci、
    converted_md），由 probes.py 提供探测策略。

对审计暴露接口：run_presence(spec, ctx) -> Verdict dict。

注意 retarget 二分（DESIGN.md §11.3.2）：
  - 文件不存在/正则不中 → verify_fail（改作业代码补产物）
  - 编码探测全失败/探测脚本异常 → verifier_runtime_error（改 verifier 脚本）
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import read_text_with_probe
from .check_atoms import verdict, _resolve_path
from . import probes


def run_presence(spec: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """执行 type=presence verify，返回结构化 Verdict。"""
    vid = spec.get("id", spec.get("in") or "presence")
    domain = spec.get("in")
    pattern = spec.get("pattern")
    paths: List[str] = list(spec.get("paths", []) or [])

    # 优先按 domain 走 probes 探测（domain 定义存在的文件集 + 校验逻辑）
    if domain:
        try:
            probe_result = probes.probe_domain(domain, ctx)
        except Exception as e:  # noqa: BLE001 — probe 脚本故障
            return verdict(vid, "presence", False, f"probe_domain 异常: {e}",
                           error_kind="verifier_runtime_error")
        if not probe_result.get("ok", False):
            # probe 报"域不存在/不完整" → verify_fail（作业缺产物）
            err = "verifier_runtime_error" if probe_result.get("verifier_error") else "verify_fail"
            return verdict(vid, "presence", False, probe_result.get("detail", "presence 域未满足"),
                           error_kind=err)

    # 显式 paths：要求每个文件存在
    missing = []
    for rel in paths:
        p = _resolve_path(rel, ctx)
        if not p.exists():
            missing.append(str(rel))
    if missing:
        return verdict(vid, "presence", False, f"缺失文件: {missing}",
                       error_kind="verify_fail")

    # 正则匹配：对 paths 拼接内容做正则搜（GBK 编码探测）
    if pattern and paths:
        try:
            joined = ""
            for rel in paths:
                p = _resolve_path(rel, ctx)
                text, enc = read_text_with_probe(p)
                joined += text + "\n"
        except UnicodeDecodeError as e:
            # 全编码探测失败 → verifier_runtime_error（编码环境问题，非作业代码错）
            return verdict(vid, "presence", False, f"编码探测失败: {e}",
                           error_kind="verifier_runtime_error")
        except FileNotFoundError as e:
            return verdict(vid, "presence", False, str(e), error_kind="verify_fail")
        rx = _to_regex(pattern)
        found = re.search(rx, joined) is not None
        require_present = spec.get("required", True)
        ok = found if require_present else (not found)
        return verdict(vid, "presence", ok, f"pattern={pattern!r} found={found}",
                       error_kind=None if ok else "verify_fail")

    # 无 domain 无 paths：退化为 file_exists on spec.get("path")
    if not domain and not paths and "path" in spec:
        v = _resolve_path(spec["path"], ctx)
        ok = v.exists()
        return verdict(vid, "presence", ok, f"path={v} exists={ok}",
                       error_kind=None if ok else "verify_fail")

    # domain probe 已 ok 且无更多约束 → 通过
    return verdict(vid, "presence", True, "presence 域满足", error_kind=None)


def _to_regex(pat: str) -> str:
    """同 check_atoms._to_regex 约定：含元字符视为正则，否则转义子串。"""
    return pat if any(c in pat for c in r".*+?()[]{}|\\$^") else re.escape(pat)