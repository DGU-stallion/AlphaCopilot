"""M3-V3 vendor loader —— 从 SKILL.md 抽 91 个 python 块并 exec 成可调用能力。

为什么不是「复制粘贴成 .py 文件」：
上游的 SKILL.md 是唯一真源，它每周发版。复制粘贴就变成第二套实现，
同步时必然漂移（而 AGENTS 反模式第 5 条正是「不要写第二套取数逻辑」）。

所以 loader 是「读真源 → 抽代码块 → 剥掉示例调用 → 同 namespace exec」。
剥示例调用这一步是关键：SKILL.md 里的块大多以 `if __name__ == "__main__":`
或顶层调用结尾（那是给人看的示例），直接 exec 会真的去联网。

验收口径（来自 docs/research/a-stock-data-v3.10.md §7.4）：
  - 91 个 python 块
  - 抽出的公开可调用对象接近 87（上游 README 的 88-1-1+1 计数口径）
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 与 fixture 同名的 `loader` 会遮住模块，所以判据级测试用这个别名。
# 放在模块级 import 而不是 fixture 里：判据测试是纯函数测试，不需要 fixture。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import loader as loader_mod  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]          # data-service/
sys.path.insert(0, str(ROOT / "src"))

SKILL = ROOT / "vendor" / "a-stock-data" / "SKILL.md"


@pytest.fixture(scope="module")
def loader():
    import loader as mod
    return mod


class TestBlocks:
    def test_skill_exists(self):
        assert SKILL.exists(), f"vendor 文件缺失：{SKILL}"

    def test_extracts_91_blocks(self, loader):
        """91 是文档里核对过的数字；变了说明 vendor 文件被改过（只读约定被破坏）。"""
        blocks = loader.blocks()
        assert len(blocks) == 91, f"期望 91 个 python 块，实际 {len(blocks)}"

    def test_blocks_are_non_empty_strings(self, loader):
        for i, b in enumerate(loader.blocks()):
            assert isinstance(b, str) and b.strip(), f"第 {i} 个块是空的"


class TestDefsOnly:
    def test_strips_module_level_example_calls(self, loader):
        """顶层裸调用必须被剥掉 —— 否则 exec 时会真去联网。"""
        src = (
            "import os\n"
            "def f():\n"
            "    return 1\n"
            "f()\n"          # 示例调用
        )
        code = loader.defs_only(src)
        ns: dict = {}
        exec(code, ns)      # 不抛错、不执行 f()
        assert callable(ns["f"])

    def test_strips_top_level_loops_and_with(self, loader):
        src = (
            "def f():\n    return 1\n"
            "for i in range(3):\n    f()\n"
            "with open('/tmp/nonexistent-xyz') as fh:\n    pass\n"
        )
        ns: dict = {}
        exec(loader.defs_only(src), ns)     # 若没剥掉，with open 会抛 FileNotFoundError
        assert callable(ns["f"])

    def test_keeps_constants_and_imports(self, loader):
        src = "import json\nAPI = 'https://example.com'\ndef f():\n    return API\n"
        ns: dict = {}
        exec(loader.defs_only(src), ns)
        assert ns["API"] == "https://example.com"
        assert ns["f"]() == "https://example.com"

    def test_keeps_assignment_that_does_not_call_local_fn(self, loader):
        src = "def f():\n    return 1\nX = 1 + 2\nf()\n"
        ns: dict = {}
        exec(loader.defs_only(src), ns)
        assert ns["X"] == 3

    def test_drops_assignment_that_calls_local_fn(self, loader):
        """`RESULT = f()` 这种是示例结果，要剥掉（否则 exec 时真跑）。"""
        src = "def f():\n    return 1\nRESULT = f()\n"
        ns: dict = {}
        exec(loader.defs_only(src), ns)
        assert "RESULT" not in ns


class TestLoad:
    def test_loads_without_network(self, loader):
        """**整份 SKILL.md 加载不得联网**。这是整个 vendor 方案的前提。

        为什么单独测：实测踩到过 —— SKILL.md 里有大量「纯示例块」
        （只有 `cb = convertible_bonds()` 这种顶层赋值，没有自己的 def），
        第一版 defs_only 只剥 Expr，留下 Assign，于是加载时真的去取数，
        block 78 卡了 16.7 秒、block 80 卡 10.3 秒。

        用 socket 拦截来验证，而不是只看耗时（耗时受网络环境影响，会假阴/假阳）。
        """
        import socket
        real = socket.socket.connect
        hits: list = []

        def guard(self, addr):  # noqa: ANN001
            hits.append(addr)
            raise RuntimeError(f"loader 不该联网，试图连接 {addr}")

        socket.socket.connect = guard
        try:
            ns = loader.load()
        finally:
            socket.socket.connect = real
        assert hits == [], f"加载时发生了网络请求：{hits[:3]}"
        assert isinstance(ns, dict)

    def test_exposes_own_callables(self, loader):
        ns = loader.load()
        own = loader.callables(ns)
        # 实测：100 个 vendor 自定义公开函数（文档的 87 是「能力入口」口径，
        # 与「函数个数」不是一回事 —— README 的 88-1-1+1 说明）。
        # 区间设宽一点容上游小改动，但不能宽到失去意义（>0 就没意义了）。
        assert 80 <= len(own) <= 130, f"vendor 自定义可调用对象 {len(own)} 个，超出预期"

    def test_excludes_third_party_imports(self, loader):
        """import 进来的类（HTTPAdapter/Optional/Path）不是能力入口，不能算进去。"""
        ns = loader.load()
        own = loader.callables(ns)
        for name in ("HTTPAdapter", "Optional", "Path", "Counter"):
            assert name not in own, f"{name} 是第三方 import，不该出现在能力清单里"

    def test_known_capability_exists(self, loader):
        """抽查几个确定存在的入口（名字来自 vendor 文件，不是猜的）。"""
        ns = loader.load()
        # 找任意一个以 _ak / _em / _sina 开头或含 quote/kline 的公开函数
        names = [k for k in ns if callable(ns[k])]
        hits = [n for n in names if any(t in n.lower() for t in ("quote", "kline", "price"))]
        assert hits, f"没找到行情类入口；已加载 {len(names)} 个可调用对象"

    def test_capabilities_listing_shape(self, loader):
        """list_capabilities() 要给 agent 一份「能调什么」的清单。"""
        caps = loader.list_capabilities()
        assert isinstance(caps, list) and caps
        for c in caps[:5]:
            assert set(c.keys()) >= {"name", "doc"}


class TestReadOnlyVendor:
    def test_vendor_files_untouched(self):
        """vendor 是只读的：loader 不该写任何文件进去。"""
        before = {p.name: p.stat().st_mtime for p in SKILL.parent.iterdir() if p.is_file()}
        import loader as mod
        mod.load()
        after = {p.name: p.stat().st_mtime for p in SKILL.parent.iterdir() if p.is_file()}
        assert before == after


def _kept(src: str) -> set[str]:
    """走**真实的剥除路径**，返回「保留」的顶层赋值目标名。

    刻意不直接调 `_is_example_fetch`：那样会绕过调用点，把调用点改坏
    （比如退回「右值含任何 Call 就丢」的旧规则）测试依然全绿 ——
    等于测了一个没人用的函数。
    """
    import ast

    tree = loader_mod.strip_examples(src)
    return {
        n.targets[0].id
        for n in tree.body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
    }


class TestStripRule:
    """剥除规则的判据（ROUND3 修）。

    为什么这里直接测判据而不是「加载一次看常量在不在」：判据写错时加载会
    **真去联网**（实测 0.36s → 99.6s），测试会挂在超时而不是失败 ——
    一个只会挂住的守卫等于没有守卫。纯函数判据秒级确定，变异立刻可见。
    """

    def test_module_level_constants_are_kept(self):
        # 真事故：旧规则「右值含任何 Call 就丢」把这三个一起埋了 ——
        #   _TICKER_RE = re.compile(...)     → Ticker 归一化 NameError
        #   EM_SESSION = requests.Session()  → **所有东财函数** NameError
        #   _CN_TZ     = timezone(...)       → 时间戳解析 NameError
        # 后果不是导入失败，而是能力「存在」但一调就崩（LPR 因此一直返回
        # NameError EM_SESSION，而 loader 自己的测试全绿）。
        src = (
            "import re\n"
            "import requests\n"
            "from datetime import timezone, timedelta\n"
            "_TICKER_RE = re.compile(r'^x$')\n"
            "EM_SESSION = requests.Session()\n"
            "_CN_TZ = timezone(timedelta(hours=8))\n"
        )
        assert _kept(src) == {"_TICKER_RE", "EM_SESSION", "_CN_TZ"}

    def test_example_fetches_are_dropped(self):
        # 另一头：示例取数必须继续丢，否则 import 阶段就联网
        src = (
            "def tencent_quote(code):\n"
            "    return {}\n"
            "quotes = tencent_quote('600519')\n"          # 块内函数 → 示例
            "snap = tdx_daily_package('2026-10-22')\n"    # 跨块取数函数 → 示例
            "ticks = tencent_ticks('600519')\n"
        )
        assert _kept(src) == set()

    def test_calls_on_data_objects_are_dropped(self):
        # `df.dropna()` / `ticks.loc[...]` 挂在**数据**上，不是模块 → 示例
        src = "df = x.dropna()\nn = df.shape[0]\n"
        # df 被丢（挂在 x 上的调用），n 保留（纯取值，没有调用）
        assert _kept(src) == {"n"}

    def test_pure_builtins_are_kept(self):
        src = "seen = set()\nn = len([1, 2])\n"
        assert _kept(src) == {"seen", "n"}

    def test_plain_literals_unaffected(self):
        src = "API = 'https://x'\nX = 1 + 2\n"
        assert _kept(src) == {"API", "X"}
