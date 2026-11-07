#!/usr/bin/env python3
"""回填情绪历史（ROUND2 阶段 1）。

## 用法

    cd backend
    python3 ../scripts/backfill-emotion.py              # 默认 60 个交易日
    python3 ../scripts/backfill-emotion.py --days 250
    python3 ../scripts/backfill-emotion.py --dry-run    # 只打印，不写库

## 为什么需要它

`emotion_daily` 表是**从今天开始**积累的。不先回填，用户想要的
「最高连板折线」「情绪柱状图」要等 60 个交易日才有形状 —— 那时已经没人在看了。

## 三个必须小心的地方（都是实测踩出来的）

1. **跌停池只认 `sort=fund:asc`**。用默认排序返回空数组而不报错，
   会静默把「这天没跌停」永久写进历史。回填最怕这种静默错误。
2. **非交易日返回空池是正常结果**，不写行（不能记成 0 涨停）。
3. **幂等**：按 date upsert，中断了重跑不会产生重复行，也不会覆盖成更差的数据。

## 为什么串行不并发

单日三池约 3.3 秒，60 天约 3.5 分钟。并发会同时打 3 个上游池 × N 线程，
触发风控的风险远大于省下来的两分钟。
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "backend"))

from api import emotion_store  # noqa: E402
from research import astock, market  # noqa: E402
from api.store import Store  # noqa: E402

BEIJING = dt.timezone(dt.timedelta(hours=8))


def trading_days_back(n: int, end: dt.date | None = None) -> list[dt.date]:
    """往前取 n 个**自然日**（非交易日由上游返回空池来过滤，不在这里猜节假日）。

    为什么不在这里判节假日：A 股节假日安排每年不同，硬编码一张表迟早错。
    上游返回空池就是最权威的「这天不开市」判据。
    """
    end = end or dt.datetime.now(BEIJING).date()
    return [end - dt.timedelta(days=i) for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60, help="回溯自然日数（默认 60）")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    ap.add_argument("--db", default=None, help="SQLite 路径（默认同 api.main）")
    args = ap.parse_args()

    db_path = args.db or str(_REPO / "backend" / "workspace" / "alphacopilot.db")
    store = Store(db_path)
    emotion_store.ensure_schema(store.conn)

    days = trading_days_back(args.days)
    written = skipped = failed = 0
    t0 = time.time()

    for i, d in enumerate(days, 1):
        ymd = d.strftime("%Y%m%d")
        try:
            snap = market._emotion_for_date(ymd)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"[{i}/{len(days)}] {ymd}  失败: {type(e).__name__}: {e}")
            continue

        if not snap:
            # 两种情况都返回空池，但含义不同（实测 2026-10-22）：
            #   · 非交易日（周末 / 中秋 09-25 / 国庆 10-01—10-07）→ 本来就不开市
            #   · **超出上游窗口**（实测只保留约 28 天：09-24 有数据、09-23 没有）
            # 两者都不该写行（不能记成「这天 0 涨停」），但提示语必须如实分开，
            # 否则后来人会把「窗口不够」误认为自己的 bug。
            skipped += 1
            print(f"[{i}/{len(days)}] {ymd}  空池（非交易日，或超出上游 ~28 天窗口）")
            continue

        if args.dry_run:
            print(
                f"[{i}/{len(days)}] {ymd}  zt={snap['zt_count']:<3} dt={snap['dt_count']:<3} "
                f"zb={snap['zb_count']:<3} max_boards={snap['max_boards']:<2} "
                f"lianban={snap['lianban_count']}"
            )
        else:
            emotion_store.upsert_snapshot(store.conn, snap, time.time())
            print(
                f"[{i}/{len(days)}] {ymd}  写入 zt={snap['zt_count']:<3} dt={snap['dt_count']:<3} "
                f"max_boards={snap['max_boards']}"
            )
        written += 1

    store.conn.commit()
    store.close()

    el = time.time() - t0
    print(
        f"\n完成：写入/更新 {written} 天，跳过（非交易日或超窗）{skipped} 天，失败 {failed} 天，"
        f"耗时 {el:.1f}s"
    )
    if written > 0 and written < 20:
        # 不报错（这不是错误），但要说清楚，否则下一个人会以为回填没跑对。
        print(
            "\n注意：写入天数少于 20 是正常的 —— 东财涨停池只保留约 28 天历史\n"
            "（实测 2026-09-24 有数据、2026-09-23 没有；akshare 同源同限制）。\n"
            "超出部分只能靠每日落库慢慢积累。"
        )
    if args.dry_run:
        print("（dry-run，未写库）")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
