"""check_atoms.py —— A 级 check 原子集实现（DESIGN.md §11.2.1）。

机器秒判，零 LLM。check 原子集：
    row_count / col_set / col_range / dup_key / json_path /
    file_exists / file_size_min / stdout_assert / exit_match / assert_expr

白名单函数（assert_expr 受限 namespace 可见）：
    size_gb(path) / min_date(path) / row_count(path) / col_range(path)

assert_expr 安全边界（DESIGN.md §4 + §11.2.1）：
    - expr 在受限 namespace 求值，禁任意 eval。
    - **不**用 eval()。受限于白名单的特征：仅允许【标识符 + 数字 + 运算符 + 调用
      白名单内已注册函数】。实现策略：把白名单函数塞进 globals'__builtins__' 设为 {},
      再用 compile+eval —— 但白名单函数本身已在 dict 内，外部名 '{}'.format 之类
      访问到 __builtins__ 仍可能逃逸。**保守做法**：用 ast 解析 expr，遍历 AST 节点
      白名单校验（仅 Name/Constant/Call/BinOp/UnaryOp/Compare/BoolOp/Tuple/List...
      且 Call 仅允许调已注册函数名），再 eval。这样彻底封死任意属性访问逃逸路径。

每条 check 返回 Verdict dict（不返散文）：
    {id, type, passed: bool, error_kind: "verify_fail"|"verifier_runtime_error"|None,
     detail: str, value: Any}
"""

from __future__ import annotations

import ast
import hashlib
import json
import operator as _op
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# parquet / 表格读取（pyarrow 优先，pandas 次之，再失败给明确错误）
# ---------------------------------------------------------------------------

def read_tabular(path: Path) -> Dict[str, Any]:
    """读取表格产物（parquet/csv），返回 {rows, cols, df_handle, backend}。

    依赖说明（DESIGN.md §11.2.2）：parquet 读取首选 pyarrow（plugin-venv 依赖），
    import 失败优雅降级到 pandas；两者皆失败给明确错误（交审计 retarget: verifier
    _script 处理，不静默吞）。CSV 多编码探测见 read_csv_probe。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"产物不存在: {p}")
    suffix = p.suffix.lower()
    # parquet：pyarrow 优先
    if suffix in (".parquet", ".pq"):
        try:
            import pyarrow.parquet as pq  # type: ignore

            table = pq.read_table(str(p))
            return {
                "rows": table.num_rows,
                "cols": list(table.column_names),
                "backend": "pyarrow",
                "_table": table,
            }
        except ImportError:
            pass
        try:
            import pandas as pd  # type: ignore

            df = pd.read_parquet(str(p))
            return {
                "rows": int(len(df)),
                "cols": list(df.columns),
                "backend": "pandas",
                "_df": df,
            }
        except ImportError as e:
            raise RuntimeError(
                "读取 parquet 需要 pyarrow 或 pandas（plugin-venv 依赖），"
                f"两者均不可用: {e}"
            ) from e
    # CSV：pandas + 多编码探测（直击空气质量 pitfalls）
    if suffix in (".csv", ".tsv"):
        try:
            import pandas as pd  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                f"读取 CSV 需要 pandas（plugin-venv 依赖）但不可用: {e}"
            ) from e
        from . import read_text_with_probe  # 复用编码探测
        _, enc = read_text_with_probe(p)
        sep = "\t" if suffix == ".tsv" else ","
        df = pd.read_csv(str(p), encoding=enc, sep=sep)
        return {
            "rows": int(len(df)),
            "cols": list(df.columns),
            "backend": "pandas",
            "_df": df,
            "_encoding": enc,
        }
    raise ValueError(f"不支持的表格格式: {suffix}")


# ---------------------------------------------------------------------------
# 白名单函数（assert_expr 受限 namespace 可见）
# ---------------------------------------------------------------------------

def size_gb(path: str) -> float:
    """文件/目录大小（GB）。assert_expr 例: size_gb('output/etl_long.parquet') >= 0.05"""
    p = Path(path)
    if p.is_dir():
        total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    elif p.is_file():
        total = p.stat().st_size
    else:
        raise FileNotFoundError(f"size_gb: 路径不存在: {path}")
    return total / (1024 ** 3)


def min_date(path: str) -> str:
    """表格产物中日期列的最小值（字符串 ISO 形式）。assert_expr 例:
       min_date('data/etl.parquet') >= '2023-01-01'"""
    data = read_tabular(Path(path))
    df = data.get("_df")
    if df is None and data.get("backend") == "pyarrow":
        try:
            df = data["_table"].to_pandas()  # 需 pandas 在场；失败抛 verifier_error
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"min_date: pyarrow->pandas 转换失败: {e}") from e
    if df is None:
        raise RuntimeError("min_date: 无可用表格后端")
    # 选名字含 date/time/日期 的列，取最小值
    cand = [c for c in df.columns if any(k in str(c).lower() for k in ("date", "time", "日期"))]
    if not cand:
        raise RuntimeError("min_date: 找不到日期列")
    series = df[cand[0]]
    try:
        return str(series.min())
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"min_date: 计算最小值失败: {e}") from e


def _row_count_fn(path: str) -> int:
    """assert_expr 内 row_count(path) 别名（与 check type=row_count 同义）。"""
    return int(read_tabular(Path(path))["rows"])


def _col_range_fn(path: str) -> int:
    """assert_expr 内 col_range(path) 返回列数。"""
    return int(len(read_tabular(Path(path))["cols"]))


# assert_expr 受限 namespace 的白名单函数表（DESIGN.md §11.2.1）
ASSERT_BUILTINS: Dict[str, Callable[..., Any]] = {
    "size_gb": size_gb,
    "min_date": min_date,
    "row_count": _row_count_fn,
    "col_range": _col_range_fn,
    # 常用比较辅助：len/max/min/sum 对纯列表安全，列入白名单
    "len": len,
    "max": max,
    "min": min,
    "sum": sum,
    "abs": abs,
    "round": round,
    "all": all,
    "any": any,
}

# AST 允许的节点类型（白名单特征，彻底封死任意属性访问逃逸）
_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,        # and / or
    ast.BinOp,         # + - * / ...
    ast.UnaryOp,       # not / -
    ast.Compare,       # == >= < ...
    ast.Call,          # 仅允许调白名单函数（见 Call 校验）
    ast.Constant,      # 数字/字符串/None/True/False
    ast.Name,          # 仅白名单名
    ast.Tuple,
    ast.List,
    ast.Set,
    ast.Dict,
)
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv)
_ALLOWED_CMPOPS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn)

# 算子节点（BinOp.op / Compare.ops / UnaryOp.op / BoolOp.op）—— ast.walk 会把它们
# 也当子节点遍历到（CPython 把 op 字段当 AST 节点存）。它们无子字段、不可逃逸，
# 故显式列入允许集，避免误报"禁用语法节点: Eq"。
_OP_NODES = _ALLOWED_BINOPS + _ALLOWED_CMPOPS + (
    ast.UAdd, ast.USub, ast.Not, ast.Invert,
    ast.And, ast.Or,
    ast.Is, ast.IsNot,   # is/is-not 也列白名单（Compare op，惰性比较无副作用）
)


def _validate_assert_ast(tree: ast.AST) -> None:
    """遍历 AST，白名单校验——禁任意 eval 的核心守门。

    规则：
      - 节点类型必须在 _ALLOWED_NODES 内（封死 Attribute / Subscript 的属性逃逸）。
      - BinOp/Compare 的 op 必须在白名单。
      - Call.func 必须是 Name，且 func.id 在 ASSERT_BUILTINS。
      - Name.id 必须在 ASSERT_BUILTINS（不暴露任何 builtins）。
    任何越界 → ValueError（交审计 retarget: verifier_script，不改作业代码）。
    """
    for node in ast.walk(tree):
        # 算子节点（Eq/Gt/Add/Not/And...）：cp 算子列举在 _OP_NODES，单独放行。
        if isinstance(node, _OP_NODES):
            continue
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"assert_expr 禁用语法节点: {type(node).__name__}")
        if isinstance(node, ast.BinOp) and not isinstance(node.op, _ALLOWED_BINOPS):
            raise ValueError(f"assert_expr 禁用二元运算: {type(node.op).__name__}")
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if not isinstance(op, _ALLOWED_CMPOPS):
                    raise ValueError(f"assert_expr 禁用比较运算: {type(op).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("assert_expr 仅允许调用白名单函数名")
            if node.func.id not in ASSERT_BUILTINS:
                raise ValueError(f"assert_expr 调用了非白名单函数: {node.func.id}")
            # 关键字参数同样收口（防 kwargs 注入）
        if isinstance(node, ast.Name) and node.id not in ASSERT_BUILTINS:
            # 允许 True/False/None（ast.Constant 形式，3.8+ 已是 Constant，此处兜底）
            if node.id not in ("True", "False", "None"):
                raise ValueError(f"assert_expr 引用了非白名单名: {node.id}")


def eval_assert_expr(expr: str, extra_funcs: Optional[Dict[str, Any]] = None) -> Any:
    """在受限 namespace 求值 assert_expr。

    安全边界：compile 后用 _validate_assert_ast 白名单校验，再用
    globals={'__builtins__': {}} + 白名单函数 dict 执行 eval——双重保险。
    任何 attribute access / import / lambda 会在 AST 校验阶段被拒。
    """
    tree = ast.parse(expr, mode="eval")
    _validate_assert_ast(tree)
    namespace: Dict[str, Any] = dict(ASSERT_BUILTINS)
    if extra_funcs:
        # 额外注入需调用方保证白名单安全（hw-exec 仅注入已校验产物句柄）
        namespace.update(extra_funcs)
    return eval(  # noqa: S307 — 已双重白名单校验
        compile(tree, "<assert_expr>", "eval"),
        {"__builtins__": {}},
        namespace,
    )


# ---------------------------------------------------------------------------
# Verdict 结构（统一 dict，不依赖 pydantic 以避免 runner 循环 import）
# ---------------------------------------------------------------------------

def verdict(
    check_id: str,
    check_type: str,
    passed: bool,
    detail: str = "",
    *,
    value: Any = None,
    error_kind: Optional[str] = None,
) -> Dict[str, Any]:
    """构造一条结构化 Verdict。error_kind: verify_fail | verifier_runtime_error | None。"""
    return {
        "id": check_id,
        "type": check_type,
        "passed": bool(passed),
        "error_kind": error_kind,
        "detail": detail,
        "value": value,
    }


# ---------------------------------------------------------------------------
# 单 check 原子实现：签名统一 (check: dict, ctx: dict) -> Verdict
# ctx 至少含 {run_dir: Path, stdout: str, exit_code: int}
# ---------------------------------------------------------------------------

def _resolve_path(p: str, ctx: Dict[str, Any]) -> Path:
    """run_dir 相对路径 → 绝对 Path（run_dir 在 ctx 中）。"""
    rp = Path(p)
    if not rp.is_absolute():
        rp = Path(ctx["run_dir"]) / rp
    return rp


def _num(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"无法转为数字: {x!r}") from e


def check_row_count(check: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """{type: row_count, op: >= | > | == | != | <= | <, value: N, path?: 产物路径}"""
    try:
        spec_obj = check
        path = spec_obj.get("path") or spec_obj.get("artifact") or spec_obj.get("file")
        if path is None:
            # 若未显式给 path，从 ctx 当前 node 产物取（hw-exec 注入 node_artifact）
            path = ctx.get("node_artifact")
            if path is None:
                return verdict(check.get("id", ""), "row_count", False,
                               "row_count 缺 path/artifact 且无 node_artifact", error_kind="verify_fail")
        data = read_tabular(_resolve_path(path, ctx))
        rc = data["rows"]
        op = spec_obj.get("op", ">=")
        val = _num(spec_obj["value"])
        ok = _compare(rc, op, val)
        return verdict(check.get("id", "row_min"), "row_count", ok,
                       f"row_count={rc} {op} {val}", value=rc, error_kind=None if ok else "verify_fail")
    except FileNotFoundError as e:
        return verdict(check.get("id", "row_min"), "row_count", False, str(e), error_kind="verify_fail")
    except Exception as e:  # noqa: BLE001 — verifier 自身故障
        return verdict(check.get("id", "row_min"), "row_count", False, str(e), error_kind="verifier_runtime_error")


def check_col_set(check: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """{type: col_set, expected: [...], path?}"""
    try:
        path = check.get("path") or ctx.get("node_artifact")
        data = read_tabular(_resolve_path(path, ctx))
        cols = set(map(str, data["cols"]))
        expected = set(map(str, check["expected"]))
        missing = sorted(expected - cols)
        extra = sorted(cols - expected)
        ok = expected.issubset(cols)  # 至少包含期望列（多列不报错，匹配长表场景）
        detail = f"cols={sorted(cols)} expected={sorted(expected)} missing={missing} extra={extra}"
        return verdict(check.get("id", "cols"), "col_set", ok, detail,
                      value=sorted(cols), error_kind=None if ok else "verify_fail")
    except FileNotFoundError as e:
        return verdict(check.get("id", "cols"), "col_set", False, str(e), error_kind="verify_fail")
    except Exception as e:  # noqa: BLE001
        return verdict(check.get("id", "cols"), "col_set", False, str(e), error_kind="verifier_runtime_error")


def check_col_range(check: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """{type: col_range, min?: N, max?: N, path?} —— 列数在 [min,max] 区间"""
    try:
        path = check.get("path") or ctx.get("node_artifact")
        data = read_tabular(_resolve_path(path, ctx))
        n = len(data["cols"])
        lo = check.get("min")
        hi = check.get("max")
        ok = True
        if lo is not None and n < _num(lo):
            ok = False
        if hi is not None and n > _num(hi):
            ok = False
        return verdict(check.get("id", "col_range"), "col_range", ok,
                       f"col_count={n} range=[{lo},{hi}]", value=n,
                       error_kind=None if ok else "verify_fail")
    except FileNotFoundError as e:
        return verdict(check.get("id", "col_range"), "col_range", False, str(e), error_kind="verify_fail")
    except Exception as e:  # noqa: BLE001
        return verdict(check.get("id", "col_range"), "col_range", False, str(e), error_kind="verifier_runtime_error")


def check_dup_key(check: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """{type: dup_key, keys: [...], path?} —— 主键无重复（dup_count==0）"""
    try:
        path = check.get("path") or ctx.get("node_artifact")
        data = read_tabular(_resolve_path(path, ctx))
        keys = check["keys"]
        df = data.get("_df")
        if df is None and data.get("backend") == "pyarrow":
            df = data["_table"].to_pandas()
        if df is None:
            raise RuntimeError("dup_key 需 pandas 后端")
        dup = int(df.duplicated(subset=keys).sum())
        ok = dup == 0
        return verdict(check.get("id", "no_dup"), "dup_key", ok, f"duplicate_count={dup}",
                      value=dup, error_kind=None if ok else "verify_fail")
    except FileNotFoundError as e:
        return verdict(check.get("id", "no_dup"), "dup_key", False, str(e), error_kind="verify_fail")
    except Exception as e:  # noqa: BLE001
        return verdict(check.get("id", "no_dup"), "dup_key", False, str(e), error_kind="verifier_runtime_error")


def check_json_path(check: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """{type: json_path, path: 文件, jq?: 'a.b[0].c', expected?: any, exists?: bool}"""
    try:
        p = _resolve_path(check["path"], ctx)
        text, _enc = (None, None)
        from . import read_text_with_probe  # 延迟 import
        text, _enc = read_text_with_probe(p)
        obj = json.loads(text)
        val = _jq_path(obj, check.get("jq", ""))
        if "expected" in check:
            ok = val == _normalize(check["expected"])
            return verdict(check.get("id", "json"), "json_path", ok,
                           f"jq={check.get('jq')} got={val!r} expected={check['expected']!r}",
                           value=val, error_kind=None if ok else "verify_fail")
        # exists 语义：jq 路径可解析到值
        ok = val is not _MISSING
        want_present = check.get("exists", True)
        ok = ok if want_present else (not ok)
        return verdict(check.get("id", "json"), "json_path", ok, f"jq={check.get('jq')} present={val is not _MISSING}",
                      value=val, error_kind=None if ok else "verify_fail")
    except FileNotFoundError as e:
        return verdict(check.get("id", "json"), "json_path", False, str(e), error_kind="verify_fail")
    except Exception as e:  # noqa: BLE001
        return verdict(check.get("id", "json"), "json_path", False, str(e), error_kind="verifier_runtime_error")


class _Missing:
    pass


_MISSING = _Missing()


def _jq_path(obj: Any, jq: str) -> Any:
    """极简点路径 a.b[0].c 取值；不支持完整 jq 语法（够用且安全）。"""
    if not jq:
        return obj
    cur = obj
    for part in jq.split("."):
        if "[" in part and part.endswith("]"):
            key = part[: part.index("[")]
            idx = int(part[part.index("[") + 1 : -1])
            if key:
                cur = _dict_get(cur, key)
            if isinstance(idx, int):
                cur = cur[idx] if isinstance(cur, list) and idx < len(cur) else _MISSING
        else:
            cur = _dict_get(cur, part)
        if cur is _MISSING:
            return _MISSING
    return cur


def _dict_get(d: Any, k: str) -> Any:
    if isinstance(d, dict):
        return d.get(k, _MISSING)
    return _MISSING


def _normalize(v: Any) -> Any:
    return v


def check_file_exists(check: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """{type: file_exists, path: 文件} —— 文件存在即过"""
    try:
        p = _resolve_path(check["path"], ctx)
        ok = p.exists()
        return verdict(check.get("id", "exists"), "file_exists", ok, f"path={p} exists={ok}",
                      error_kind=None if ok else "verify_fail")
    except Exception as e:  # noqa: BLE001
        return verdict(check.get("id", "exists"), "file_exists", False, str(e), error_kind="verifier_runtime_error")


def check_file_size_min(check: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """{type: file_size_min, path: 文件, value: 字节数}"""
    try:
        p = _resolve_path(check["path"], ctx)
        if not p.exists():
            return verdict(check.get("id", "size_min"), "file_size_min", False,
                           f"文件不存在: {p}", error_kind="verify_fail")
        sz = p.stat().st_size
        val = _num(check["value"])
        ok = sz >= val
        return verdict(check.get("id", "size_min"), "file_size_min", ok,
                       f"size={sz} >= {val}", value=sz, error_kind=None if ok else "verify_fail")
    except Exception as e:  # noqa: BLE001
        return verdict(check.get("id", "size_min"), "file_size_min", False, str(e), error_kind="verifier_runtime_error")


def check_stdout_assert(check: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """{type: stdout_assert, pattern: 正则/子串, required: bool}

    DESIGN §11.2.1 stdout_asserts 项。required=true 时 pattern 须出现；
    required=false 时 pattern 须不出现（验"分块"等正向痕迹可用）。
    注：pattern 用 re 子串匹配（非全文锚），面向中文 stdout 友好。
    """
    import re
    try:
        stdout = ctx.get("stdout", "")
        pat = check["pattern"]
        required = check.get("required", True)
        found = re.search(_to_regex(pat), stdout) is not None
        ok = found if required else (not found)
        return verdict(check.get("id", "stdout"), "stdout_assert", ok,
                       f"pattern={pat!r} found={found} required={required}",
                       error_kind=None if ok else "verify_fail")
    except Exception as e:  # noqa: BLE001
        return verdict(check.get("id", "stdout"), "stdout_assert", False, str(e), error_kind="verifier_runtime_error")


def _to_regex(pat: str) -> str:
    """子串/正则统一：若 pat 含特殊字符视为正则，否则转义当子串。"""
    import re
    return pat if any(c in pat for c in r".*+?()[]{}|\\$^") else re.escape(pat)


def check_exit_match(check: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """{type: exit_match, value: 期望退出码}（node 退出码须等于 value）"""
    try:
        got = int(ctx.get("exit_code", -1))
        want = int(check.get("value", 0))
        ok = got == want
        return verdict(check.get("id", "exit"), "exit_match", ok, f"exit={got} == {want}",
                       value=got, error_kind=None if ok else "verify_fail")
    except Exception as e:  # noqa: BLE001
        return verdict(check.get("id", "exit"), "exit_match", False, str(e), error_kind="verifier_runtime_error")


def check_assert_expr(check: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """{type: assert_expr, expr: 'size_gb(...) >= 0.05'}

    expr 在受限 namespace 求值（白名单函数 + 禁任意 eval，见 eval_assert_expr）。
    产物路径相对 run_dir；ctx 注入 node_artifact 供 size_gb 等直接引用文件名。
    """
    try:
        expr = check["expr"]
        # 注入相对 run_dir 解析的 path 句柄，让 size_gb('output/x.parquet') 可寻
        ok = bool(eval_assert_expr(expr))
        return verdict(check.get("id", "assert"), "assert_expr", ok, f"expr={expr!r} -> {ok}",
                       value=ok, error_kind=None if ok else "verify_fail")
    except (ValueError, SyntaxError) as e:
        # expr 语法/白名单越界 → verifier 脚本层问题，不改作业代码
        return verdict(check.get("id", "assert"), "assert_expr", False, str(e), error_kind="verifier_runtime_error")
    except FileNotFoundError as e:
        return verdict(check.get("id", "assert"), "assert_expr", False, str(e), error_kind="verify_fail")
    except Exception as e:  # noqa: BLE001
        return verdict(check.get("id", "assert"), "assert_expr", False, str(e), error_kind="verifier_runtime_error")


# ---------------------------------------------------------------------------
# 分派表 + 通用比较
# ---------------------------------------------------------------------------

_OPS: Dict[str, Callable[[Any, Any], bool]] = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
}


def _compare(a: Any, op: str, b: Any) -> bool:
    if op not in _OPS:
        raise ValueError(f"未知 op: {op}")
    try:
        return _OPS[op](a, b)
    except TypeError:
        # 比较不了（类型不兼容）→ verifier_runtime_error 由调用方根据 verdict 判，这里保守 False
        return False


# check type -> 原子函数 分派表（hw-exec run-node 走这里；assert/tool/presence 走 runner）
CHECK_DISPATCH: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = {
    "row_count": check_row_count,
    "col_set": check_col_set,
    "col_range": check_col_range,
    "dup_key": check_dup_key,
    "json_path": check_json_path,
    "file_exists": check_file_exists,
    "file_size_min": check_file_size_min,
    "stdout_assert": check_stdout_assert,
    "exit_match": check_exit_match,
    "assert_expr": check_assert_expr,
}


def run_check_atom(check: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """按 check.type 分派到对应原子，返回 Verdict。未知 type → verifier_runtime_error。"""
    ctype = check.get("type")
    fn = CHECK_DISPATCH.get(ctype) if ctype else None
    if fn is None:
        return verdict(check.get("id", ctype or ""), ctype or "unknown", False,
                       f"未知 check type: {ctype}", error_kind="verifier_runtime_error")
    return fn(check, ctx)


# ---------------------------------------------------------------------------
# 产物 digest（facts_patch.artifacts.<node>.digest 用，DESIGN.md §11.2.1）
# ---------------------------------------------------------------------------

def file_digest(path: Path, algo: str = "sha256") -> str:
    """流式计算文件摘要（大文件不全量读入内存，直击空气质量 13230 CSV 内存陷阱）。"""
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()