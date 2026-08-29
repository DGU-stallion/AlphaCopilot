"""领域存储 —— 产品真源（SQLite）。

架构边界（ADR-0006）：业务层是唯一持有产品数据库的角色。前端不读 dsh JSONL；
agent 不直接写库（只写 workspace + 调副作用 MCP 工具，业务层校验后落库）。

五张表：
  session   —— 一条对话（前端意义上的会话；映射见 T27，dsh session_id 每次进程运行新分配）
  message   —— 对话里的一条消息（user / assistant）
  artifact  —— agent 产出物（chart / table / markdown / metric / image）
  page      —— 展示页 spec（status 恒 draft，发布需人工，T41+）
  job       —— 长任务（回测等，T38+）
  doc       —— 文档库条目（年报/研报，T45+）

repository 层是薄封装：建表 + CRUD + 简单查询。零业务逻辑（校验在 api 层）。
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS session (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS message (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    seq         INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_message_session ON message(session_id, seq);

CREATE TABLE IF NOT EXISTS artifact (
    id          TEXT PRIMARY KEY,
    message_id  TEXT REFERENCES message(id) ON DELETE CASCADE,
    run_id      TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('chart','table','markdown','metric','image')),
    title       TEXT NOT NULL DEFAULT '',
    path        TEXT NOT NULL,
    payload     TEXT,              -- 内联 JSON（chart option / metric 等），可空
    inputs      TEXT,              -- 可重跑参数 JSON
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifact_message ON artifact(message_id);

CREATE TABLE IF NOT EXISTS page (
    id          TEXT PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published')),
    spec        TEXT NOT NULL,     -- 完整 page spec JSON
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS job (
    id          TEXT PRIMARY KEY,
    session_id  TEXT REFERENCES session(id) ON DELETE SET NULL,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','running','succeeded','failed')),
    params      TEXT,              -- 提交参数 JSON
    result      TEXT,              -- 完成后 run_id / 结果 JSON
    error       TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS doc (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    source_path TEXT NOT NULL,
    text        TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);
"""


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Store:
    """SQLite 仓储层。同一连接串行使用；FastAPI 层每请求可用 with 上下文。"""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._path = str(db_path)
        self.conn = sqlite3.connect(self._path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    def migrate(self) -> None:
        """建表（幂等）。这是唯一的迁移入口。"""
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------- session ----------
    def create_session(self, title: str = "") -> str:
        sid = _new_id("s")
        self.conn.execute(
            "INSERT INTO session (id, title, created_at) VALUES (?,?,?)",
            (sid, title, time.time()),
        )
        self.conn.commit()
        return sid

    def get_session(self, sid: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM session WHERE id=?", (sid,)).fetchone()
        return dict(row) if row else None

    def list_sessions(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM session ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- message ----------
    def add_message(self, session_id: str, role: str, content: str = "") -> str:
        mid = _new_id("m")
        seq_row = self.conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM message WHERE session_id=?",
            (session_id,),
        ).fetchone()
        seq = seq_row["n"]
        self.conn.execute(
            "INSERT INTO message (id, session_id, role, content, created_at, seq) "
            "VALUES (?,?,?,?,?,?)",
            (mid, session_id, role, content, time.time(), seq),
        )
        self.conn.commit()
        return mid

    def update_message(self, mid: str, content: str) -> None:
        self.conn.execute("UPDATE message SET content=? WHERE id=?", (content, mid))
        self.conn.commit()

    def get_message(self, mid: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM message WHERE id=?", (mid,)).fetchone()
        return dict(row) if row else None

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM message WHERE session_id=? ORDER BY seq", (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- artifact ----------
    def add_artifact(
        self,
        run_id: str,
        kind: str,
        path: str,
        *,
        message_id: str | None = None,
        title: str = "",
        payload: Any = None,
        inputs: Any = None,
    ) -> str:
        aid = _new_id("a")
        self.conn.execute(
            "INSERT INTO artifact "
            "(id, message_id, run_id, kind, title, path, payload, inputs, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                aid,
                message_id,
                run_id,
                kind,
                title,
                path,
                json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                json.dumps(inputs, ensure_ascii=False) if inputs is not None else None,
                time.time(),
            ),
        )
        self.conn.commit()
        return aid

    def get_artifact(self, aid: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM artifact WHERE id=?", (aid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["payload"] = json.loads(d["payload"]) if d["payload"] else None
        d["inputs"] = json.loads(d["inputs"]) if d["inputs"] else None
        return d

    def list_artifacts_for_message(self, message_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM artifact WHERE message_id=? ORDER BY created_at",
            (message_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload"]) if d["payload"] else None
            d["inputs"] = json.loads(d["inputs"]) if d["inputs"] else None
            out.append(d)
        return out

    def attach_artifact(self, aid: str, message_id: str) -> None:
        self.conn.execute(
            "UPDATE artifact SET message_id=? WHERE id=?", (message_id, aid)
        )
        self.conn.commit()

    # ---------- page ----------
    def create_page(self, slug: str, title: str, spec: dict[str, Any]) -> str:
        pid = _new_id("p")
        now = time.time()
        self.conn.execute(
            "INSERT INTO page (id, slug, title, status, spec, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (pid, slug, title, "draft", json.dumps(spec, ensure_ascii=False), now, now),
        )
        self.conn.commit()
        return pid

    def get_page(self, pid: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM page WHERE id=?", (pid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["spec"] = json.loads(d["spec"])
        return d

    def list_pages(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, slug, title, status, created_at, updated_at FROM page "
            "ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def publish_page(self, pid: str) -> None:
        self.conn.execute(
            "UPDATE page SET status='published', updated_at=? WHERE id=?",
            (time.time(), pid),
        )
        self.conn.commit()

    # ---------- job ----------
    def create_job(
        self, kind: str, params: Any = None, session_id: str | None = None
    ) -> str:
        jid = _new_id("j")
        now = time.time()
        self.conn.execute(
            "INSERT INTO job (id, session_id, kind, status, params, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                jid,
                session_id,
                kind,
                "queued",
                json.dumps(params, ensure_ascii=False) if params is not None else None,
                now,
                now,
            ),
        )
        self.conn.commit()
        return jid

    def update_job(
        self,
        jid: str,
        *,
        status: str | None = None,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        sets = ["updated_at=?"]
        vals: list[Any] = [time.time()]
        if status is not None:
            sets.append("status=?")
            vals.append(status)
        if result is not None:
            sets.append("result=?")
            vals.append(json.dumps(result, ensure_ascii=False))
        if error is not None:
            sets.append("error=?")
            vals.append(error)
        vals.append(jid)
        self.conn.execute(f"UPDATE job SET {', '.join(sets)} WHERE id=?", vals)
        self.conn.commit()

    def get_job(self, jid: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM job WHERE id=?", (jid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["params"] = json.loads(d["params"]) if d["params"] else None
        d["result"] = json.loads(d["result"]) if d["result"] else None
        return d

    # ---------- doc ----------
    def add_doc(self, title: str, source_path: str, text: str = "") -> str:
        did = _new_id("d")
        self.conn.execute(
            "INSERT INTO doc (id, title, source_path, text, created_at) VALUES (?,?,?,?,?)",
            (did, title, source_path, text, time.time()),
        )
        self.conn.commit()
        return did

    def get_doc(self, did: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM doc WHERE id=?", (did,)).fetchone()
        return dict(row) if row else None

    def list_docs(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, title, source_path, created_at FROM doc ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
