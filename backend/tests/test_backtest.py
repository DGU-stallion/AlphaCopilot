"""T39 alpha.backtest 测试 —— 固定 fixture 的净值/指标与手算基准一致。"""

import math

import pytest

from alpha import backtest as bt


def test_ma_basic():
    assert bt.ma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]


def test_always_in_equals_buy_and_hold():
    """信号恒 1 → position 次日全 1 → 净值 = 买入持有（首日空仓）。"""
    closes = [100.0, 110.0, 121.0]  # 每日 +10%
    signal = [1, 1, 1]
    r = bt.run(closes, signal)
    # position[0]=0, position[1]=signal[0]=1, position[2]=signal[1]=1
    # equity: 1.0 -> 1.0*(1+0.10)=1.10 -> 1.10*(1+0.10)=1.21
    assert r.positions == [0, 1, 1]
    assert r.equity[0] == pytest.approx(1.0)
    assert r.equity[1] == pytest.approx(1.10)
    assert r.equity[2] == pytest.approx(1.21)
    assert r.metrics["total_return"] == pytest.approx(0.21, abs=1e-6)


def test_flat_signal_no_return():
    """信号恒 0 → 全程空仓 → 净值不变，回撤 0。"""
    closes = [100.0, 90.0, 120.0]
    r = bt.run(closes, [0, 0, 0])
    assert r.equity == pytest.approx([1.0, 1.0, 1.0])
    assert r.metrics["total_return"] == pytest.approx(0.0)
    assert r.metrics["max_drawdown"] == pytest.approx(0.0)


def test_drawdown_hand_computed():
    """持仓吃到一段下跌，回撤应等于手算值。"""
    closes = [100.0, 110.0, 88.0]  # +10% 然后 -20%
    r = bt.run(closes, [1, 1, 1])
    # equity: 1.0, 1.10, 1.10*0.8=0.88
    assert r.equity[2] == pytest.approx(0.88)
    # peak=1.10 at t1; drawdown[2] = 0.88/1.10 - 1 = -0.20
    assert r.metrics["max_drawdown"] == pytest.approx(-0.20, abs=1e-6)


def test_trade_count_counts_position_changes():
    closes = [10.0, 11.0, 10.0, 11.0, 12.0]
    # signal drives next-day position: pos=[0, s0, s1, s2, s3]
    r = bt.run(closes, [1, 0, 1, 1, 0])
    # positions: [0,1,0,1,1] -> changes at t1(0->1),t2(1->0),t3(0->1) = 3
    assert r.positions == [0, 1, 0, 1, 1]
    assert r.metrics["trade_count"] == 3


def test_golden_cross_signal_shape():
    # 上升趋势后段 fast(2) 应在 slow(3) 之上 → 尾部信号=1
    closes = [1, 2, 3, 4, 5, 6]
    sig = bt.golden_cross_signal(closes, fast=2, slow=3)
    assert len(sig) == 6
    assert sig[-1] == 1  # 持续上涨，快线在慢线上方


def test_backtest_golden_cross_end_to_end():
    # 明确的金叉/死叉：先跌后涨，20/60 需要足够长度
    closes = [100.0 - i for i in range(60)] + [40.0 + i * 2 for i in range(60)]
    r = bt.backtest_golden_cross(closes, fast=20, slow=60)
    assert len(r.equity) == len(closes)
    assert set(r.positions) <= {0, 1}
    assert "sharpe" in r.metrics and "annual_return" in r.metrics


def test_run_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        bt.run([1.0, 2.0], [1])


def test_sharpe_finite_for_varied_returns():
    closes = [100, 102, 101, 105, 103, 108.0]
    r = bt.run(closes, [1, 1, 1, 1, 1, 1])
    assert math.isfinite(r.metrics["sharpe"])
