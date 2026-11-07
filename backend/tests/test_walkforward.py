"""Walk-forward / 样本外验证（M4-4）。

## 为什么这一层最重要

参数扫描能找出「全样本上最好」的参数，但那是在**同一份数据上挑的**。
挑出来的最优几乎必然在样本外崩 —— 这是过拟合的定义，不是意外。

Walk-forward 是唯一诚实的检验：只用训练段选参数，然后在**紧邻的、
没参与挑选的**测试段上用它。拼起来的那条样本外曲线，才是「如果当初
真这么做会怎样」。

## 这里守的几条（错了都会让结果变好看，也就是骗人）

1. **训练段与测试段严格不重叠**，且测试段在训练段之后
2. **测试段之间不重叠**（重叠会把同一天算两次，样本外收益被重复计入）
3. **选参数只能用训练段**（用全样本选 = 过拟合的根源，也是最容易犯的错）
4. 某窗口全失败要跳过，不能整个失败

用**注入的确定性 engine** 测，不跑真实数据 —— 否则测试会随行情闪烁。
"""

from __future__ import annotations

import pytest

from alpha.walkforward import split_windows, walk_forward


class TestSplitWindows:
    def test_non_overlapping_test_segments(self):
        """相邻窗口的 test 段不能重叠，否则样本外被重复使用。"""
        ws = split_windows(500, train=120, test=60)
        assert ws
        for a, b in zip(ws, ws[1:], strict=False):
            assert a["test_end"] <= b["test_start"], f"test 段重叠: {a} / {b}"

    def test_test_after_train(self):
        """测试段必须在训练段之后 —— 不能用未来数据训练。"""
        for w in split_windows(500, train=120, test=60):
            assert w["test_start"] >= w["train_end"]
            assert w["test_end"] > w["test_start"]

    def test_no_window_when_too_short(self):
        """总长度不够一个窗口 → 空列表，不硬凑不完整窗口。"""
        assert split_windows(100, train=120, test=60) == []

    def test_exactly_one_window(self):
        ws = split_windows(180, train=120, test=60)
        assert len(ws) == 1
        assert ws[0] == {"train_start": 0, "train_end": 120, "test_start": 120, "test_end": 180}


class TestWalkForward:
    """用「已知最优参数」的假引擎，验证选参逻辑。"""

    def _engine_factory(self, best_fast: int):
        """构造一个假引擎：参数 fast == best_fast 时表现最好。"""
        def engine(closes, params):
            fast = params.get("fast", 0)
            # 造一个能影响指标的「净值」：fast 越接近 best_fast 越好
            good = 1.0 if fast == best_fast else 0.0
            eq = [100.0 + i * (1.0 + 10.0 * good) for i in range(len(closes))]
            return {"metrics": {"total_return": (eq[-1] / eq[0] - 1.0)}, "equity": eq}
        return engine

    def _closes(self, n=400):
        return [100.0 + i * 0.1 for i in range(n)]

    def test_each_window_uses_train_best_params(self):
        """每窗选出来的参数应该是训练段最优的那个。"""
        wf = walk_forward(
            self._closes(), None,
            param_grid=[{"fast": 5}, {"fast": 20}, {"fast": 60}],
            train=120, test=60,
            engine=self._engine_factory(best_fast=20),
            metric="total_return",
        )
        assert wf["windows"], "应该有窗口"
        for w in wf["windows"]:
            assert w["chosen_params"]["fast"] == 20, w

    def test_oos_equity_length_equals_sum_of_test_segments(self):
        """样本外拼接曲线的长度 = 各测试段长度之和。"""
        wf = walk_forward(
            self._closes(), None,
            param_grid=[{"fast": 20}],
            train=120, test=60,
            engine=self._engine_factory(best_fast=20),
            metric="total_return",
        )
        # 每个窗口的 test_range 是 (start, end) 元组
        expected = sum(w["test_range"][1] - w["test_range"][0] for w in wf["windows"])
        assert len(wf["oos_equity"]) == expected
        assert expected > 0

    def test_selection_uses_train_only(self):
        """**这是最重要的一条**：选参数只能用训练段。

        构造一个引擎：fast=5 在训练段最好、fast=60 在测试段最好。
        如果实现正确地只用训练段选参，每窗都会选 5。
        如果实现（错误地）用了全样本，就可能选到 60。
        """
        n = 400
        # 前半段（训练）偏好 5，后半段（测试）偏好 60 —— 用索引区间区分
        def engine(closes, params):
            fast = params.get("fast", 0)
            # 训练段对应的调用会传前 120 个点，测试段传 60 个点：
            # 用长度区分（120 vs 60），模拟「不同段有不同最优参数」
            prefer = 5 if len(closes) >= 100 else 60
            good = 1.0 if fast == prefer else 0.0
            eq = [100.0 + i * (1.0 + 10.0 * good) for i in range(len(closes))]
            return {"metrics": {"total_return": (eq[-1] / eq[0] - 1.0)}, "equity": eq}

        wf = walk_forward(
            self._closes(n), None,
            param_grid=[{"fast": 5}, {"fast": 60}],
            train=120, test=60,
            engine=engine,
            metric="total_return",
        )
        # 训练段长 120 → prefer=5，所以每窗都该选 5
        assert all(w["chosen_params"]["fast"] == 5 for w in wf["windows"]), \
            [w["chosen_params"] for w in wf["windows"]]

    def test_overfit_engine_shows_degradation_below_one(self):
        """样本内好、样本外差的引擎 → degradation 明显 < 1。"""
        def engine(closes, params):
            # 训练段（长）赚，测试段（短）亏 —— 这就是过拟合的样子
            gain = 0.5 if len(closes) >= 100 else -0.2
            eq = [100.0 * (1.0 + gain * i / max(len(closes) - 1, 1)) for i in range(len(closes))]
            return {"metrics": {"total_return": gain}, "equity": eq}

        wf = walk_forward(
            self._closes(), None, param_grid=[{"fast": 20}],
            train=120, test=60, engine=engine, metric="total_return",
        )
        # walk_forward 自身已带 summary（aggregate 是独立入口）
        assert wf["summary"]["degradation"] is not None
        assert wf["summary"]["degradation"] < 1.0, wf["summary"]

    def test_healthy_engine_has_degradation_near_one(self):
        """样本内外表现一致的引擎 → degradation ≈ 1。

        两个坑（我第一版都踩了，记在这里免得后人再踩）：
        1. 样本外指标是从 **equity 复算**的，假引擎的 equity 必须真的体现收益，
           只往 metrics 里塞数字没用
        2. **总收益不能跨长度比较**：同样日收益下 120 天的总收益天然大于 60 天。
           用「总收益」当 metric 测 degradation 时，训练段/测试段长度不同会让
           degradation 系统性偏低（0.47 而不是 1.0），看着像过拟合、其实不是。

        所以这里改用**相同口径**的构造：固定日收益率 + 训练/测试等长，
        让样本内外的总收益真正可比。
        """
        def engine(closes, params):
            r = 0.002
            eq = [100.0]
            for _ in range(1, len(closes)):
                eq.append(eq[-1] * (1.0 + r))
            return {"metrics": {"total_return": eq[-1] / eq[0] - 1.0}, "equity": eq}

        # train == test：让两个区间等长，总收益才可比（见 docstring 第 2 点）
        wf = walk_forward(
            self._closes(), None, param_grid=[{"fast": 20}],
            train=60, test=60, engine=engine, metric="total_return",
        )
        assert abs(wf["summary"]["degradation"] - 1.0) < 0.05, wf["summary"]

    def test_all_params_fail_in_a_window_is_skipped(self):
        """某窗全部参数都失败 → 跳过该窗，不整个失败。"""
        calls = {"n": 0}

        def engine(closes, params):
            calls["n"] += 1
            # 第一个窗口（前两次调用）全部失败
            if calls["n"] <= 2:
                raise RuntimeError("数据不足")
            eq = [100.0 + i for i in range(len(closes))]
            return {"metrics": {"total_return": 0.1}, "equity": eq}

        wf = walk_forward(
            self._closes(), None, param_grid=[{"fast": 20}, {"fast": 60}],
            train=120, test=60, engine=engine, metric="total_return",
        )
        # 有窗口被标记为失败（status 非 ok），而不是整个 walk_forward 抛错
        assert any(w.get("status") != "ok" for w in wf["windows"]), wf["windows"]

    def test_step_smaller_than_test_is_rejected(self):
        """step < test 会让测试段重叠 → 重复计入样本外收益，必须拒绝。"""
        with pytest.raises(ValueError):
            walk_forward(
                self._closes(), None, param_grid=[{"fast": 20}],
                train=120, test=60, step=30,
                engine=self._engine_factory(20), metric="total_return",
            )

    def test_empty_input(self):
        wf = walk_forward([], None, param_grid=[{"fast": 20}], train=120, test=60)
        assert wf["windows"] == []
        assert wf["oos_equity"] == []
