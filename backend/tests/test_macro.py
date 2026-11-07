"""D4：宏观时间序列端点（ROUND3 D4）。

七条端点全部经 `VendorBridge` 调 data-service 的 vendor 能力 ——
这里**不 mock vendor 函数本身**，mock 的是 bridge（进程边界），因为：
  - vendor 是仓库里装的**真**实现（唯一取数实现，AGENTS 反模式）；
    在 backend 里再 mock 它等于另写一套取数事实。
  - bridge 是测试与 vendor 之间天然的缝：JSON 子进程协议就是契约。

契约（与 frontend/src/lib/api.ts 的 MacroSeries / MacroCurve 对齐）：
  series → {"available", "reason", "unit", "points": [{period, value}]}
  curve  → {"available", "reason", "unit", "date", "points": [{tenor, value}]}
硬约束：取不到一律 available=False + reason 非空，**不返回空数组冒充成功**
（空数组会被前端画成一条平线，比不画更误导），也不编造 / 插值 / 补 0。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from alpha.vendor_bridge import VendorError
from api.macro import build_macro_router

TENORS = ["3m", "6m", "1y", "3y", "5y", "7y", "10y", "30y"]


class FakeBridge:
    """vendor 桩：invoke 结果按（能力名, 元组化实参）查表；查不到抛 VendorError。"""

    def __init__(self, results: dict, calls: list[str] | None = None):
        self.results = results
        self.calls = calls if calls is not None else []

    def available(self) -> bool:  # pragma: no cover
        return True

    def invoke(self, name, *, args=None, kwargs=None):
        self.calls.append(name)
        result = self.results.get(name)
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise VendorError(f"测试桩没有为 {name} 设定返回值")
        if callable(result):
            return result(args=list(args or []), kwargs=dict(kwargs or {}))
        return result


def frame(columns: list[str], rows: list[list]) -> dict:
    """worker 序列化 DataFrame 的形状（与 /api/v1/invoke 实测一致）。"""
    return {"columns": columns, "rows": rows}


def make_client(results: dict) -> tuple[TestClient, FakeBridge]:
    bridge = FakeBridge(results)
    app = FastAPI()
    app.include_router(build_macro_router(bridge=bridge))
    return TestClient(app), bridge


# ---- PMI -------------------------------------------------------------------

def test_pmi_latest_point():
    """nbs_pmi 只回最新一期：如实返回单点（reason 说明仅有一期），不编造历史。"""
    client, b = make_client({"nbs_pmi": {
        "period": "2026-09", "manufacturing_pmi": 50.1,
        "non_manufacturing_pmi": 50.2, "composite_pmi": 50.7,
    }})
    body = client.get("/api/macro/pmi").json()
    assert body["available"] is True
    assert body["unit"] == "%"
    assert body["points"] == [{"period": "2026-09", "value": 50.1}]
    assert b.calls == ["nbs_pmi"]


def test_pmi_missing_value_reports_unavailable():
    """vendor 回了正文却解析不到制造业 PMI（None）→ 无点可画，如实降级。"""
    client, _ = make_client({"nbs_pmi": {"period": "2026-09", "manufacturing_pmi": None}})
    body = client.get("/api/macro/pmi").json()
    assert body["available"] is False
    assert body["reason"]


def test_pmi_vendor_error_degrades():
    client, _ = make_client(
        {"nbs_pmi": VendorError("国家统计局最新发布页未找到「采购经理指数」条目")})
    body = client.get("/api/macro/pmi").json()
    assert body["available"] is False
    assert body["reason"]


# ---- 社融 ------------------------------------------------------------------

def sf_year_rows(year: int, months) -> list[list]:
    return [[f"{year}-{m:02d}", 1000.0 + m] for m in months]


def test_social_financing_concatenates_three_years():
    """近 36 个月 = 最近三个自然年的 pboc 调用按月拼起来；升序，空行要丢。"""
    by_year = {
        2024: frame(["month", "afre_total"], sf_year_rows(2024, range(1, 13))),
        2025: frame(["month", "afre_total"], sf_year_rows(2025, range(1, 13))),
        2026: frame(["month", "afre_total"],
                    [[None, 1.0], *sf_year_rows(2026, range(1, 10))]),
    }
    # 用 callable 按实参分派：FakeBridge 本来就支持这条件缝。
    # 让**生产代码**去识别「年份→表」的字典形状是错的 —— 真实 vendor 按年返回一张表。
    client, b = make_client({
        "pboc_social_financing": lambda args, kwargs: by_year[args[0]],
    })
    body = client.get("/api/macro/social-financing").json()
    assert body["available"] is True
    assert body["unit"] == "亿元"
    pts = body["points"]
    assert len(pts) == 33  # 12 + 12 + 9（2026 只发布到 9 月）
    assert [p["period"] for p in pts] == sorted(p["period"] for p in pts)
    assert pts[0] == {"period": "2024-01", "value": 1001.0}
    assert pts[-1] == {"period": "2026-09", "value": 1009.0}
    assert b.calls == ["pboc_social_financing"] * 3


def test_social_financing_skips_failed_year():
    """某一年取数失败（年份页改版）不整条报废：凑得 ≥12 个月就算成功。"""
    by_year = {
        2024: frame(["month", "afre_total"], sf_year_rows(2024, range(1, 13))),
        2025: frame(["month", "afre_total"], sf_year_rows(2025, range(1, 13))),
        2026: VendorError("人民银行索引页未找到「XXXX年统计数据」链接"),
    }

    def dispatch(args, kwargs):
        r = by_year[args[0]]
        if isinstance(r, Exception):
            raise r
        return r

    client, _ = make_client({"pboc_social_financing": dispatch})
    body = client.get("/api/macro/social-financing").json()
    assert body["available"] is True
    assert len(body["points"]) == 24
    assert body["points"][0]["period"] == "2024-01"


def test_social_financing_all_years_fail():
    def dispatch(_args, _kwargs):
        raise VendorError("人民银行索引页未找到")

    client, _ = make_client({"pboc_social_financing": dispatch})
    body = client.get("/api/macro/social-financing").json()
    assert body["available"] is False
    assert body["reason"]


# ---- 中债收益率曲线 ---------------------------------------------------------

def test_cn_yields_latest_curve():
    cols = ["date", "curve", *TENORS]
    rows = [
        ["2026-10-21", "中债国债收益率曲线", *[2.0] * 8],
        ["2026-10-22", "中债国债收益率曲线", 1.15, 1.16, 1.18, 1.27, 1.35, 1.46, 1.64, 2.06],
    ]
    client, b = make_client({"chinabond_yield_curve": frame(cols, rows)})
    body = client.get("/api/macro/cn-yields").json()
    assert body["available"] is True
    assert body["date"] == "2026-10-22"
    assert body["unit"] == "%"
    assert [p["tenor"] for p in body["points"]] == TENORS
    assert body["points"][6] == {"tenor": "10y", "value": 1.64}


def test_cn_yields_vendor_error():
    client, _ = make_client(
        {"chinabond_yield_curve": VendorError("中债收益率页面表头改变，不能按原列序解析")})
    body = client.get("/api/macro/cn-yields").json()
    assert body["available"] is False
    assert body["reason"]


# ---- 回购利率 ---------------------------------------------------------------

def test_repo_last_60_days():
    # 80 个交易日，FR001 = 序号（1..80）。断言两件事：
    #   ① 只保留最近 60 条；② 最新一条是「日期最大」的那条，不是数组最后一条。
    # 顺带把行顺序打乱 —— 依赖上游顺序的实现会在这里露馅。
    rows = [[f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", float(i + 1), 1.5, 1.6]
            for i in range(80)]
    rows = rows[::-1]
    client, _ = make_client(
        {"repo_fixing_rates": frame(["date", "FR001", "FR007", "FR014"], rows)})
    body = client.get("/api/macro/repo").json()
    assert body["available"] is True
    assert body["unit"] == "%"
    assert len(body["points"]) == 60  # 只留最近 60 个交易日
    assert body["points"][-1]["value"] == 80.0
    assert body["points"][0]["value"] == 21.0
    assert [p["period"] for p in body["points"]] == sorted(p["period"] for p in body["points"])


def test_repo_vendor_error():
    client, _ = make_client(
        {"repo_fixing_rates": VendorError("货币网定盘利率 CSV 格式改变")})
    body = client.get("/api/macro/repo").json()
    assert body["available"] is False
    assert body["reason"]


# ---- LPR --------------------------------------------------------------------

def test_lpr_success_path_shapes_points():
    """vendor 修好后（东财共用 helper 恢复）端点应出 LPR 1Y 月度点。"""
    rows = [["2026-08-20", 3.0, 3.5], ["2026-07-20", 3.1, 3.6], ["2026-06-20", 3.2, 3.7]]
    client, _ = make_client(
        {"lpr_history": frame(["date", "lpr_1y", "lpr_5y"], rows)})
    body = client.get("/api/macro/lpr").json()
    assert body["available"] is True
    assert body["unit"] == "%"
    assert [p["value"] for p in body["points"]] == [3.2, 3.1, 3.0]
    assert [p["period"] for p in body["points"]] == ["2026-06", "2026-07", "2026-08"]


def test_lpr_vendor_error_degrades_with_reason():
    """实测（2026-10-22）：vendor 的 lpr_history 经 loader 加载后调用会因东财
    共用 helper 的 EM_SESSION 被剥掉而 NameError。端点必须如实降级，不伪造。"""
    client, _ = make_client(
        {"lpr_history": VendorError("NameError: name 'EM_SESSION' is not defined")})
    body = client.get("/api/macro/lpr").json()
    assert body["available"] is False
    assert body["reason"]


# ---- 北向 / 两融 -------------------------------------------------------------

def test_northbound_unavailable_without_fake_series():
    """北向日频历史当前 vendor 拿不出（本地自缓存 CSV 为空、上游收紧盘中披露、
    现有能力只有盘中分钟流向）→ 如实 available=False，不发起调用、不伪造序列。"""
    client, b = make_client({})
    body = client.get("/api/macro/northbound").json()
    assert body["available"] is False
    assert body["reason"]
    assert body["points"] == []
    assert not b.calls


def test_margin_unavailable_without_fake_series():
    """两融：vendor 只有单股明细（loader 下调不通）与官方单日快照（逐日逐所拉
    全市场，60 日要 120+ 次子进程调用，不可行）→ available=False + 非空 reason。"""
    client, b = make_client({})
    body = client.get("/api/macro/margin").json()
    assert body["available"] is False
    assert body["reason"]
    assert body["points"] == []
    assert not b.calls
