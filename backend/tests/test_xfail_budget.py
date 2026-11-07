"""门禁：xfail 数量不得增加（M0-2）。

背景：v2 重构期间曾有 8 个测试依赖已消失的 `deepseek_harness` SDK，标为
`xfail(strict=True)` 过渡。M1 换成 PiProvider 后它们已全部按新契约重写并转绿
（2026-10-21），预算从 8 降到 0。

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

# 2026-10-21：已清零（M1-2/M1-6 换 Pi + 重写 mock 手法后全部转绿）。
# 这个数字现在的作用是**禁止**再引入 xfail —— 有测试红了就修，不要藏。
# 确有必要（例如某个上游接口已知会挂一段时间）时，先在这里显式加数并写清原因与排期。
XFAIL_BUDGET = 0


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


def test_no_xfail_at_all():
    """预算为 0 时，不能有任何 xfail。

    这条与上面那条冗余是故意的：预算 0 意味着「一个都不许」，
    值得一条直说的断言，而不是让读者从「<= 0」自己推出来。
    """
    counts = _count_xfail_marks()
    assert not counts, (
        f"不应存在任何 xfail，实际分布：{counts}。\n"
        "测试红了就修，不要用 xfail 掩盖。"
    )
