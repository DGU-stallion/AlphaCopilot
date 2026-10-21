"""M3-1 Run registry + M3-3 View 模型 —— 共享地基的契约测试。

这是 M3 的地基：Run 让「每次回测可比较、可复现、可重跑」成立，
View 让「页面 = 保存的 View 集合」成立（ADR-0012）。

为什么 Run 必须落库而不是只用 runs/ 目录：
  - 「两个 Run 对比」需要可查询的指标与参数（目录只能靠扫文件）
  - dataAsOf 必须能直接过滤（「只看今天数据算出来的」）
  - codeHash 是「同一个策略代码」的判据，改一个字就该是新 Run

这里只测**约定**，不测具体实现细节：能存、能查、能比较、幂等。
"""

import time

import pytest

from api.store import Store


@pytest.fixture()
def store():
    s = Store(":memory:")
    yield s
    s.close()


def _run_kwargs(**over):
    base = {
        "kind": "backtest",
        "params": {"symbol": "600519", "fast": 20, "slow": 60},
        "code_hash": "abc123",
        "data_as_of": "2026-10-21",
        "metrics": {"总收益": -0.1688, "夏普": -1.64},
        "artifact_ids": ["equity", "drawdown", "metrics"],
    }
    base.update(over)
    return base


class TestRunRegistry:
    def test_create_and_get_roundtrip(self, store):
        rid = store.runs.create(**_run_kwargs())
        r = store.runs.get(rid)
        assert r is not None
        assert r["kind"] == "backtest"
        assert r["params"]["symbol"] == "600519"
        assert r["metrics"]["夏普"] == -1.64
        assert r["artifact_ids"] == ["equity", "drawdown", "metrics"]

    def test_params_and_metrics_are_json_not_string_soup(self, store):
        """必须是结构化 JSON：前端要直接读字段，不该二次解析字符串。"""
        rid = store.runs.create(**_run_kwargs())
        r = store.runs.get(rid)
        assert isinstance(r["params"], dict)
        assert isinstance(r["metrics"], dict)

    def test_list_newest_first(self, store):
        a = store.runs.create(**_run_kwargs())
        time.sleep(0.01)
        b = store.runs.create(**_run_kwargs())
        ids = [x["id"] for x in store.runs.list_recent()]
        assert ids.index(b) < ids.index(a)

    def test_list_filters_by_kind(self, store):
        store.runs.create(**_run_kwargs(kind="backtest"))
        store.runs.create(**_run_kwargs(kind="factor"))
        assert len(store.runs.list_recent(kind="backtest")) == 1
        assert len(store.runs.list_recent(kind="factor")) == 1

    def test_list_filters_by_data_as_of(self, store):
        """「只看今天数据算出来的」是常见诉求；靠 dataAsOf 过滤，不用全表扫。"""
        store.runs.create(**_run_kwargs(data_as_of="2026-10-20"))
        store.runs.create(**_run_kwargs(data_as_of="2026-10-21"))
        rows = store.runs.list_recent(data_as_of="2026-10-21")
        assert len(rows) == 1
        assert rows[0]["data_as_of"] == "2026-10-21"

    def test_missing_run_returns_none(self, store):
        assert store.runs.get("nope") is None

    def test_artifact_ids_default_to_empty_list(self, store):
        """没产 artifact 的 Run（比如纯计算）也要能存。"""
        rid = store.runs.create(**_run_kwargs(artifact_ids=None))
        assert store.runs.get(rid)["artifact_ids"] == []


class TestRunDiff:
    def test_diff_reports_metric_deltas(self, store):
        """M3-4 的基础：两个 Run 的指标差异要能直接算出来。"""
        a = store.runs.create(**_run_kwargs(metrics={"总收益": -0.10, "夏普": -1.0}))
        b = store.runs.create(**_run_kwargs(metrics={"总收益": 0.05, "夏普": 0.8}))
        d = store.runs.diff(a, b)
        assert d["metrics"]["总收益"]["a"] == -0.10
        assert d["metrics"]["总收益"]["b"] == 0.05
        assert d["metrics"]["总收益"]["delta"] == pytest.approx(0.15)

    def test_diff_marks_metrics_only_in_one_side(self, store):
        """只有一侧有的指标不能当成 delta=0（那会让人以为没变化）。"""
        a = store.runs.create(**_run_kwargs(metrics={"总收益": -0.10}))
        b = store.runs.create(**_run_kwargs(metrics={"总收益": -0.10, "新增": 1.0}))
        d = store.runs.diff(a, b)
        assert d["metrics"]["新增"]["a"] is None
        assert d["metrics"]["新增"]["delta"] is None   # 不能是 0

    def test_diff_reports_param_changes(self, store):
        """参数变了才说明「这两个 Run 不是同一个实验设计」。"""
        a = store.runs.create(**_run_kwargs(params={"fast": 20, "slow": 60}))
        b = store.runs.create(**_run_kwargs(params={"fast": 10, "slow": 60}))
        d = store.runs.diff(a, b)
        assert d["params"]["fast"] == {"a": 20, "b": 10}
        assert "slow" not in d["params"]    # 没变的不列

    def test_diff_of_same_run_is_empty(self, store):
        a = store.runs.create(**_run_kwargs())
        d = store.runs.diff(a, a)
        assert d["params"] == {}
        assert all(v["delta"] == 0 for v in d["metrics"].values())

    def test_diff_missing_run_raises(self, store):
        a = store.runs.create(**_run_kwargs())
        with pytest.raises(KeyError):
            store.runs.diff(a, "nope")


class TestViewModel:
    """View = 保存的「看什么」。页面 = View 的集合（ADR-0012）。"""

    def test_create_and_get(self, store):
        vid = store.views.create(
            name="白酒三巨头 60 日相关",
            kind="correlation",
            params={"symbols": ["600519", "000858"], "window": 60},
        )
        v = store.views.get(vid)
        assert v["name"] == "白酒三巨头 60 日相关"
        assert v["params"]["window"] == 60

    def test_pinned_views_listed_separately(self, store):
        """Pin 是「我天天要看这个」，与「我存过」是两件事。"""
        store.views.create(name="A", kind="correlation", params={})
        vid = store.views.create(name="B", kind="factor", params={})
        store.views.set_pinned(vid, True)
        pinned = store.views.list_pinned()
        assert [v["name"] for v in pinned] == ["B"]

    def test_unpin(self, store):
        vid = store.views.create(name="A", kind="correlation", params={})
        store.views.set_pinned(vid, True)
        store.views.set_pinned(vid, False)
        assert store.views.list_pinned() == []

    def test_view_links_to_run(self, store):
        """View 可指回「上次用这个 View 跑出来的 Run」，用于「重跑」与「对比历史」。"""
        rid = store.runs.create(**_run_kwargs())
        vid = store.views.create(name="A", kind="backtest", params={}, last_run_id=rid)
        assert store.views.get(vid)["last_run_id"] == rid


class TestIdempotentMigration:
    def test_migrate_twice_is_safe(self, store):
        """迁移必须幂等：每次 create_app 都会跑一遍（builtin 页靠它自愈）。"""
        store.migrate()
        store.migrate()
        rid = store.runs.create(**_run_kwargs())
        assert store.runs.get(rid) is not None
