"""S4 A 股回测引擎 —— 规则回归测试（fixture，无网络）。

验证移植自 Vibe-Research 的 A 股规则：板块涨跌停 / 整手 / 费用 / T+1 / 无未来函数 / gate。
"""

from __future__ import annotations

import pytest

from alpha import backtest_engine as be


def test_price_limit_by_board():
    assert be.price_limit("600519") == 0.10
    assert be.price_limit("000001") == 0.10
    assert be.price_limit("300750") == 0.20
    assert be.price_limit("688111") == 0.20
    assert be.price_limit("830799") == 0.30
    assert be.price_limit("600519.SH") == 0.10


def test_round_lot_floors_to_100():
    assert be.round_lot(250) == 200
    assert be.round_lot(99) == 0
    assert be.round_lot(100) == 100


def test_sell_cost_includes_stamp_tax_buy_does_not():
    notional = 1_000_000.0
    # 卖出比买入多印花税万5
    assert be.sell_cost(notional) - be.buy_cost(notional) == pytest.approx(
        notional * 0.0005
    )


def test_commission_min_5():
    # 极小额：佣金取下限 ¥5（+过户费）
    assert be.buy_cost(100.0) == pytest.approx(5.0 + 100.0 * 0.00001)


# ---- gate 拒绝 ----

def test_gate_rejects_short_series():
    assert be.gate([100.0], [0], None) is not None


def test_gate_rejects_length_mismatch():
    assert be.gate([100.0, 101.0], [1], None) is not None


def test_gate_rejects_nonpositive_price():
    assert be.gate([100.0, 0.0, 101.0], [0, 0, 0], None) is not None


def test_gate_passes_valid():
    assert be.gate([100.0, 101.0, 102.0], [0, 1, 1], None) is None


# ---- 回测行为 ----

def test_flat_signal_equity_stays_1():
    closes = [100.0, 110.0, 120.0, 130.0]
    res = be.run("600519", closes, [0, 0, 0, 0])
    assert res.equity[-1] == 1.0  # 从不持仓，净值不动
    assert res.trades == 0


def test_buy_and_hold_captures_upside_minus_costs():
    # 全程想持有：次日建仓后一直持有，净值应随价格上涨（扣费用后略低于毛涨幅）。
    closes = [100.0, 100.0, 110.0, 121.0]
    res = be.run("600519", closes, [1, 1, 1, 1], initial_cash=1_000_000.0)
    # 毛涨幅从建仓价 100（t=1 成交）到 121 = +21%；扣费用后净值 >1 且 <1.21
    assert 1.0 < res.equity[-1] < 1.21
    assert res.trades == 1  # 只建仓一次，未平仓


def test_t_plus_1_blocks_same_day_sell():
    # t=1 建仓，t=1 当天不能卖。信号 [1,0,...]：t=0 想持有→t=1 建仓；
    # t=1 信号 0 想卖→次日 t=2 才执行（且 t>entry_idx）。
    closes = [100.0, 100.0, 105.0, 105.0]
    res = be.run("600519", closes, [1, 0, 0, 0])
    # t=1 建仓(entry_idx=1)，t=2 卖出（T+1 满足）。持仓在 t=1 有、t=2 起 0。
    assert res.positions[1] > 0
    assert res.positions[2] == 0


def test_limit_up_blocks_entry():
    # 次日涨停（day_move >= 10%）时不建仓。closes: 100 -> 111（+11% 封板）
    closes = [100.0, 111.0, 112.0]
    res = be.run("600519", closes, [1, 1, 1])
    # t=1 涨停封板，建仓被拦；t=2 涨幅小可建仓
    assert res.positions[1] == 0
    assert res.positions[2] > 0


def test_no_lookahead_signal_applies_next_day():
    # signal[t] 在 t+1 生效：t=0 给 1，t=1 才建仓（不在 t=0 用未来信号）
    closes = [100.0, 100.0, 100.0]
    res = be.run("600519", closes, [1, 1, 1])
    assert res.positions[0] == 0  # 第 0 天不可能已持仓
    assert res.positions[1] > 0
