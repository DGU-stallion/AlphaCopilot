"""provenance 落地与盖章权测试（M1-7）—— 先红。

## 这条测试保护的是什么

ADR-0012「已决 1」把「数字只来自确定性函数」这条硬规则从**审计 agent 的代码**
改成**卡产物落库那一刻**。核心断言只有一句：

> `provenance.kind = "deterministic"` 只能由服务端铸造；agent 无权自称。

为什么这样改：agent 有 bash，可以 `python3 -c "..."` 自己算夏普，这条路不产
`code.py`，事后 review 抓不到。而「这段代码算不算绕开了库函数」是语义判断，
写不成规则。所以执法点后移到产物上——**agent 自己算的数字照样能显示，
但必须挂 AI 角标**。

这条测试就是那句规则的执行体：伪造 manifest 声称 deterministic → 必须被改写。

## seam

`api.artifacts.ingest_run(store, run_dir, message_id)` —— 服务端摄取产物的唯一入口。
测试通过它观察行为，不碰内部校验函数，因此校验逻辑怎么重写都不影响本文件。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.artifacts import ManifestError, ingest_run
from api.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def mid(store):
    """一条真实的 assistant 消息 id。

    artifact 表对 message_id 有外键约束，所以每条测试都要先建出这条消息——
    这不是测试的冗余，它同时验证了「artifact 必须挂在一条存在的消息上」。
    """
    sid = store.create_session()
    return store.add_message(sid, "assistant", "结论")


def _make_run(tmp_path: Path, manifest: dict, *, with_chart: bool = True) -> Path:
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    if with_chart:
        (run_dir / "chart.json").write_text(
            json.dumps({"series": [{"type": "line", "data": [1, 2, 3]}]}),
            encoding="utf-8",
        )
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return run_dir


def _base_manifest(**art_extra) -> dict:
    art = {"id": "a1", "kind": "chart", "title": "测试图", "path": "chart.json"}
    art.update(art_extra)
    return {"run_id": "r1", "code_ref": "code.py", "artifacts": [art]}


# --------------------------------------------------------------------------
# 1. 缺失 provenance → 拒收
# --------------------------------------------------------------------------


def test_manifest_without_provenance_is_rejected(store, mid, tmp_path):
    """没有 provenance 的 manifest 必须拒收（ADR-0012 §1：这是唯一的硬约束）。"""
    run_dir = _make_run(tmp_path, _base_manifest())

    with pytest.raises(ManifestError, match="provenance"):
        ingest_run(store, run_dir, mid)


def test_manifest_with_empty_provenance_is_rejected(store, mid, tmp_path):
    """空 provenance 对象也不算数——`{}` 是最容易被当成「填了」的形态。"""
    run_dir = _make_run(tmp_path, _base_manifest(provenance={}))

    with pytest.raises(ManifestError, match="provenance"):
        ingest_run(store, run_dir, mid)


# --------------------------------------------------------------------------
# 2. 盖章权：agent 无权自称 deterministic
# --------------------------------------------------------------------------


def test_agent_claiming_deterministic_is_downgraded_to_agent(store, mid, tmp_path):
    """agent 在 manifest 里写 `kind: "deterministic"` → 服务端改写成 `agent`。

    这是本 ADR 最重要的一条。agent 有能力自己算数字（bash 绕开库函数），
    也能在 manifest 里撒谎。我们不去验证它到底怎么算的，而是**不采信它的声明**：
    只有服务端自己能调 `alpha.registry` 的函数，才有资格盖 deterministic 章。

    后果：agent 手算的数字照样能显示，但带 AI 角标，用户一眼知道它不可信。
    """
    forged = {
        "kind": "deterministic",
        "fn": "alpha.factor.correlation",
        "params": {"symbols": ["600519"]},
        "dataAsOf": "2026-10-21",
    }
    run_dir = _make_run(tmp_path, _base_manifest(provenance=forged))

    aids = ingest_run(store, run_dir, mid)

    art = store.get_artifact(aids[0])
    prov = json.loads(art["provenance"])
    assert prov["kind"] == "agent", (
        f"agent 声称 deterministic 必须被降级为 agent；实际 {prov['kind']!r}\n"
        "若这条变绿了，说明盖章权失守——任何人都能把 AI 手算的数字标成可信"
    )


def test_downgraded_provenance_records_why(store, mid, tmp_path):
    """被降级时要留下痕迹，否则事后无从判断「它本来想自称什么」。

    记的是原始 kind，不是整份伪造内容——目的是审计「有多少 agent 在试图自称可信」，
    而不是保存它编造的参数（那些本来就不可信）。
    """
    forged = {"kind": "deterministic", "fn": "fake.fn", "dataAsOf": "2026-10-21"}
    run_dir = _make_run(tmp_path, _base_manifest(provenance=forged))

    aids = ingest_run(store, run_dir, mid)
    prov = json.loads(store.get_artifact(aids[0])["provenance"])

    assert prov.get("claimedKind") == "deterministic", (
        f"应记录 agent 原本声称的 kind；实际 {prov}"
    )


def test_agent_provenance_keeps_run_id_and_code_hash(store, mid, tmp_path):
    """agent 轨的 provenance 必须带 runId + codeHash（可回看、可重跑）。"""
    prov = {"kind": "agent", "runId": "run-abc", "codeHash": "sha256:deadbeef",
            "dataAsOf": "2026-10-21"}
    run_dir = _make_run(tmp_path, _base_manifest(provenance=prov))

    aids = ingest_run(store, run_dir, mid)
    got = json.loads(store.get_artifact(aids[0])["provenance"])

    assert got["kind"] == "agent"
    assert got["runId"] == "run-abc"
    assert got["codeHash"] == "sha256:deadbeef"


# --------------------------------------------------------------------------
# 3. 服务端铸造 deterministic
# --------------------------------------------------------------------------


def test_server_can_stamp_deterministic(store, mid, tmp_path):
    """服务端自己产出的 artifact 可以是 deterministic。

    这条与上一条的区别只有「谁在调用」：`ingest_run` 多了 `server_stamped=True`
    这个只有业务层能传的参数。agent 交来的 manifest 永远走不到这条路径。
    """
    prov = {"kind": "deterministic", "fn": "alpha.backtest.run",
            "params": {"fast": 20}, "dataAsOf": "2026-10-21"}
    run_dir = _make_run(tmp_path, _base_manifest(provenance=prov))

    aids = ingest_run(store, run_dir, mid, server_stamped=True)

    got = json.loads(store.get_artifact(aids[0])["provenance"])
    assert got["kind"] == "deterministic", (
        f"服务端铸造的 deterministic 不应被降级；实际 {got}"
    )
    assert got["fn"] == "alpha.backtest.run"


def test_deterministic_requires_fn_and_data_as_of(store, mid, tmp_path):
    """deterministic 必须带 fn + dataAsOf，否则不构成「可复现」的声明。"""
    prov = {"kind": "deterministic", "params": {}}  # 缺 fn 与 dataAsOf
    run_dir = _make_run(tmp_path, _base_manifest(provenance=prov))

    with pytest.raises(ManifestError, match="fn"):
        ingest_run(store, run_dir, mid, server_stamped=True)


def test_unknown_kind_is_rejected(store, mid, tmp_path):
    """kind 只能是 deterministic / agent。拼错的 kind 不得静默通过。"""
    run_dir = _make_run(tmp_path, _base_manifest(provenance={"kind": "trustme"}))

    with pytest.raises(ManifestError, match="kind"):
        ingest_run(store, run_dir, mid)


# --------------------------------------------------------------------------
# 4. 落库形态
# --------------------------------------------------------------------------


def test_provenance_is_persisted_as_json_column(store, mid, tmp_path):
    """provenance 落成 artifact 表的独立列（可查询、可 join、可加索引）。"""
    prov = {"kind": "agent", "runId": "r1", "codeHash": "h", "dataAsOf": "2026-10-21"}
    run_dir = _make_run(tmp_path, _base_manifest(provenance=prov))

    aids = ingest_run(store, run_dir, mid)

    rows = store.conn.execute(
        "SELECT provenance FROM artifact WHERE id=?", (aids[0],)
    ).fetchall()
    assert rows, "artifact 未落库"
    assert rows[0]["provenance"], "artifact.provenance 列是空的"
    assert json.loads(rows[0]["provenance"])["kind"] == "agent"


def test_provenance_is_attached_to_the_message(store, mid, tmp_path):
    """前端拿消息时，挂在上面的 artifact 要能读到 provenance（用于显示角标）。"""
    prov = {"kind": "agent", "runId": "r1", "codeHash": "h", "dataAsOf": "2026-10-21"}
    run_dir = _make_run(tmp_path, _base_manifest(provenance=prov))

    ingest_run(store, run_dir, mid)

    arts = store.list_artifacts_for_message(mid)
    assert arts, "消息上没有 artifact"
    assert json.loads(arts[0]["provenance"])["kind"] == "agent", (
        "list_artifacts_for_message 必须带出 provenance，否则前端无法显示 AI 角标"
    )
