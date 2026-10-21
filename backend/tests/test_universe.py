"""M3-2 Universe as query —— 条件求值器单元测试（先于实现写就）。

关键正确性由测试守护（非真实网络，snapshot 由参数注入；offline Deterministic）：
  1. 显式列表 → resolve 原样返回，不需要快照（不触网）。
  2. board 按代码前缀判定：60/00=主板，30=创业板，688=科创板；其余（4/8/92 北交所）不属于任何板块。
  3. 区间边界含等号（≤/≥，[lo, hi] 闭区间），None 表示该侧不限。
  4. 多条件组合是 AND（每条都得满足才算入选）。
  5. exclude_st 排除名称含 ST / *ST 的。
  6. limit 生效（代码升序取前 N，保证同一天重复求值结果一致）。
  7. **数据源不可用必须抛 DataUnavailable，而不是返回空列表** —— 这条最重要：
     空列表与「今天真的没有符合条件的股票」无法区分（见 test_data_observability 的约定，
     「数据源挂了」被当成「没数据」会让 agent 用 bash 自造数字）。
  8. describe() 输出可读且包含所有生效条件（前端要如实显示「你选的池是什么」）。
  9. 空条件 → 明确拒绝（ValueError），不默认全市场。

snapshot 行约定（由 alpha.universe.load_snapshot 产出）：
  {code: {"name": str, "pe": float|None, "pb": float|None,
          "mcap": float|None, "turnover": float|None}}
  pe/pb 为倍数，mcap 单位亿元，turnover 单位 %。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alpha import universe
from alpha.universe import UniverseQuery

# ---------------------------------------------------------------------------
# 离线快照：覆盖三类板块 + ST 变体 + 缺值行。数值全部手工可心算。
# ---------------------------------------------------------------------------

_SNAPSHOT = {
    "600519": {"name": "贵州茅台", "pe": 30.0, "pb": 9.0, "mcap": 21000.0, "turnover": 0.4},
    "000858": {"name": "五粮液", "pe": 18.0, "pb": 5.0, "mcap": 4700.0, "turnover": 1.2},
    "002594": {"name": "比亚迪", "pe": 22.0, "pb": 5.5, "mcap": 8000.0, "turnover": 1.1},
    "600000": {"name": "ST浦银", "pe": 6.0, "pb": 0.5, "mcap": 1200.0, "turnover": 0.6},
    "000012": {"name": "*ST中天", "pe": None, "pb": 1.1, "mcap": 30.0, "turnover": 2.0},
    "300750": {"name": "宁德时代", "pe": 25.0, "pb": 4.0, "mcap": 9000.0, "turnover": 1.5},
    "301001": {"name": "创业板新股", "pe": 60.0, "pb": 3.0, "mcap": 60.0, "turnover": 6.0},
    "688981": {"name": "中芯国际", "pe": 100.0, "pb": 3.2, "mcap": 4000.0, "turnover": 0.9},
    "430047": {"name": "北交所 example", "pe": 15.0, "pb": 2.0, "mcap": 12.0, "turnover": 3.0},
}


def _codes(q: UniverseQuery, snap=None) -> list[str]:
    return universe.resolve(q, snapshot=snap if snap is not None else _SNAPSHOT)


# 1. 显式列表 ----------------------------------------------------------------

def test_explicit_codes_returned_as_is_without_snapshot():
    """显式列表原样返回；不需要快照（证明不触网、不依赖数据源）。"""
    q = universe.from_codes(["600519", "000858", "300750"])
    assert universe.resolve(q, snapshot=None) == ["600519", "000858", "300750"]


def test_from_codes_rejects_bad_codes():
    with pytest.raises(ValueError):
        universe.from_codes(["茅台", "000858"])


# 2. 板块 --------------------------------------------------------------------

def test_board_filter_by_prefix():
    assert _codes(UniverseQuery(board="主板")) == [
        "000012", "000858", "002594", "600000", "600519"]
    assert _codes(UniverseQuery(board="创业板")) == ["300750", "301001"]
    assert _codes(UniverseQuery(board="科创板")) == ["688981"]


def test_board_rejects_unknown_value():
    with pytest.raises(ValueError):
        _codes(UniverseQuery(board="港股"))


def test_board_filter_excludes_bj_when_board_given():
    """北交所 4/8/92 前缀不属于三类板块；指定 board 时自然排除。"""
    assert "430047" not in _codes(UniverseQuery(board="主板"))
    assert "430047" in _codes(UniverseQuery(pe_min=1, pe_max=100))  # 不限板块时在全市场里


# 3. 区间边界（闭区间，含等号；None 不限）----------------------------------------

def test_range_boundaries_are_inclusive():
    # pe=25 的 300750 恰好命中上界；pe=18 的 000858 恰好命中下界
    out = _codes(UniverseQuery(pe_min=18, pe_max=25))
    assert out == ["000858", "002594", "300750"]  # 002594=22 夹在中间；600000=6 太低 100 太高


def test_pe_max_includes_boundary_excludes_above():
    out = _codes(UniverseQuery(pe_max=25))
    assert "300750" in out      # pe==25 边界命中
    assert "688981" not in out  # pe=100 不命中


def test_none_side_is_unbounded():
    out = _codes(UniverseQuery(pe_min=18))
    assert "688981" in out and "600000" not in out  # 只有下界时上侧不限


def test_missing_metric_value_is_not_matched():
    """pe 缺值（如 *ST 行 pe=None）不能命中涉及 PE 的条件——无法验证即不入选。"""
    out = _codes(UniverseQuery(pe_max=1000))
    assert "000012" not in out


def test_mcap_boundary_inclusive():
    out = _codes(UniverseQuery(mcap_min=4700))
    assert "000858" in out  # 4700 == 4700 边界


# 4. 多条件 AND ----------------------------------------------------------------

def test_multiple_conditions_are_and():
    q = UniverseQuery(board="主板", pe_min=20, pe_max=30, pb_max=9.0,
                      mcap_min=2000.0, turnover_min=0.3, exclude_st=True)
    # 主板里再卡 PE 20~30：600519(30/9/21000/0.4)、002594(22/5.5/8000/1.1)；
    # 600000 pe=6 太低，000858 pe=18 太低，000012 pe 缺值
    assert _codes(q) == ["002594", "600519"]


# 5. exclude_st ----------------------------------------------------------------

def test_exclude_st_removes_st_and_star_st():
    out = _codes(UniverseQuery(board="主板", pe_min=1, pe_max=100, exclude_st=True))
    assert "000012" not in out and "600000" not in out  # *ST中天 / ST浦银
    assert "000858" in out
    out2 = _codes(UniverseQuery(board="主板", pe_min=1, pe_max=100))
    assert "600000" in out2  # 不加 exclude_st 时 ST 仍在池里


# 6. limit ----------------------------------------------------------------------

def test_limit_takes_first_n_in_code_order():
    assert _codes(UniverseQuery(board="主板", limit=2)) == ["000012", "000858"]
    assert _codes(UniverseQuery(board="创业板", limit=1)) == ["300750"]


def test_limit_larger_than_pool_returns_all():
    assert len(_codes(UniverseQuery(board="科创板", limit=99))) == 1


# 7. 数据源不可用 → DataUnavailable（最重要）----------------------------------------

def test_snapshot_failure_raises_data_unavailable_not_empty():
    """mock 数据源抛错时，resolve 必须让它穿透：把「环境取不到数」如实暴露。

    变异目标：若实现里 try/except 吞掉异常返回 []，本测试必红。
    """
    def broken_snapshot():
        raise universe.DataUnavailable("全市场快照两个入口均不可用")

    with pytest.raises(universe.DataUnavailable, match="不可用"):
        universe.resolve(UniverseQuery(board="主板"), snapshot=broken_snapshot)


def test_conditional_query_without_snapshot_is_a_clear_error():
    """条件型查询必须提供快照：None 不是「空结果」而是「没给数据」的编程错误。"""
    with pytest.raises(ValueError):
        universe.resolve(UniverseQuery(board="主板"), snapshot=None)


# 8. describe() ----------------------------------------------------------------

def test_describe_contains_every_active_condition():
    q = UniverseQuery(board="主板", pe_min=15, pe_max=20, pb_max=2.5,
                      mcap_min=500, mcap_max=2000, turnover_min=3,
                      exclude_st=True, limit=50)
    d = q.describe()
    assert "主板" in d
    assert "15≤PE≤20" in d
    assert "PB≤2.5" in d
    assert "500≤市值≤2000亿" in d
    assert "换手≥3%" in d
    assert "剔除ST" in d
    assert "前50只" in d


def test_describe_one_sided_ranges():
    assert "PE≤20" in UniverseQuery(pe_max=20).describe()
    assert "PE≥15" in UniverseQuery(pe_min=15).describe()
    assert "市值≥500亿" in UniverseQuery(mcap_min=500).describe()
    assert "换手≤8%" in UniverseQuery(turnover_max=8).describe()


def test_describe_explicit_list():
    d = universe.from_codes(["600519", "000858"]).describe()
    assert "显式" in d and "2" in d


def test_describe_board_only():
    assert UniverseQuery(board="科创板").describe() == "科创板"


# 9. 空条件 ----------------------------------------------------------------------

def test_empty_query_is_rejected_not_all_market():
    """空条件（未选板块、未给任何区间、又非显式列表）→ 拒绝求值。

    理由：全市场 ≈ 5000 只，静默把「忘填条件」当「全 A 池」几乎肯定不是用户本意，
    而且和「条件真的匹配 0 只」无法区分（DataUnavailable 同款教训：失败要能分辨）。
    """
    with pytest.raises(ValueError, match="空"):
        universe.resolve(UniverseQuery(), snapshot=_SNAPSHOT)


# ---------------------------------------------------------------------------
# API 层（不触网：monkeypatch 掉快照加载函数）
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi import FastAPI

    from api import universes

    app = FastAPI()
    app.include_router(universes.build_universe_router())
    with TestClient(app) as c:
        yield c


def test_api_resolve_returns_codes_description_count(client, monkeypatch):
    from api import universes
    monkeypatch.setattr(universes, "_load_snapshot", lambda: _SNAPSHOT)
    r = client.post("/api/universes/resolve", json={"board": "主板", "pe_max": 25})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["codes"] == ["000858", "002594", "600000"]  # 000012 pe 缺值不入选
    assert data["count"] == 3
    assert "主板" in data["description"] and "PE≤25" in data["description"]


def test_api_resolve_returns_502_when_source_down(client, monkeypatch):
    from api import universes
    from research.astock import DataUnavailable

    def broken():
        raise DataUnavailable("push2 与 push2delay 均不可用")
    monkeypatch.setattr(universes, "_load_snapshot", broken)
    r = client.post("/api/universes/resolve", json={"board": "主板"})
    assert r.status_code == 502
    assert "不可用" in r.json()["detail"]


def test_api_resolve_rejects_empty_query(client):
    r = client.post("/api/universes/resolve", json={})
    assert r.status_code == 400  # 400 而非 200 空列表：与「匹配 0 只」可分辨
    r2 = client.post("/api/universes/resolve",
                     json={"codes": ["600519"], "board": "主板"})
    assert r2.status_code == 400  # 显式列表与其他条件互斥


def test_api_resolve_explicit_codes_needs_no_snapshot(client):
    r = client.post("/api/universes/resolve", json={"codes": ["600519", "000858"]})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["codes"] == ["600519", "000858"] and data["count"] == 2


def test_api_fields_lists_form_metadata(client):
    r = client.get("/api/universes/fields")
    assert r.status_code == 200
    fields = r.json()["data"]
    names = {f["field"] for f in fields}
    assert {"board", "pe_min", "pe_max", "pb_min", "pb_max", "mcap_min",
            "mcap_max", "turnover_min", "turnover_max", "exclude_st", "limit"} <= names
    board = next(f for f in fields if f["field"] == "board")
    assert board["type"] == "enum" and "科创板" in board["options"]
