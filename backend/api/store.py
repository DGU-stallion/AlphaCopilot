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
  session   —— 一条对话（前端意义上的会话；映射见 T27，运行时 session_id 每次进程运行新分配）
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
    -- 运行时会话 id（Pi 的 sessionId）。跨进程续接的抓手：
    -- 首次启动由 PiProvider 从 get_state 取回后写这里；之后每次启动读出来
    -- 填回 ProviderSpec.session_id，agent 才不会「界面有历史、自己却失忆」。
    runtime_session_id TEXT,
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
    -- provenance：这个数字凭什么是可信的（ADR-0012 §1，唯一硬约束）。
    -- JSON：{kind:"deterministic"|"agent", ...}。deterministic **只能由服务端铸造**
    -- （ADR-0012「已决 1」）；agent 交来的声明一律降级为 agent 并记 claimedKind。
    provenance  TEXT,
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

-- M3-1 Run registry：一次确定性计算的**全部可复现要素**。
-- 为什么不是「只留 runs/ 目录」：对比两个 Run 要查指标、按 dataAsOf 过滤、
-- 按 codeHash 判断「是不是同一份策略代码」——这些都要可查询，扫目录做不到。
CREATE TABLE IF NOT EXISTS run (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,                 -- backtest / factor / correlation ...
    params       TEXT NOT NULL DEFAULT '{}',    -- 输入参数 JSON
    -- 产出这份结果的代码指纹。同一个策略改一个字就该是新 Run，
    -- 否则「可复现」是空话（你不知道当时跑的是哪版代码）。
    code_hash    TEXT NOT NULL DEFAULT '',
    -- 数据截止时点。早上的数字与下午的数字必须能区分（ADR-0012）。
    data_as_of   TEXT NOT NULL DEFAULT '',
    metrics      TEXT NOT NULL DEFAULT '{}',    -- 指标 JSON（结构化，前端直接读）
    artifact_ids TEXT NOT NULL DEFAULT '[]',    -- 产出的 artifact id 列表 JSON
    -- 足以**重跑**的完整输入快照（含 closes 这类调用方给的数据）。
    -- params 只是「实验设计」（fast/slow/symbol），inputs 才是「原料」。
    -- 少了它只能说「可比较」，不能说「可重跑」（M3-4）。
    inputs       TEXT NOT NULL DEFAULT '{}',
    -- 研究线（M5-3）：这次计算是为了验证哪条判断。
    -- 空串 = 随手跑的，不属于任何研究线（不强制 —— 强制会让人干脆不写笔记）。
    note_id      TEXT NOT NULL DEFAULT '',
    created_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_created ON run(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_kind_asof ON run(kind, data_as_of);

-- M3-3 View：保存的「看什么」。页面 = View 的集合（ADR-0012）。
CREATE TABLE IF NOT EXISTS view (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,                  -- correlation / backtest / factor ...
    params      TEXT NOT NULL DEFAULT '{}',
    pinned      INTEGER NOT NULL DEFAULT 0,     -- 0/1：Pin = 「我天天要看这个」
    last_run_id TEXT,                           -- 上次用这个 View 跑出的 Run（重跑/对比用）
    note_id     TEXT NOT NULL DEFAULT '',       -- 研究线归属（M5-3）
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_view_pinned ON view(pinned, updated_at DESC);

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


def _migrate_run_inputs(conn: sqlite3.Connection) -> None:
    """幂等迁移：老库 run 表缺 inputs 列时补列（默认 '{}'，老 Run 无法重跑但可读）。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(run)").fetchall()}
    if cols and "inputs" not in cols:
        conn.execute("ALTER TABLE run ADD COLUMN inputs TEXT NOT NULL DEFAULT '{}'")


def _migrate_note_links(conn: sqlite3.Connection) -> None:
    """幂等迁移：run / view 补 note_id 列（研究线，M5-3）。"""
    for table in ("run", "view"):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if cols and "note_id" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN note_id TEXT NOT NULL DEFAULT ''")


def _migrate_page_soft_delete(conn: sqlite3.Connection) -> None:
    """幂等迁移：page 补软删除列（ROUND2 §9）。

    `deleted_at` 非空 = 已软删（不出现在列表/查询里，但数据还在）；
    `former_slug` 存删除前的原 slug —— 删除时把 `slug` 改成墓标值以释放
    UNIQUE 约束（否则「删了想改一下再建同名页」会撞 UNIQUE）。
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(page)").fetchall()}
    if cols and "deleted_at" not in cols:
        conn.execute("ALTER TABLE page ADD COLUMN deleted_at REAL")
    if cols and "former_slug" not in cols:
        conn.execute("ALTER TABLE page ADD COLUMN former_slug TEXT")


def _migrate_soft_delete_and_meta(conn: sqlite3.Connection) -> None:
    """幂等迁移：run / doc 补软删除 + 备注/归档列（ROUND2 §13）。

    **为什么 run 也要软删**：Run 是「这次计算的留档」，删了就没法证明当时跑的是
    哪一版代码/哪一份数据。硬删等于毁掉可复现性的证据链。所以：
      - `deleted_at` 非空 = 已软删（列表里不出现，但 `get()` 仍能取到，可撤销）
      - `note` 是用户自己写的备注（「这一版是想验证什么」），与 `note_id`
        不同：`note_id` 指向研究线 doc，`note` 是一行随手写的说明

    doc（研报归档）需要 `kind`/`tags`/`file_path`/`bytes`/`mime`/`deleted_at`：
    之前只有 title/source_path/text，无法承载「上传一个 PDF 文件」这件事。
    """
    for table, cols in (
        ("run", {
            "deleted_at": "REAL",
            "note": "TEXT NOT NULL DEFAULT ''",
        }),
        ("doc", {
            "deleted_at": "REAL",
            "kind": "TEXT NOT NULL DEFAULT 'note'",   # note / pdf / markdown / image
            "tags": "TEXT NOT NULL DEFAULT ''",
            "file_path": "TEXT NOT NULL DEFAULT ''",   # 相对 workspace/reports/ 的文件名
            "bytes": "INTEGER NOT NULL DEFAULT 0",
            "mime": "TEXT NOT NULL DEFAULT ''",
        }),
    ):
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if not have:
            continue
        for name, decl in cols.items():
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def _migrate_setting_table(conn: sqlite3.Connection) -> None:
    """幂等迁移：建 setting 表（k/v）。

    为什么不用环境变量：`ALPHACOPILOT_MODEL` 只在进程启动时读一次，改它要重启
    后端。而「换个模型试试」是高频操作 —— 前端改完就生效才叫能改。
    也不用写 JSON 文件：已经有一个 SQLite 了，再引入第二种持久化形态，
    备份/迁移就会漏掉一份。
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS setting ("
        "  key TEXT PRIMARY KEY,"
        "  value TEXT NOT NULL DEFAULT '',"
        "  updated_at REAL NOT NULL"
        ")"
    )


def _migrate_page_kind(conn: sqlite3.Connection) -> None:
    """幂等迁移：老库 page 表缺 kind 列时补列，旧行默认 'user'。

    通过 PRAGMA table_info 探测列是否已存在——存在则不动，故迁移两次亦不报错。
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(page)").fetchall()}
    if "kind" not in cols:
        conn.execute(
            "ALTER TABLE page ADD COLUMN kind TEXT NOT NULL DEFAULT 'user'"
        )


def _migrate_session_runtime_id(conn: sqlite3.Connection) -> None:
    """幂等迁移：老库 session 表缺 runtime_session_id 列时补列。

    旧行留 NULL —— 表示「这条会话是续接功能上线前建的，不知道它的运行时 id」。
    下次启动会重新生成一个新 id 填进去（相当于从那一刻开始可以续接了）。
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(session)").fetchall()}
    if "runtime_session_id" not in cols:
        conn.execute("ALTER TABLE session ADD COLUMN runtime_session_id TEXT")


def _migrate_artifact_provenance(conn: sqlite3.Connection) -> None:
    """幂等迁移：老库 artifact 表缺 provenance 列时补列。

    旧行留 NULL 而不是编一个默认值 —— 「这个 artifact 没有 provenance」是历史事实，
    伪造一个 `{"kind":"agent"}` 会让它看起来像是走过了盖章流程。
    读的时候按 NULL 处理成「未声明」，前端不显示角标。
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(artifact)").fetchall()}
    if "provenance" not in cols:
        conn.execute("ALTER TABLE artifact ADD COLUMN provenance TEXT")


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

    def set_runtime_session_id(self, sid: str, runtime_session_id: str | None) -> None:
        """记录该会话在运行时里的 id（用于跨进程续接）。幂等，可覆盖。"""
        self.conn.execute(
            "UPDATE session SET runtime_session_id=? WHERE id=?", (runtime_session_id, sid)
        )
        self.conn.commit()

    def get_session(self, sid: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM session WHERE id=?", (sid,)).fetchone()
        return dict(row) if row else None

    def list_sessions(self) -> list[dict[str, Any]]:
        """会话列表 + 消息条数。

        带上 `message_count` 是为了让前端会话列表能区分「聊了 30 轮的」和
        「误点开一次空着的」—— 只有标题和时间的列表几乎没法挑。
        """
        rows = self.conn.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM message m WHERE m.session_id = s.id) "
            "AS message_count FROM session s ORDER BY s.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, sid: str) -> bool:
        """删会话连同它的消息。

        ⚠️ 这里是**硬删**，与 Run 的软删不同，理由是：会话是 agent 的内部记忆
        （硬规则 2 明确说它「不是产品真源」），产出的 artifact 早已独立落库。
        删掉一个会话不会让任何已经展示过的数字失去证据。
        """
        cur = self.conn.execute("DELETE FROM session WHERE id=?", (sid,))
        self.conn.commit()
        return cur.rowcount > 0

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
        provenance: Any = None,
    ) -> str:
        aid = _new_id("a")
        self.conn.execute(
            "INSERT INTO artifact "
            "(id, message_id, run_id, kind, title, path, payload, inputs, provenance, "
            " created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                aid,
                message_id,
                run_id,
                kind,
                title,
                path,
                json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                json.dumps(inputs, ensure_ascii=False) if inputs is not None else None,
                json.dumps(provenance, ensure_ascii=False) if provenance is not None else None,
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
        # slug 冲突必须在落库前检查并给出清晰原因：slug 是 URL 的一部分，
        # 重复会让「打开哪个页面」变得不确定。依赖 UNIQUE 约束报错的话，
        # 上层拿到的是 sqlite3.IntegrityError，看不出是 slug 的事。
        existing = self.conn.execute(
            "SELECT id FROM page WHERE slug=?", (spec["slug"],)
        ).fetchone()
        if existing is not None:
            raise ValueError(f"slug 已被占用：{spec['slug']!r}（page {existing[0]}）")
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
        # 已软删的页对「读」不可见 —— 但对 restore 需要看得到，那个走 find_any。
        row = self.conn.execute(
            "SELECT * FROM page WHERE id=? AND deleted_at IS NULL", (pid,)
        ).fetchone()
        return self._row_to_dict(row)

    def find_any(self, pid: str) -> dict[str, Any] | None:
        """含已软删的行。只给 restore / 诊断用，**不要**拿它做页面查询。"""
        row = self.conn.execute("SELECT * FROM page WHERE id=?", (pid,)).fetchone()
        return self._row_to_dict(row)

    def get_page_by_slug(self, slug: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM page WHERE slug=? AND deleted_at IS NULL", (slug,)
        ).fetchone()
        return self._row_to_dict(row)

    def list_pages(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, slug, title, kind, status, created_at, updated_at FROM page "
            "WHERE deleted_at IS NULL ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def publish_page(self, pid: str) -> None:
        self.conn.execute(
            "UPDATE page SET status='published', updated_at=? WHERE id=?",
            (time.time(), pid),
        )
        self.conn.commit()

    def delete_page(self, pid: str) -> bool:
        """**软删**一个页面。返回 False 表示不存在（或已删）。

        为什么放在 repo 而不在 api 层写 SQL：所有 page 的写操作都应该走同一个
        地方，否则「哪些字段能改」会散到多个文件（ADR-0016 之后页面的建/删会
        被 agent 频繁调用，不能让它变成散装 SQL）。

        **内置页拒删的判断不在这里**，而在 api 层（那里才知道「内置」意味着
        会被 `register_builtin_pages` 重新 upsert 的事实）。repo 只管删除。

        为什么是软删（ROUND2 §9 事故）：这条链路原本是硬 DELETE，且前端没有
        确认框。当时的理由是「页面内容是 spec，可再生」——**这个判断是错的**，
        用户手写的页面不是可再生资源，实际造成了一个自定义页被删后无法恢复。

        释放 slug 的做法：删除时把 `slug` 改成墓标值 `原slug#deleted#id`，
        原值存进 `former_slug`。这样 UNIQUE 约束不会挡住「删了再建同名页」，
        恢复时又能查出原来的 slug 是否已被占用。
        """
        cur = self.conn.execute(
            "UPDATE page SET deleted_at=?, former_slug=slug, "
            "slug = slug || '#deleted#' || id, updated_at=? "
            "WHERE id=? AND deleted_at IS NULL",
            (time.time(), time.time(), pid),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def restore_page(self, pid: str) -> tuple[bool, str]:
        """恢复软删的页。返回 (成功, 原因)。

        失败的唯一情况：删除后有人又建了同名 slug —— 那时不能恢复，
        因为 slug 是 URL 的一部分，两个页抢一个 slug 会让「打开哪个」不确定。
        """
        row = self.find_any(pid)
        if row is None:
            return False, "not found"
        if row.get("deleted_at") is None:
            return True, "already active"      # 幂等：没删过也算成功
        target = row.get("former_slug") or row["slug"]
        taken = self.conn.execute(
            "SELECT id FROM page WHERE slug=? AND deleted_at IS NULL", (target,)
        ).fetchone()
        if taken is not None:
            return False, f"slug 已被占用：{target!r}"
        self.conn.execute(
            "UPDATE page SET slug=?, former_slug=NULL, deleted_at=NULL, updated_at=? "
            "WHERE id=?",
            (target, time.time(), pid),
        )
        self.conn.commit()
        return True, "restored"

    # 注：M5-2 的 `set_status`（draft ↔ published）已随 Build 模式删除
    # （ROUND2-B1）。发布语义仍保留在 `publish_page`（内置页注册用）。


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


class RunRepo:
    """Run registry（M3-1）：一次确定性计算的完整可复现要素。

    ADR-0012：每个 artifact 带 provenance；Run 是 provenance 的**上位概念** ——
    一次计算产多个 artifact，它们共享同一组 params / codeHash / dataAsOf。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(
        self,
        *,
        kind: str,
        params: dict[str, Any] | None = None,
        code_hash: str = "",
        data_as_of: str = "",
        metrics: dict[str, Any] | None = None,
        artifact_ids: list[str] | None = None,
        inputs: dict[str, Any] | None = None,
        note_id: str = "",
    ) -> str:
        rid = _new_id("run")
        self.conn.execute(
            "INSERT INTO run "
            "(id, kind, params, code_hash, data_as_of, metrics, artifact_ids, inputs, "
            "note_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                rid, kind,
                json.dumps(params or {}, ensure_ascii=False),
                code_hash, data_as_of,
                json.dumps(metrics or {}, ensure_ascii=False),
                json.dumps(artifact_ids or [], ensure_ascii=False),
                json.dumps(inputs or {}, ensure_ascii=False),
                note_id,
                time.time(),
            ),
        )
        self.conn.commit()
        return rid

    def _row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        d = dict(row)
        d["params"] = json.loads(d.get("params") or "{}")
        d["metrics"] = json.loads(d.get("metrics") or "{}")
        d["artifact_ids"] = json.loads(d.get("artifact_ids") or "[]")
        d["inputs"] = json.loads(d.get("inputs") or "{}")
        return d

    def get(self, rid: str) -> dict[str, Any] | None:
        return self._row(self.conn.execute("SELECT * FROM run WHERE id = ?", (rid,)).fetchone())

    def list_recent(
        self, *, kind: str | None = None, data_as_of: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """按时间倒序。kind / data_as_of 可过滤 —— 「只看今天数据算出来的」是常见诉求。"""
        sql = "SELECT * FROM run"
        where: list[str] = []
        args: list[Any] = []
        if kind:
            where.append("kind = ?")
            args.append(kind)
        if data_as_of:
            where.append("data_as_of = ?")
            args.append(data_as_of)
        # 软删的 Run 不出现在列表里（但 get() 仍取得到，撤销才可能）。
        where.append("deleted_at IS NULL")
        sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        return [self._row(r) for r in self.conn.execute(sql, args).fetchall()]  # type: ignore[misc]

    def soft_delete(self, rid: str) -> bool:
        """软删一条 Run。

        **为什么不是硬删**（ROUND2 §13）：Run 是「这次计算跑的是哪一版代码、
        哪一份数据」的唯一证据。硬删之后「可复现」就变成空话 —— 你无法证明
        当时那个数字是怎么来的。而删错的代价是不对称的：多留一条列表脏一点，
        删掉一条则永远回不来。
        """
        cur = self.conn.execute(
            "UPDATE run SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (time.time(), rid),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def restore(self, rid: str) -> bool:
        cur = self.conn.execute(
            "UPDATE run SET deleted_at = NULL WHERE id = ? AND deleted_at IS NOT NULL",
            (rid,),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def set_note(self, rid: str, note: str) -> bool:
        """写一行备注（「这一版想验证什么」）。与 note_id 不同：那个指向研究线文档。"""
        cur = self.conn.execute("UPDATE run SET note = ? WHERE id = ?", (note, rid))
        self.conn.commit()
        return cur.rowcount > 0

    def list_by_note(self, note_id: str) -> list[dict[str, Any]]:
        """某个研究判断下跑过的全部 Run（M5-3：这个判断我用什么验证过）。"""
        rows = self.conn.execute(
            "SELECT * FROM run WHERE note_id = ? ORDER BY created_at ASC", (note_id,)
        ).fetchall()
        return [self._row(r) for r in rows]  # type: ignore[misc]

    def diff(self, a_id: str, b_id: str) -> dict[str, Any]:
        """两个 Run 的差异（M3-4）：参数变化 + 指标 delta。

        约定：只有一侧有的指标 delta 为 None（**不是 0**）——
        delta=0 会让人以为「没变化」，而实际是「这一侧根本没这个指标」。
        """
        a = self.get(a_id)
        b = self.get(b_id)
        if a is None:
            raise KeyError(a_id)
        if b is None:
            raise KeyError(b_id)

        params = {
            k: {"a": a["params"].get(k), "b": b["params"].get(k)}
            for k in set(a["params"]) | set(b["params"])
            if a["params"].get(k) != b["params"].get(k)
        }
        metrics: dict[str, Any] = {}
        for k in set(a["metrics"]) | set(b["metrics"]):
            av, bv = a["metrics"].get(k), b["metrics"].get(k)
            both = isinstance(av, (int, float)) and isinstance(bv, (int, float))
            metrics[k] = {
                "a": av, "b": bv,
                "delta": (bv - av) if both else None,
            }
        return {"a": a_id, "b": b_id, "params": params, "metrics": metrics}


class ViewRepo:
    """View：保存的「看什么」（M3-3）。页面 = View 的集合。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(
        self, *, name: str, kind: str, params: dict[str, Any] | None = None,
        last_run_id: str | None = None, note_id: str = "",
    ) -> str:
        vid = _new_id("view")
        now = time.time()
        self.conn.execute(
            "INSERT INTO view "
            "(id, name, kind, params, pinned, last_run_id, note_id, created_at, updated_at) "
            "VALUES (?,?,?,?,0,?,?,?,?)",
            (vid, name, kind, json.dumps(params or {}, ensure_ascii=False),
             last_run_id, note_id, now, now),
        )
        self.conn.commit()
        return vid

    def _row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        d = dict(row)
        d["params"] = json.loads(d.get("params") or "{}")
        d["pinned"] = bool(d.get("pinned"))
        return d

    def get(self, vid: str) -> dict[str, Any] | None:
        return self._row(self.conn.execute("SELECT * FROM view WHERE id = ?", (vid,)).fetchone())

    def list_all(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM view ORDER BY updated_at DESC").fetchall()
        return [self._row(r) for r in rows]  # type: ignore[misc]

    def list_pinned(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM view WHERE pinned = 1 ORDER BY updated_at DESC"
        ).fetchall()
        return [self._row(r) for r in rows]  # type: ignore[misc]

    def set_pinned(self, vid: str, pinned: bool) -> None:
        self.conn.execute(
            "UPDATE view SET pinned = ?, updated_at = ? WHERE id = ?",
            (1 if pinned else 0, time.time(), vid),
        )
        self.conn.commit()

    def delete(self, vid: str) -> None:
        self.conn.execute("DELETE FROM view WHERE id = ?", (vid,))
        self.conn.commit()


class DocRepo:
    """文档库聚合：doc。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add_doc(
        self,
        title: str,
        source_path: str,
        text: str = "",
        *,
        kind: str = "note",
        tags: str = "",
        file_path: str = "",
        bytes_: int = 0,
        mime: str = "",
    ) -> str:
        """新增一条归档。

        `kind` 区分形态（note / pdf / markdown / image）—— 前端据此决定
        「用 <img> 预览 / 用 iframe 嵌 PDF / 直接渲染正文」，不靠猜扩展名。
        `file_path` 是**相对** `workspace/reports/` 的文件名：存绝对路径会让
        备份/搬家后全部失效，而且会把本机目录结构写进数据库。
        """
        did = _new_id("d")
        self.conn.execute(
            "INSERT INTO doc (id, title, source_path, text, kind, tags, file_path, "
            "bytes, mime, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (did, title, source_path, text, kind, tags, file_path, bytes_, mime, time.time()),
        )
        self.conn.commit()
        return did

    def get_doc(self, did: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM doc WHERE id=?", (did,)).fetchone()
        return dict(row) if row else None

    def list_docs(self) -> list[dict[str, Any]]:
        """归档列表。**不含软删**；`text` 全文不回传（可能几百 KB，列表不需要）。"""
        rows = self.conn.execute(
            "SELECT id, title, source_path, kind, tags, file_path, bytes, mime, "
            "deleted_at, created_at FROM doc WHERE deleted_at IS NULL "
            "ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def soft_delete_doc(self, did: str) -> bool:
        cur = self.conn.execute(
            "UPDATE doc SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (time.time(), did),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def restore_doc(self, did: str) -> bool:
        cur = self.conn.execute(
            "UPDATE doc SET deleted_at = NULL WHERE id = ? AND deleted_at IS NOT NULL",
            (did,),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def update_doc_meta(
        self, did: str, *, title: str | None = None, tags: str | None = None
    ) -> bool:
        sets: list[str] = []
        args: list[Any] = []
        if title is not None:
            sets.append("title = ?")
            args.append(title)
        if tags is not None:
            sets.append("tags = ?")
            args.append(tags)
        if not sets:
            return False
        args.append(did)
        cur = self.conn.execute(f"UPDATE doc SET {', '.join(sets)} WHERE id = ?", args)
        self.conn.commit()
        return cur.rowcount > 0

    def thread(self, did: str) -> dict[str, Any]:
        """一条研究线的完整视图（M5-3）：笔记本身 + 它的 Run + 它的 View。

        为什么放在 DocRepo：调用方问的是「这条笔记的研究线」，
        笔记是主语。让它去拼 runs/views 两个 repo 是合理的编排，
        而反过来（RunRepo 提供 thread）语义是歪的。
        """
        note = self.get_doc(did)
        runs = self.conn.execute(
            "SELECT * FROM run WHERE note_id = ? ORDER BY created_at ASC", (did,)
        ).fetchall()
        views = self.conn.execute(
            "SELECT * FROM view WHERE note_id = ? ORDER BY created_at ASC", (did,)
        ).fetchall()

        def _run(r: sqlite3.Row) -> dict[str, Any]:
            d = dict(r)
            d["params"] = json.loads(d.get("params") or "{}")
            d["metrics"] = json.loads(d.get("metrics") or "{}")
            d["artifact_ids"] = json.loads(d.get("artifact_ids") or "[]")
            d["inputs"] = json.loads(d.get("inputs") or "{}")
            return d

        def _view(r: sqlite3.Row) -> dict[str, Any]:
            d = dict(r)
            d["params"] = json.loads(d.get("params") or "{}")
            d["pinned"] = bool(d.get("pinned"))
            return d

        return {
            "note": note,
            "runs": [_run(r) for r in runs],
            "views": [_view(v) for v in views],
        }

    def delete_doc(self, did: str) -> bool:
        cur = self.conn.execute("DELETE FROM doc WHERE id=?", (did,))
        self.conn.commit()
        return cur.rowcount > 0


class SettingRepo:
    """键值设置（ROUND2 §13，A3）。

    只放**运行时该改的东西**，不放大配置：模型 id 属于前者（换模型要立刻生效），
    数据源地址/密钥属于后者（改了等于换环境，应当走配置文件）。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM setting WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO setting (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "updated_at=excluded.updated_at",
            (key, value, time.time()),
        )
        self.conn.commit()


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
        self.runs = RunRepo(self.conn)
        self.views = ViewRepo(self.conn)
        self.settings = SettingRepo(self.conn)

    def migrate(self) -> None:
        """建表 + 增量迁移（幂等）。这是唯一的迁移入口。"""
        self.conn.executescript(SCHEMA)
        _migrate_page_kind(self.conn)
        _migrate_artifact_provenance(self.conn)
        _migrate_session_runtime_id(self.conn)
        _migrate_run_inputs(self.conn)
        _migrate_note_links(self.conn)
        _migrate_page_soft_delete(self.conn)
        _migrate_soft_delete_and_meta(self.conn)
        _migrate_setting_table(self.conn)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------- session（委派 SessionRepo）----------
    def create_session(self, title: str = "") -> str:
        return self.sessions.create_session(title)

    def get_session(self, sid: str) -> dict[str, Any] | None:
        return self.sessions.get_session(sid)

    def set_runtime_session_id(self, sid: str, runtime_session_id: str | None) -> None:
        self.sessions.set_runtime_session_id(sid, runtime_session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.sessions.list_sessions()

    def delete_session(self, sid: str) -> bool:
        return self.sessions.delete_session(sid)

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
        provenance: Any = None,
    ) -> str:
        return self.sessions.add_artifact(
            run_id, kind, path,
            message_id=message_id, title=title, payload=payload, inputs=inputs,
            provenance=provenance,
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

    def delete_page(self, pid: str) -> bool:
        return self.pages.delete_page(pid)

    def restore_page(self, pid: str) -> tuple[bool, str]:
        return self.pages.restore_page(pid)

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
