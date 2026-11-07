"""情绪历史的落库与查询（ROUND2 阶段 1）。

## 为什么需要这张表

用户要「市场情绪柱状图」「最高连板折线」，而**所有接口只返回当天快照**。
一条只有今天一个点的折线画出来是一颗孤零零的点，比数字还糟。
用户原话说得很准：「单纯的独立数字看不出来什么，需要跟之前的数据进行比对」。

比对需要历史。库里原本 12 张表全是业务数据，没有一张时间序列 —— 这是结构性缺口。

## 设计要点

1. **只存聚合计数，不存个股**。守产品「零标的」红线：`lianban_stocks` 这种
   个股清单不进历史表（存了就等于在库里堆积甩名单）。
2. **按 date 幂等 upsert**。回填脚本可中断续跑；重复跑不产生重复行。
3. **区分「非交易日」与「取数失败」**。非交易日上游返回空池是**正常结果**，
   应该记下 `is_trading_day=False`；取数失败则不该写任何行 ——
   否则会把「今天没取到」永久固化成「这天 0 跌停」。
"""

from __future__ import annotations

import sqlite3
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS emotion_daily (
    date            TEXT PRIMARY KEY,        -- YYYY-MM-DD（交易日）
    zt_count        INTEGER NOT NULL,        -- 涨停家数
    dt_count        INTEGER NOT NULL,        -- 跌停家数
    zb_count        INTEGER NOT NULL,        -- 炸板家数
    max_boards      INTEGER NOT NULL,        -- 最高连板数
    lianban_count   INTEGER NOT NULL,        -- 2 板及以上家数
    yzt_count       INTEGER NOT NULL DEFAULT 0,  -- 昨日涨停家数（算晋级率用）
    seal_rate       REAL,                    -- 封板率（可空：无尝试时为 Null）
    break_rate      REAL,                    -- 炸板率
    promotion_rate  REAL,                    -- 晋级率
    updated_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_emotion_date ON emotion_daily(date DESC);
"""

# 落库的字段（与 SCHEMA 对应，顺序固定）。抽出来是为了 upsert 与 row→dict 两处
# 用同一份清单，加字段时不会漏掉一边。
FIELDS: tuple[str, ...] = (
    "date", "zt_count", "dt_count", "zb_count", "max_boards",
    "lianban_count", "yzt_count", "seal_rate", "break_rate", "promotion_rate",
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_snapshot(conn: sqlite3.Connection, snap: dict[str, Any], now: float) -> None:
    """写/更新一天的快照。幂等 —— 同一天重复写只更新，不插重复行。

    `date` 必须已归一成 `YYYY-MM-DD`（上游给的是 `YYYYMMDD`，转换在调用方做，
    因为这里是存储层，不该知道上游的格式）。
    """
    if not snap.get("date"):
        raise ValueError("snapshot 缺 date")

    values = [snap.get(f) for f in FIELDS]
    # 计数类字段不允许 None：写进去会让后续 SUM/AVG 变成 NaN。
    # 缺失视为 0（上游确实会因为接口参数问题返回空池，见跌停池的 sort 坑）。
    for i, name in enumerate(FIELDS):
        if name in ("seal_rate", "break_rate", "promotion_rate"):
            continue                      # 比率允许 NULL（分母为 0 时无意义）
        if values[i] is None:
            values[i] = 0

    placeholders = ",".join("?" for _ in FIELDS)
    updates = ",".join(f"{f}=excluded.{f}" for f in FIELDS if f != "date")
    conn.execute(
        f"INSERT INTO emotion_daily ({','.join(FIELDS)}, updated_at) "
        f"VALUES ({placeholders}, ?) "
        f"ON CONFLICT(date) DO UPDATE SET {updates}, updated_at=excluded.updated_at",
        (*values, now),
    )


def history(conn: sqlite3.Connection, days: int = 60) -> list[dict[str, Any]]:
    """最近 N 条快照，**按日期升序**返回（画图要时间从左到右）。"""
    rows = conn.execute(
        f"SELECT {','.join(FIELDS)} FROM emotion_daily ORDER BY date DESC LIMIT ?",
        (days,),
    ).fetchall()
    out = [dict(r) for r in rows]
    out.reverse()
    return out
