"""门禁：xfail 数量不得增加（M0-2）。

背景：v2 重构期间有 8 个测试依赖已消失的 `deepseek_harness` SDK，暂时标为
`xfail(strict=True)`，等 M1-2 换成 PiProvider 后按新契约重写。

风险：`xfail` 是一种**合法的静默**——测试不会红，CI 也不会叫。如果不设上限，
重构过程中「这个测试太麻烦了，先 xfail 吧」会一点点把测试套件掏空，而没人察觉。
这正是当初 8 个测试红了很久没人管的原因。

所以把「xfail 只能减少不能增加」写成一条测试。它跑得极快（只读源码，不执行
被测代码），代价接近于零，但把一种缓慢的腐化变成了会红的失败。

seam：源码文本里 xfail 标记的出现次数。
选这个边界的理由：它统计的是**声明**而非**运行结果**，因此不受 skipif、
外部依赖、环境差异影响——在 macOS 和 Linux 上给出同一个答案。
"""

from __future__ import annotations

from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# 动态拼出标记，避免本文件的字面量把自己也统计进去（否则审计器自指）。
_MARKER = "@pytest.mark." + "xfail("

# 2026-10-21 基线：全部是 deepseek_harness 缺失导致，等 M1-2 处理后应逐个移除。
# 只允许往下调，不允许往上调。下调后请同步更新这个数字。
XFAIL_BUDGET = 8


def _count_xfail_marks() -> dict[str, int]:
    """统计每个测试文件里 xfail 声明的出现次数。"""
    counts: dict[str, int] = {}
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        n = path.read_text(encoding="utf-8").count(_MARKER)
        if n:
            counts[path.name] = n
    return counts


def test_xfail_budget_not_exceeded():
    counts = _count_xfail_marks()
    total = sum(counts.values())

    assert total <= XFAIL_BUDGET, (
        f"xfail 数量 {total} 超过预算 {XFAIL_BUDGET}。\n"
        f"分布：{counts}\n\n"
        "禁止用 xfail 掩盖新失败。要么修好，要么在 REFACTOR-PLAN 里立一条"
        "带排期的任务再调整 XFAIL_BUDGET。"
    )


def test_xfail_budget_tracks_reality():
    """预算不应远高于实际用量——否则等于给自己留了偷偷加 xfail 的空间。

    实际用量降下来后，把 XFAIL_BUDGET 同步调低，这条会提醒你。
    """
    total = sum(_count_xfail_marks().values())

    assert total >= XFAIL_BUDGET - 2, (
        f"实际 xfail 只有 {total} 个，但预算写着 {XFAIL_BUDGET}。\n"
        f"把 tests/test_xfail_budget.py 里的 XFAIL_BUDGET 改成 {total}，"
        "把腾出来的额度收回。"
    )
