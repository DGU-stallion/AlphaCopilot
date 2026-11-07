"""Universes as query —— 标的池 REST（M3-2）。薄端点：校验 → alpha.universe 纯函数 → {data:...}。

  POST /api/universes/resolve   body=查询条件 → {codes, description, count, data_as_of}
  GET  /api/universes/fields    条件字段元信息（前端渲染表单用）

纪律（与 api/market.py 一致）：
  · 全部 {data:...} 契约；
  · 数据源不可用 → 502（**不是 200 空列表**：空列表与「今天真的没有符合条件的股票」
    无法区分，ADR-0012「数字可信」与 test_data_observability 的约定）；
  · 条件不成立（空条件 / 显式列表混条件 / board 非法）→ 400；
  · 快照加载失败不吞：alpha.universe.load_snapshot 抛 DataUnavailable 时原样转 502。
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from alpha import universe
from research.astock import DataUnavailable


class UniverseQueryIn(BaseModel):
    """POST /universes/resolve 的 body。全部字段可选；至少要有一个生效条件。"""

    codes: list[str] | None = None
    board: str | None = None
    pe_min: float | None = Field(None, ge=0, description="PE(TTM) 下限（倍）")
    pe_max: float | None = Field(None, ge=0)
    pb_min: float | None = Field(None, ge=0)
    pb_max: float | None = Field(None, ge=0)
    mcap_min: float | None = Field(None, ge=0, description="亿元")
    mcap_max: float | None = Field(None, ge=0)
    turnover_min: float | None = Field(None, ge=0, description="%")
    turnover_max: float | None = Field(None, ge=0)
    exclude_st: bool = False
    limit: int | None = Field(None, gt=0, description="最多返回 N 只")


# 快照 TTL 缓存（秒）。盘中 PE/PB/换手随行情动，5 分钟窗口内同一条件重复求值可复用，
# 也避免每次 resolve 都全市场一把抓。fail 不缓存（下次立即重试）。
_SNAPSHOT_TTL = 300
_snapshot_cache: dict[str, object] = {"at": 0.0, "snap": None}


def _load_snapshot() -> dict[str, dict]:
    now = time.monotonic()
    snap, at = _snapshot_cache["snap"], float(_snapshot_cache["at"])
    if snap is not None and now - at < _SNAPSHOT_TTL:
        return snap
    snap = universe.load_snapshot()
    _snapshot_cache["snap"], _snapshot_cache["at"] = snap, now
    return snap


def build_universe_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/universes/resolve")
    def resolve_universe(body: UniverseQueryIn) -> dict:
        """把池条件按当前数据求值成代码列表（确定性；同数据必得同结果）。"""
        try:
            q = universe.UniverseQuery(
                codes=tuple(body.codes) if body.codes else (),
                board=body.board,
                pe_min=body.pe_min, pe_max=body.pe_max,
                pb_min=body.pb_min, pb_max=body.pb_max,
                mcap_min=body.mcap_min, mcap_max=body.mcap_max,
                turnover_min=body.turnover_min, turnover_max=body.turnover_max,
                exclude_st=body.exclude_st,
                limit=body.limit,
            )
        except universe.UniverseConditionError as e:  # board 非法 / 代码非法
            raise HTTPException(400, f"查询条件不成立：{e}") from e
        if q.is_empty():
            raise HTTPException(400, "查询条件为空：必须给显式 codes 或至少一个过滤条件")
        try:
            snap = None if q.codes else _load_snapshot()  # 显式列表不需要数据
            codes = universe.resolve(q, snapshot=snap)
        except DataUnavailable as e:
            raise HTTPException(502, f"全市场快照数据源不可用：{e}") from e
        except universe.UniverseConditionError as e:
            raise HTTPException(400, f"查询条件不成立：{e}") from e
        return {"data": {"codes": codes, "count": len(codes),
                         "description": q.describe()}}

    @router.get("/universes/fields")
    def fields() -> dict:
        """条件字段元信息（字段名 / 类型 / 单位 / 选项），前端渲染表单用。"""
        return {"data": universe.QUERY_FIELDS}

    return router
