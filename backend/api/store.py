"""领域存储 —— 产品真源（SQLite）。

架构边界（ADR-0006）：业务层是唯一持有产品数据库的角色。前端不读 dsh JSONL；
agent 不直接写库（只写 workspace + 调副作用 MCP 工具，业务层校验后落库）。

聚合拆分（ADR-0007，DDD 务实子集）：按聚合把仓储拆成四个类，共享同一 sqlite 连接：
  SessionRepo —— session / message / artifact（同属会话聚合，artifact 挂在 message 上）
  PageRepo    —— page（展示页 spec；create 走 validate_spec 白名单校验）
  JobRepo     —— job（长任务）
  DocRepo     —— doc（文档库）
`Store` 保留为聚合面候（facade），方法委派到各 repo，向后兼容既有调用方与测试。

五张表：
  session   —— 一条对话（前端意义上的会话；映射见 T27，dsh session_id 每次进程运行新分配）
  message   —— 对话里的一条消息（user / assistant）
  artifact  —— agent 产出物（chart / table / markdown / metric / image）
  page      —— 展示页 spec（kind builtin/user；status draft/published）
  job       —— 长任务（回测等，T38+）
  doc       —— 文档库条目（年报/研报，T45+）

repository 层是薄封装：建表 + CRUD + 简单查询。零业务逻辑（校验在 api 层 / page_spec）。
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
    kind        TEXT NOT NULL DEFAULT 'user' CHECK (kind IN ('builtin','user')),
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published')),
    spec        TEXT NOT NULL,     -- 完整 page spec JSON（含 params/blocks/analysis_ref）
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

CREATE TABLE IF NOT EXISTS stock_pool (
    id          TEXT PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS journal (
    id          TEXT PRIMARY KEY,
    code        TEXT NOT NULL DEFAULT '',
    name        TEXT NOT NULL DEFAULT '',
    side        TEXT NOT NULL CHECK (side IN ('buy','sell')),
    price       REAL NOT NULL,
    shares      INTEGER NOT NULL,
    fee         REAL NOT NULL DEFAULT 0,
    traded_at   TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_journal_traded ON journal(traded_at);

CREATE TABLE IF NOT EXISTS portfolio (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    benchmark   TEXT NOT NULL DEFAULT '000300',
    created_at  REAL NOT NULL,
    created_on  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS rebalance_event (
    id           TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL REFERENCES portfolio(id) ON DELETE CASCADE,
    effective_on TEXT NOT NULL,
    weights      TEXT NOT NULL,
    created_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rebalance_portfolio ON rebalance_event(portfolio_id, effective_on);
"""


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _migrate_page_kind(conn: sqlite3.Connection) -> None:
    """幂等迁移：老库 page 表缺 kind 列时补列，旧行默认 'user'。

    通过 PRAGMA table_info 探测列是否已存在——存在则不动，故迁移两次亦不报错。
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(page)").fetchall()}
    if "kind" not in cols:
        conn.execute(
            "ALTER TABLE page ADD COLUMN kind TEXT NOT NULL DEFAULT 'user'"
        )


class SessionRepo:
    """会话聚合：session / message / artifact（artifact 挂在 message 上）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

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


class PageRepo:
    """展示页聚合：page。create/upsert 落库前经 page_spec.validate_spec 白名单校验。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _row_to_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        d = dict(row)
        d["spec"] = json.loads(d["spec"])
        return d

    # 旧签名（T26）：显式 slug/title/spec，不做白名单校验，status 恒 draft。
    # 保留向后兼容 test_store.py 与既有调用方。
    def create_page(self, slug: str, title: str, spec: dict[str, Any]) -> str:
        pid = _new_id("p")
        now = time.time()
        self.conn.execute(
            "INSERT INTO page (id, slug, title, kind, status, spec, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (pid, slug, title, "user", "draft",
             json.dumps(spec, ensure_ascii=False), now, now),
        )
        self.conn.commit()
        return pid

    # 新签名（T45）：完整 spec dict 自带 slug/title/kind；落库前 validate_spec。
    def create_page_from_spec(self, spec: dict[str, Any], kind: str = "user") -> str:
        from api.page_spec import validate_spec

        spec = validate_spec(spec)
        pid = _new_id("p")
        now = time.time()
        status = "published" if kind == "builtin" else "draft"
        self.conn.execute(
            "INSERT INTO page (id, slug, title, kind, status, spec, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (pid, spec["slug"], spec["title"], kind, status,
             json.dumps(spec, ensure_ascii=False), now, now),
        )
        self.conn.commit()
        return pid

    def upsert_builtin_page(self, spec: dict[str, Any]) -> str:
        """内置页（Wave3 固定 spec）：按 slug upsert，kind=builtin、status=published。"""
        from api.page_spec import validate_spec

        spec = validate_spec(spec)
        now = time.time()
        existing = self.conn.execute(
            "SELECT id FROM page WHERE slug=?", (spec["slug"],)
        ).fetchone()
        spec_json = json.dumps(spec, ensure_ascii=False)
        if existing:
            self.conn.execute(
                "UPDATE page SET title=?, kind='builtin', status='published', "
                "spec=?, updated_at=? WHERE slug=?",
                (spec["title"], spec_json, now, spec["slug"]),
            )
            self.conn.commit()
            return existing["id"]
        pid = _new_id("p")
        self.conn.execute(
            "INSERT INTO page (id, slug, title, kind, status, spec, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (pid, spec["slug"], spec["title"], "builtin", "published",
             spec_json, now, now),
        )
        self.conn.commit()
        return pid

    def get_page(self, pid: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM page WHERE id=?", (pid,)).fetchone()
        return self._row_to_dict(row)

    def get_page_by_slug(self, slug: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM page WHERE slug=?", (slug,)).fetchone()
        return self._row_to_dict(row)

    def list_pages(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, slug, title, kind, status, created_at, updated_at FROM page "
            "ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def publish_page(self, pid: str) -> None:
        self.conn.execute(
            "UPDATE page SET status='published', updated_at=? WHERE id=?",
            (time.time(), pid),
        )
        self.conn.commit()


class JobRepo:
    """长任务聚合：job。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

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


class DocRepo:
    """文档库聚合：doc。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

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

    def delete_doc(self, did: str) -> bool:
        cur = self.conn.execute("DELETE FROM doc WHERE id=?", (did,))
        self.conn.commit()
        return cur.rowcount > 0


class StockPoolRepo:
    """股票池聚合：stock_pool（研究池——代码/名称/备注/标签）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, code: str, name: str = "", note: str = "", tags: str = "") -> str:
        """加入股票池。code 唯一——重复 code 按 upsert 更新 name/note/tags。"""
        existing = self.conn.execute(
            "SELECT id FROM stock_pool WHERE code=?", (code,)
        ).fetchone()
        if existing:
            self.conn.execute(
                "UPDATE stock_pool SET name=?, note=?, tags=? WHERE code=?",
                (name, note, tags, code),
            )
            self.conn.commit()
            return existing["id"]
        pid = _new_id("sp")
        self.conn.execute(
            "INSERT INTO stock_pool (id, code, name, note, tags, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (pid, code, name, note, tags, time.time()),
        )
        self.conn.commit()
        return pid

    def remove(self, code: str) -> bool:
        cur = self.conn.execute("DELETE FROM stock_pool WHERE code=?", (code,))
        self.conn.commit()
        return cur.rowcount > 0

    def list(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM stock_pool ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


class JournalRepo:
    """交易日志聚合：journal（真实成交记录 + 复盘备注）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(
        self, *, code: str, name: str, side: str, price: float, shares: int,
        fee: float = 0.0, traded_at: str = "", note: str = "",
    ) -> str:
        if side not in ("buy", "sell"):
            raise ValueError(f"side 必须是 buy/sell，得到 {side!r}")
        jid = _new_id("jn")
        self.conn.execute(
            "INSERT INTO journal "
            "(id, code, name, side, price, shares, fee, traded_at, note, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (jid, code, name, side, float(price), int(shares), float(fee),
             traded_at, note, time.time()),
        )
        self.conn.commit()
        return jid

    def remove(self, jid: str) -> bool:
        cur = self.conn.execute("DELETE FROM journal WHERE id=?", (jid,))
        self.conn.commit()
        return cur.rowcount > 0

    def list(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM journal ORDER BY traded_at DESC, created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


class PortfolioRepo:
    """模拟组合聚合：portfolio + rebalance_event（雪球式调仓事件，权重历史不可覆盖）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, name: str, benchmark: str = "000300", created_on: str = "") -> str:
        pid = _new_id("pf")
        self.conn.execute(
            "INSERT INTO portfolio (id, name, benchmark, created_at, created_on) "
            "VALUES (?,?,?,?,?)",
            (pid, name, benchmark, time.time(), created_on),
        )
        self.conn.commit()
        return pid

    def get(self, pid: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM portfolio WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM portfolio ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, pid: str) -> bool:
        cur = self.conn.execute("DELETE FROM portfolio WHERE id=?", (pid,))
        self.conn.commit()
        return cur.rowcount > 0

    def add_rebalance(self, portfolio_id: str, effective_on: str, weights: dict[str, float]) -> str:
        """新增一次调仓事件（生效日期 + {code: weight}）。历史事件保留不覆盖。"""
        rid = _new_id("rb")
        self.conn.execute(
            "INSERT INTO rebalance_event (id, portfolio_id, effective_on, weights, created_at) "
            "VALUES (?,?,?,?,?)",
            (rid, portfolio_id, effective_on,
             json.dumps(weights, ensure_ascii=False), time.time()),
        )
        self.conn.commit()
        return rid

    def list_rebalances(self, portfolio_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM rebalance_event WHERE portfolio_id=? ORDER BY effective_on",
            (portfolio_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["weights"] = json.loads(d["weights"])
            out.append(d)
        return out


class Store:
    """SQLite 仓储聚合面候（facade）。持有连接与四个 repo，方法委派保持向后兼容。

    同一连接串行使用；FastAPI 层每请求可用 with 上下文。
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._path = str(db_path)
        self.conn = sqlite3.connect(self._path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.migrate()
        # 各聚合 repo 共享同一连接。
        self.sessions = SessionRepo(self.conn)
        self.pages = PageRepo(self.conn)
        self.jobs = JobRepo(self.conn)
        self.docs = DocRepo(self.conn)
        self.stock_pool = StockPoolRepo(self.conn)
        self.journal = JournalRepo(self.conn)
        self.portfolio = PortfolioRepo(self.conn)

    def migrate(self) -> None:
        """建表 + 增量迁移（幂等）。这是唯一的迁移入口。"""
        self.conn.executescript(SCHEMA)
        _migrate_page_kind(self.conn)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------- session（委派 SessionRepo）----------
    def create_session(self, title: str = "") -> str:
        return self.sessions.create_session(title)

    def get_session(self, sid: str) -> dict[str, Any] | None:
        return self.sessions.get_session(sid)

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.sessions.list_sessions()

    # ---------- message ----------
    def add_message(self, session_id: str, role: str, content: str = "") -> str:
        return self.sessions.add_message(session_id, role, content)

    def update_message(self, mid: str, content: str) -> None:
        self.sessions.update_message(mid, content)

    def get_message(self, mid: str) -> dict[str, Any] | None:
        return self.sessions.get_message(mid)

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        return self.sessions.list_messages(session_id)

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
        return self.sessions.add_artifact(
            run_id, kind, path,
            message_id=message_id, title=title, payload=payload, inputs=inputs,
        )

    def get_artifact(self, aid: str) -> dict[str, Any] | None:
        return self.sessions.get_artifact(aid)

    def list_artifacts_for_message(self, message_id: str) -> list[dict[str, Any]]:
        return self.sessions.list_artifacts_for_message(message_id)

    def attach_artifact(self, aid: str, message_id: str) -> None:
        self.sessions.attach_artifact(aid, message_id)

    # ---------- page（委派 PageRepo）----------
    def create_page(self, slug: str, title: str, spec: dict[str, Any]) -> str:
        return self.pages.create_page(slug, title, spec)

    def get_page(self, pid: str) -> dict[str, Any] | None:
        return self.pages.get_page(pid)

    def list_pages(self) -> list[dict[str, Any]]:
        return self.pages.list_pages()

    def publish_page(self, pid: str) -> None:
        self.pages.publish_page(pid)

    # ---------- job（委派 JobRepo）----------
    def create_job(
        self, kind: str, params: Any = None, session_id: str | None = None
    ) -> str:
        return self.jobs.create_job(kind, params, session_id)

    def update_job(
        self,
        jid: str,
        *,
        status: str | None = None,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        self.jobs.update_job(jid, status=status, result=result, error=error)

    def get_job(self, jid: str) -> dict[str, Any] | None:
        return self.jobs.get_job(jid)

    # ---------- doc（委派 DocRepo）----------
    def add_doc(self, title: str, source_path: str, text: str = "") -> str:
        return self.docs.add_doc(title, source_path, text)

    def get_doc(self, did: str) -> dict[str, Any] | None:
        return self.docs.get_doc(did)

    def list_docs(self) -> list[dict[str, Any]]:
        return self.docs.list_docs()
