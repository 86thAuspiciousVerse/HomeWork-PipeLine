"""verifiers 子系统的包级 CLI 入口（冒烟/调试用，非主执行器）。

主执行器是 plugins/homework-pipeline/.homework/hw-exec（无扩展名），它 import 本包。
本 __main__ 提供独立 probe：
    python -m <pkg> verify-assert '{"type":"assert","expr":"size_gb(\"x\")>=0.05"}' --run-dir <d>
    python -m <pkg> probe-domain requirements_and_ci --run-dir <d>
    python -m <pkg> list
便于开发期对齐 DESIGN.md §11.3.1 的 verify DSL 语义而无需起主 agent。

输出严格 JSON（exit 0=verifier 自身正常，非0=verifier 自身故障）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def _ctx(run_dir: str) -> Dict[str, Any]:
    return {
        "run_dir": Path(run_dir),
        "stdout": "",
        "exit_code": 0,
        "node_artifact": None,
    }


def main(argv: List[str]) -> int:
    if not argv:
        print('用法: python -m <pkg> {verify-assert|verify-tool|verify-presence|probe-domain|list} ...',
              file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        if cmd == "list":
            from . import probes, assert_runner
            out = {
                "presence_domains": probes.list_domains(),
                "check_atoms": list(__import__(__package__ + ".check_atoms", fromlist=["CHECK_DISPATCH"]).CHECK_DISPATCH.keys()),  # noqa: E501
                "check_modules": assert_runner.list_check_modules(),
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0
        if cmd == "probe-domain":
            domain, run_dir = argv[1], argv[2]
            from . import probes
            print(json.dumps(probes.probe_domain(domain, _ctx(run_dir)), ensure_ascii=False))
            return 0
        if cmd == "verify-assert":
            spec = json.loads(argv[1])
            run_dir = argv[2] if len(argv) > 2 else "."
            from . import run_assert
            print(json.dumps(run_assert(spec, _ctx(run_dir)), ensure_ascii=False))
            return 0
        if cmd == "verify-tool":
            spec = json.loads(argv[1])
            run_dir = argv[2] if len(argv) > 2 else "."
            from . import run_tool
            print(json.dumps(run_tool(spec, _ctx(run_dir)), ensure_ascii=False))
            return 0
        if cmd == "verify-presence":
            spec = json.loads(argv[1])
            run_dir = argv[2] if len(argv) > 2 else "."
            from . import run_presence
            print(json.dumps(run_presence(spec, _ctx(run_dir)), ensure_ascii=False))
            return 0
        print(f"未知命令: {cmd}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — verifier 自身故障，写明确错误 + 非0
        print(json.dumps({"verifier_self_error": str(e), "exit": 1}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))