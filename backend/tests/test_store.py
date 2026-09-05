"""T26 领域存储 CRUD 单测 —— 五张表建起 + 增查改 + 外键/约束行为。"""

import sqlite3

import pytest

from api.store import Store


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


def test_migrate_creates_five_tables(store):
    rows = store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert {"session", "message", "artifact", "page", "job", "doc"} <= names


def test_session_and_message_roundtrip(store):
    sid = store.create_session(title="白酒相关性")
    assert store.get_session(sid)["title"] == "白酒相关性"

    m1 = store.add_message(sid, "user", "分析白酒板块相关性")
    m2 = store.add_message(sid, "assistant", "")
    store.update_message(m2, "这是结论")

    msgs = store.list_messages(sid)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert [m["seq"] for m in msgs] == [1, 2]
    assert store.get_message(m2)["content"] == "这是结论"
    assert m1 != m2


def test_message_role_check_rejects_bad_role(store):
    sid = store.create_session()
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute(
            "INSERT INTO message (id, session_id, role, content, created_at, seq) "
            "VALUES ('m-x', ?, 'system', '', 0, 1)",
            (sid,),
        )


def test_artifact_attach_and_read(store):
    sid = store.create_session()
    mid = store.add_message(sid, "assistant", "")
    aid = store.add_artifact(
        run_id="r-1",
        kind="chart",
        path="chart.json",
        title="热力图",
        payload={"series": [1, 2, 3]},
        inputs={"symbols": ["600519.SH"], "window": 60},
    )
    # 先不挂消息，再 attach
    assert store.get_artifact(aid)["message_id"] is None
    store.attach_artifact(aid, mid)

    got = store.get_artifact(aid)
    assert got["message_id"] == mid
    assert got["kind"] == "chart"
    assert got["payload"] == {"series": [1, 2, 3]}
    assert got["inputs"]["window"] == 60

    lst = store.list_artifacts_for_message(mid)
    assert len(lst) == 1 and lst[0]["id"] == aid


def test_artifact_kind_check(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute(
            "INSERT INTO artifact (id, run_id, kind, path, created_at) "
            "VALUES ('a-x','r-1','bogus','p',0)"
        )


def test_page_defaults_draft_and_publish(store):
    pid = store.create_page(
        slug="baijiu-corr",
        title="白酒相关性",
        spec={"layout": "grid", "blocks": []},
    )
    p = store.get_page(pid)
    assert p["status"] == "draft"
    assert p["spec"]["layout"] == "grid"

    store.publish_page(pid)
    assert store.get_page(pid)["status"] == "published"


def test_page_slug_unique(store):
    store.create_page(slug="dup", title="A", spec={})
    with pytest.raises(sqlite3.IntegrityError):
        store.create_page(slug="dup", title="B", spec={})


def test_job_lifecycle(store):
    jid = store.create_job(kind="backtest", params={"symbol": "600519"})
    assert store.get_job(jid)["status"] == "queued"
    assert store.get_job(jid)["params"]["symbol"] == "600519"

    store.update_job(jid, status="running")
    assert store.get_job(jid)["status"] == "running"

    store.update_job(jid, status="succeeded", result={"run_id": "r-9"})
    j = store.get_job(jid)
    assert j["status"] == "succeeded"
    assert j["result"]["run_id"] == "r-9"


def test_job_status_check(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute(
            "INSERT INTO job (id, kind, status, created_at, updated_at) "
            "VALUES ('j-x','backtest','bogus',0,0)"
        )


def test_doc_roundtrip(store):
    did = store.add_doc(title="2023 年报", source_path="/docs/a.pdf", text="营收增长")
    assert store.get_doc(did)["title"] == "2023 年报"
    assert len(store.list_docs()) == 1


def test_foreign_key_cascade_message(store):
    sid = store.create_session()
    store.add_message(sid, "user", "hi")
    store.conn.execute("DELETE FROM session WHERE id=?", (sid,))
    store.conn.commit()
    assert store.list_messages(sid) == []


def test_page_kind_migration_idempotent_on_legacy_db():
    """老库（page 表无 kind 列）迁移应补列且旧行默认 'user'；跑两次不报错（幂等）。"""
    from api.store import _migrate_page_kind

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # 模拟 T26 老 schema：page 表没有 kind 列。
    conn.execute(
        "CREATE TABLE page ("
        " id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL,"
        " status TEXT NOT NULL DEFAULT 'draft', spec TEXT NOT NULL,"
        " created_at REAL NOT NULL, updated_at REAL NOT NULL)"
    )
    conn.execute(
        "INSERT INTO page (id, slug, title, status, spec, created_at, updated_at) "
        "VALUES ('p-old','legacy','旧页','draft','{}',0,0)"
    )
    conn.commit()

    # 迁移两次：均不报错（幂等）。
    _migrate_page_kind(conn)
    _migrate_page_kind(conn)

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(page)").fetchall()}
    assert "kind" in cols
    row = conn.execute("SELECT kind FROM page WHERE id='p-old'").fetchone()
    assert row["kind"] == "user"  # 旧行默认 user
    conn.close()
