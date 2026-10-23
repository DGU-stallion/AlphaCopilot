"""vendor a-stock-data 的 loader（M3-V3）。

把 `vendor/a-stock-data/SKILL.md` 里的 91 个 python 块抽出来，剥掉示例调用，
exec 进同一个 namespace，得到一套可调用的取数能力。

**为什么不复制成 .py 文件**：SKILL.md 是上游唯一真源，它每周发版。
复制粘贴就是第二套实现，同步必然漂移（AGENTS 反模式：不要写第二套取数逻辑）。
loader 保持「真源 → 运行时」，升级只需替换 vendor 文件。

**为什么必须剥掉示例调用**：SKILL.md 的块大多以顶层调用结尾（`r = _em_quote("600519")`、
`for i in ...`）。那是给人看的示例；直接 exec 会在 import 阶段就真去联网，
于是「加载模块」变成「发起网络请求」—— 测试不可跑、CI 不可跑、离线不可用。
"""

from __future__ import annotations

import ast
import re
import types
from pathlib import Path
from typing import Any

SKILL = Path(__file__).resolve().parents[1] / "vendor" / "a-stock-data" / "SKILL.md"

# 匹配 ```python ... ``` 代码块。用非贪婪 + DOTALL。
_BLOCK_RE = re.compile(r"```python\n(.*?)\n```", re.S)


def blocks() -> list[str]:
    """抽出全部 python 代码块（保持文件内顺序 —— 后面的块会复用前面的定义）。"""
    text = SKILL.read_text(encoding="utf-8")
    return _BLOCK_RE.findall(text)


def _module_aliases(tree: ast.Module) -> set[str]:
    """本块 import 进来的**模块**名（`import re as R` → R；`import os.path` → os.path/os）。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
    return names


def _imported_symbols(tree: ast.Module) -> set[str]:
    """`from x import y as z` 进来的符号（`timezone`、`Counter`）。"""
    return {
        a.asname or a.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for a in node.names
    }


def _is_example_fetch(node: ast.stmt, local_names: set[str], module_names: set[str]) -> bool:
    """这次模块级赋值是「示例取数」吗（是 → 该丢）。

    只有**纯构造**才留下：`re.compile(...)`、`requests.Session()`、`timezone(...)`、
    `set()`。任何挂在数据对象上的调用（`df.dropna()`）或裸名字取数函数
    （`tencent_quote(...)`）都算示例。
    """
    for call in (c for c in ast.walk(node) if isinstance(c, ast.Call)):
        f = call.func
        if isinstance(f, ast.Name):
            if f.id in local_names:
                return True                     # 块内 def → 示例结果
            if f.id in _PURE_BUILTINS or f.id in module_names:
                continue                        # set()/list() / timezone()/Counter()
            # 其余裸名字调用 = 跨块的取数函数（`tencent_quote` / `tdx_daily_package`
            # / `st_stock_list`）→ 必须丢。这里写成 continue 过一次，代价是加载
            # 从 0.36s 涨到 99.6s（九个块在 import 阶段真去联网）。
            return True
        if isinstance(f, ast.Attribute):
            base = f.value
            # 只看最外层根节点是不是 import 进来的模块
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and base.id in module_names:
                continue                        # re.compile / requests.Session / os.environ.get
            return True                         # 挂在数据上的调用（df.dropna()）
        return True
    return False


# 构造值的裸名字内建（不是取数）。
_PURE_BUILTINS = {"set", "list", "dict", "tuple", "frozenset", "int", "float", "str", "bool", "len", "sum", "min", "max"}


def _strip(src: str) -> ast.Module:
    """保留 import / 常量 / def / class，剥掉模块级示例调用。返回 AST。

    剥除规则（对齐上游 tests 的 `_defs_only` 思路）：
      - Expr / For / While / With / If：整块丢
        （if 也丢：很多块用 `if __name__ == "__main__":` 包示例调用）
      - Assign / AnnAssign：若其右值**调用了本块自己定义的函数**，丢
        （`RESULT = _em_quote(...)` 是示例结果，不是定义）
      - 其余保留

    `if` 的处理比上游宽一档：上游保留 if（可能因为它们的块里 if 是逻辑分支），
    但这里的 SKILL.md 里 if 主要出现在 `__main__` 守卫，保留会让示例跑起来。
    这是我实测后的判断，不是抄。
    """
    tree = ast.parse(src)
    local_names = {
        n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    module_names = _module_aliases(tree)
    # `from datetime import timezone` 这类符号也是纯构造来源，并入模块名集合
    module_names |= _imported_symbols(tree)

    keep: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.Expr, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.If)):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            # 判据：这次赋值是**构造一个值**，还是**发起一次取数**？
            #
            # 早先的规则是「右值含任何 Call 就丢」。它把示例取数（`cb = convertible_bonds()`）
            # 挡掉的同时，也把**模块级常量**一起埋了：
            #     _TICKER_RE   = re.compile(...)          → Ticker 归一化直接 NameError
            #     EM_SESSION   = requests.Session()       → 所有东财函数 NameError
            #     _CN_TZ       = timezone(timedelta(...)) → 时间戳解析 NameError
            # 后果不是报错，而是**静默降级**：能力「存在」，一调就崩
            # （LPR 端点就是因为这个一直返回 NameError，见 api/macro.py）。
            #
            # 现在的判据看**被调者是谁**：
            #   · 裸名字调用（`f()`）→ 只有 f 来自 import 或内建（set/list/Counter/re.compile…）
            #     才算构造；否则是块内 def（示例）或跨块取数函数（`tencent_quote`）→ 丢
            #   · 属性调用（`a.b()`）→ 只有 a 是本块 import 进来的**模块**才算构造
            #     （`re.compile` / `os.environ.get` / `requests.Session`）；
            #     `ticks.loc[...]`、`client.bars(...)` 这类挂在**数据**上的调用 → 丢
            #
            # 这个判据把 143 处被剥的赋值分成了「常量（留）」与「示例取数（丢）」两堆，
            # 且仍能挡住 block 78 那种纯示例块（实测加载后不再联网）。
            if _is_example_fetch(node, local_names, module_names):
                continue
        keep.append(node)

    tree.body = keep
    return tree


def strip_examples(src: str) -> ast.Module:
    """只做「剥示例」这一步，返回 AST（不编译）。

    把这一步单独暴露出去，是为了让测试能**走真实的剥除路径**：
    早先判据被抽成独立函数、测试直接调它，结果把调用点改坏（退回旧规则）
    测试依然全绿 —— 测了半天测的是没人调用的那个函数。
    """
    return _strip(src)


def defs_only(src: str) -> types.CodeType:
    """剥示例 → 编译。"""
    # type_ignores 在 3.8+ 是必填字段，ast.parse 已经带上
    return compile(strip_examples(src), "SKILL.md", "exec")


def load() -> dict[str, Any]:
    """把全部块 exec 进同一个 namespace。

    后定义覆盖先定义（vendor 里 `_macro_get` 之类会重复出现 —— 以最后一份为准，
    因为上游是在同一个文件里逐步演进的，靠后的版本是修正版）。

    跳过单块失败的块，不中断整个加载。**已知的三类失败**（都实测过）：

      1. `ModuleNotFoundError: mootdx` —— 该块 import 了 mootdx。
         我们**有意不装** mootdx（ADR-0011 事实 1：2026-09 起连财务也取不到），
         所以依赖它的块必然失败。这是预期行为，不是缺陷。
      2. `NameError: _v39_contract` / `tencent_ticks` 等 —— **前向引用**：
         某块调用了后面块才定义的函数。SKILL.md 是给人按顺序读的，
         不是按依赖排序的模块。这类块在当前顺序下无法加载，
         但它的函数定义部分已经进 namespace 了（失败发生在顶层调用之前
         的情况除外），所以能力大多仍可用。
      3. SyntaxError —— 少数块是 shell 片段或伪代码。

    统一捕获 Exception 而不是只捕 SyntaxError：加载阶段的目标是「尽可能多的
    能力可用」，而不是「一有问题就整体失败」。真正调用某个能力时缺依赖会
    在调用点抛错，那时再报错更准确。
    """
    ns: dict[str, Any] = {"__name__": "vendor.a_stock_data"}
    for block in blocks():
        try:
            exec(defs_only(block), ns)  # noqa: S102 —— 这是本模块的核心职责
        except Exception:  # noqa: BLE001 —— 见 docstring：加载阶段容错，调用阶段才报错
            continue
    return ns


def _summary(node: ast.AST) -> str:
    """取 docstring 首行作为说明；没有就空串。"""
    doc = ast.get_docstring(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else None
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()


def list_capabilities() -> list[dict[str, str]]:
    """列出可用的公开能力（给 agent 一份「能调什么」的清单）。

    从源码 AST 里取：这比从 exec 后的 namespace 取更准 ——
    namespace 里混着 import 进来的第三方函数（requests.get、json.dumps），
    那些不是我们的能力入口，列进清单只会让 agent 困惑。

    只列**公开**（不以 _ 开头）且**有 docstring**的函数：
    没有文档的函数 agent 猜不到怎么用，列出来是噪音。
    """
    seen: dict[str, dict[str, str]] = {}
    for block in blocks():
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = node.name
            if name.startswith("_"):
                continue
            doc = _summary(node)
            if not doc:
                continue
            # 后出现的覆盖先出现的（与 load() 的语义一致：靠后的是修正版）
            seen[name] = {"name": name, "doc": doc}
    return list(seen.values())


def callables(ns: dict[str, Any]) -> dict[str, Any]:
    """只取**vendor 自己定义**的公开函数，排除 import 进来的第三方类。

    为什么要区分：`load()` 的 namespace 里混着 `HTTPAdapter`、`Optional`、
    `Path` 这些 import 进来的名字。它们 callable，但不是「能力入口」。
    把它们列进给 agent 的清单只会让 agent 困惑（"我可以调 Optional？"）。

    判据：vendor 里定义的函数是纯 Python 函数，有 `__code__`；
    第三方类/类型助手的对象没有。
    """
    return {
        k: v for k, v in ns.items()
        if not k.startswith("_") and callable(v) and getattr(v, "__code__", None) is not None
    }


if __name__ == "__main__":  # pragma: no cover
    caps = list_capabilities()
    ns = load()
    print(f"blocks: {len(blocks())}")
    print(f"own callables: {len(callables(ns))}")
    print(f"documented capabilities: {len(caps)}")
    for c in caps[:20]:
        print(f"  {c['name']}: {c['doc'][:70]}")
