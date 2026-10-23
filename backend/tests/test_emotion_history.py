"""情绪历史落库（ROUND2 阶段 1）。

用户要「最高连板折线」「情绪柱状图」，而所有接口只返回当天快照。
这些测试锁住存储层的三条纪律：幂等、不写假零、升序返回。
"""

import sqlite3

import pytest

from api import emotion_store


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    emotion_store.ensure_schema(c)
    yield c
    c.close()


def _snap(date="2026-10-22", **over):
    base = {
        "date": date,
        "zt_count": 33, "dt_count": 49, "zb_count": 23,
        "max_boards": 5, "lianban_count": 9, "yzt_count": 51,
        "seal_rate": 0.589, "break_rate": 0.411, "promotion_rate": 0.176,
    }
    base.update(over)
    return base


class TestUpsert:
    def test_writes_and_reads_back(self, conn):
        emotion_store.upsert_snapshot(conn, _snap(), now=1.0)
        rows = emotion_store.history(conn, days=10)
        assert len(rows) == 1
        assert rows[0]["date"] == "2026-10-22"
        assert rows[0]["zt_count"] == 33
        assert rows[0]["max_boards"] == 5

    def test_idempotent_same_date_updates_not_duplicates(self, conn):
        """回填脚本会重跑，同一天不能变成两行。"""
        emotion_store.upsert_snapshot(conn, _snap(zt_count=33), now=1.0)
        emotion_store.upsert_snapshot(conn, _snap(zt_count=99), now=2.0)
        rows = emotion_store.history(conn, days=10)
        assert len(rows) == 1, "同一天重复写必须更新，不能插重复行"
        assert rows[0]["zt_count"] == 99, "应该是后写的覆盖先写的"

    def test_missing_counts_become_zero_not_null(self, conn):
        """计数缺失写 0，不能写 NULL —— NULL 会让 AVG/SUM 变 NaN，图表直接断。"""
        snap = _snap()
        del snap["dt_count"]
        emotion_store.upsert_snapshot(conn, snap, now=1.0)
        assert emotion_store.history(conn, 10)[0]["dt_count"] == 0

    def test_rates_may_be_null(self, conn):
        """比率允许 NULL：分母为 0 时「封板率」根本没有意义，写 0 会撒谎。"""
        emotion_store.upsert_snapshot(conn, _snap(seal_rate=None), now=1.0)
        assert emotion_store.history(conn, 10)[0]["seal_rate"] is None

    def test_rejects_snapshot_without_date(self, conn):
        snap = _snap()
        del snap["date"]
        with pytest.raises(ValueError):
            emotion_store.upsert_snapshot(conn, snap, now=1.0)


class TestHistory:
    def test_returns_ascending_for_charting(self, conn):
        """升序：画图要时间从左到右，前端不该自己再排一遍。"""
        for d in ("2026-10-20", "2026-10-21", "2026-10-22"):
            emotion_store.upsert_snapshot(conn, _snap(date=d), now=1.0)
        dates = [r["date"] for r in emotion_store.history(conn, 10)]
        assert dates == ["2026-10-20", "2026-10-21", "2026-10-22"]

    def test_limit_keeps_most_recent(self, conn):
        """`days=2` 要给**最近**两天，不是最早两天。"""
        for d in ("2026-10-15", "2026-10-20", "2026-10-21", "2026-10-22"):
            emotion_store.upsert_snapshot(conn, _snap(date=d), now=1.0)
        dates = [r["date"] for r in emotion_store.history(conn, 2)]
        assert dates == ["2026-10-21", "2026-10-22"]

    def test_empty_table_returns_empty_list(self, conn):
        assert emotion_store.history(conn, 60) == []


def test_schema_is_idempotent(conn):
    """ensure_schema 会每次请求都调（见 api/market.py），必须可重复执行。"""
    emotion_store.ensure_schema(conn)
    emotion_store.ensure_schema(conn)
