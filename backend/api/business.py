"""业务页 CRUD REST（S3）——股票池 / 交易日志 / 我的研报（文档库）。

状态型业务页的真源是 SQLite（AGENTS 边界：业务层唯一持有产品数据库）。
本 router 是薄 CRUD：校验 → 调 store repo → 回 JSON。零分析逻辑。

  股票池 stock_pool：
    GET    /api/stock-pool           列出
    POST   /api/stock-pool           加入/更新（code 唯一 upsert）
    DELETE /api/stock-pool/{code}    移除
  交易日志 journal：
    GET    /api/journal              列出
    POST   /api/journal              新增一条成交
    POST   /api/journal/import       批量导入（vibe-astock JSON / 标准 CSV 行数组）
    DELETE /api/journal/{jid}        删除
  我的研报 reports（复用 doc 表）：
    GET    /api/reports              列出（遗留；新前端走 /api/docs）
    POST   /api/reports              新增（标题 + 文本/来源）
  研报归档库 docs（ROUND3 B4，doc 表的完整 CRUD + 附件）：
    GET    /api/docs                 列出（软删已排除，不回 text）
    GET    /api/docs/{did}           单条（含 text）
    POST   /api/docs                 multipart 上传（PDF / Markdown / 图片）
    POST   /api/docs/note            纯文本笔记
    GET    /api/docs/{did}/file      原文件（<img> / <iframe> 预览用）
    PATCH  /api/docs/{did}           改标题/标签
    DELETE /api/docs/{did}           软删（可 restore）
    POST   /api/docs/{did}/restore   撤销软删
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.store import Store

# ---------------------------------------------------------------------------
# 研报归档库（ROUND3 B4）
#
# 三件事必须做对，否则这一页就是个「假的上传控件」：
#   1. **kind / mime 由文件字节决定，不由前端说了算**。浏览器给的 Content-Type
#      是按扩展名猜的 —— 把 .html 改名成 .pdf 照样报 application/pdf。
#      所以这里嗅 magic number（PDF/PNG/JPEG/GIF/WEBP）+ 试 UTF-8 解码，
#      扩展名只做一致性对照。
#   2. **落盘位置固定，DB 只存文件名**。存绝对路径在备份/搬家后全失效，
#      还会把本机目录结构写进数据库。
#   3. **删除是软删**。手写的研报笔记不是可再生资源（AGENTS 硬规则 14）。
# ---------------------------------------------------------------------------

DOCS_SUBDIR = "reports"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: 扩展名 → kind。**不是**分类的全部依据（还有内容嗅探），只用来要求
#: 「扩展名与内容一致」—— kind 决定前端用哪个预览器，判错就是白屏。
KIND_BY_EXT = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
}

WHITELIST_HINT = "只接受 PDF / Markdown / 图片"


def _sniff_binary(data: bytes) -> tuple[str, str] | None:
    """按 magic number 判 (kind, mime)。不认识则 None（可能是文本）。"""
    head = data[:16]
    if head.startswith(b"%PDF"):
        return "pdf", "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image", "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image", "image/webp"
    return None


def _is_utf8_text(data: bytes) -> bool:
    """是不是可以当 Markdown 渲染的文本。

    含 NUL 字节的一律不算（那是二进制被改了扩展名）。
    解码整份而不是前 4KB：截断会把多字节字符切成两半，误判成二进制。
    """
    if b"\x00" in data[:4096]:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def classify_upload(filename: str, data: bytes) -> tuple[str, str]:
    """判定 (kind, mime)；不合格抛 400。

    白名单三步：扩展名 → 内容嗅探 → 两者一致。任何一步不过就拒，
    错误消息里始终带 `WHITELIST_HINT`（前端直接展示这句话）。
    """
    ext = Path(filename or "").suffix.lower()
    kind = KIND_BY_EXT.get(ext)
    if kind is None:
        raise HTTPException(400, f"不支持的扩展名 {ext or '(无)'}；{WHITELIST_HINT}")

    sniffed = _sniff_binary(data)
    if kind == "markdown":
        if sniffed is not None:
            raise HTTPException(
                400, f"扩展名是 {ext}，但内容是 {sniffed[0]}；{WHITELIST_HINT}"
            )
        if not _is_utf8_text(data):
            raise HTTPException(400, f"{ext} 的内容不是 UTF-8 文本；{WHITELIST_HINT}")
        # 统一记 text/markdown：浏览器对 .md 会给 text/plain 甚至空串，
        # 存前端猜的那个值等于把猜测写进数据库。
        return "markdown", "text/markdown"

    if sniffed is None or sniffed[0] != kind:
        got = sniffed[0] if sniffed else "文本/未知"
        raise HTTPException(400, f"扩展名是 {ext}，但内容是 {got}；{WHITELIST_HINT}")
    return sniffed


def reports_dir(store: Store, workspace_root: Path | None = None) -> Path:
    """附件落盘目录 `<workspace>/reports/`。

    workspace_root 从哪来：`Store` 只持有一个 sqlite 连接，没有 workspace 概念。
    但本项目的约定是**数据库就放在 workspace 根下**——
      · `api/main.py`：`db = <repo>/workspace/alphacopilot.db`，`ws = <repo>/workspace`
      · 测试 fixture：`db_path=tmp_path/"t.db"`，`workspace_root=tmp_path`
    两处 `Path(db_path).parent` 都恰好等于 workspace_root，
    所以不需要让 app.py 额外注入（它的签名不在本包所有权内）。

    `:memory:` 没有磁盘目录，退回 `<cwd>/workspace`（只影响交互式内存库）。
    """
    if workspace_root is not None:
        return Path(workspace_root) / DOCS_SUBDIR
    raw = str(getattr(store, "_path", "") or "")
    parent = Path(raw).parent if raw and raw != ":memory:" else Path(".")
    if raw == ":memory:" or str(parent) in (".", ""):
        parent = Path.cwd() / "workspace"
    return parent / DOCS_SUBDIR


class StockPoolIn(BaseModel):
    code: str
    name: str = ""
    note: str = ""
    tags: str = ""


class JournalIn(BaseModel):
    code: str = ""
    name: str = ""
    side: str
    price: float
    shares: int
    fee: float = 0.0
    traded_at: str = ""
    note: str = ""


class JournalImportIn(BaseModel):
    rows: list[dict[str, Any]]


class ReportIn(BaseModel):
    title: str
    text: str = ""
    source_path: str = ""


class DocNoteIn(BaseModel):
    title: str
    text: str = ""
    tags: str = ""


class DocMetaIn(BaseModel):
    title: str | None = None
    tags: str | None = None


class PortfolioIn(BaseModel):
    name: str
    benchmark: str = "000300"
    created_on: str = ""


class RebalanceIn(BaseModel):
    effective_on: str
    weights: dict[str, float]


async def _read_capped(file: UploadFile) -> bytes:
    """分块读，**边读边卡上限**。

    先 `await file.read()` 再判长度等于放任客户端把内存打满；
    20MB 的闸门应该在字节流进来的路上，不是在读完以后。
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "文件超过 20MB 上限")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(400, "空文件")
    return data


def build_business_router(
    store: Store, workspace_root: Path | None = None
) -> APIRouter:
    """业务页 CRUD。

    `workspace_root` 可空：app.py 只传 store（它的签名不在本包所有权内），
    此时按 `reports_dir()` 里写明的约定从 db 路径推出。
    """
    router = APIRouter(prefix="/api")

    # ---------- 股票池 ----------
    @router.get("/stock-pool")
    def list_pool() -> list:
        return store.stock_pool.list()

    @router.post("/stock-pool")
    def add_pool(body: StockPoolIn) -> dict:
        code = body.code.strip()
        if not (len(code) == 6 and code.isdigit()):
            raise HTTPException(400, f"非法标的代码 {code!r}（须 6 位数字）")
        pid = store.stock_pool.add(code, body.name, body.note, body.tags)
        return {"id": pid, "code": code}

    @router.delete("/stock-pool/{code}")
    def remove_pool(code: str) -> dict:
        if not store.stock_pool.remove(code):
            raise HTTPException(404, "不在股票池中")
        return {"ok": True}

    # ---------- 交易日志 ----------
    @router.get("/journal")
    def list_journal() -> list:
        return store.journal.list()

    @router.post("/journal")
    def add_journal(body: JournalIn) -> dict:
        try:
            jid = store.journal.add(
                code=body.code, name=body.name, side=body.side, price=body.price,
                shares=body.shares, fee=body.fee, traded_at=body.traded_at, note=body.note,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"id": jid}

    @router.post("/journal/import")
    def import_journal(body: JournalImportIn) -> dict:
        """批量导入。每行支持 vibe-astock/标准字段：code/name/side/price/shares/fee/traded_at/note。

        导入前逐行校验 side/price/shares；任一行非法则整批拒绝（预览校验语义），不部分写入。
        """
        parsed: list[dict[str, Any]] = []
        for i, row in enumerate(body.rows):
            side = str(row.get("side", "")).lower()
            if side not in ("buy", "sell"):
                raise HTTPException(400, f"第 {i + 1} 行 side 非法: {row.get('side')!r}")
            try:
                price = float(row.get("price"))
                shares = int(row.get("shares"))
            except (TypeError, ValueError) as e:
                raise HTTPException(400, f"第 {i + 1} 行 price/shares 非法") from e
            parsed.append({
                "code": str(row.get("code", "")), "name": str(row.get("name", "")),
                "side": side, "price": price, "shares": shares,
                "fee": float(row.get("fee", 0) or 0),
                "traded_at": str(row.get("traded_at", "")), "note": str(row.get("note", "")),
            })
        for p in parsed:
            store.journal.add(**p)
        return {"imported": len(parsed)}

    @router.delete("/journal/{jid}")
    def remove_journal(jid: str) -> dict:
        if not store.journal.remove(jid):
            raise HTTPException(404, "日志不存在")
        return {"ok": True}

    # ---------- 我的研报（复用 doc 表，遗留端点）----------
    @router.get("/reports")
    def list_reports() -> list:
        return store.docs.list_docs()

    @router.post("/reports")
    def add_report(body: ReportIn) -> dict:
        if not body.title.strip():
            raise HTTPException(400, "标题不能为空")
        did = store.docs.add_doc(body.title, body.source_path or "manual", body.text)
        return {"id": did}

    @router.delete("/reports/{did}")
    def remove_report(did: str) -> dict:
        # 曾经是硬 DELETE：研报不是可再生资源（AGENTS 硬规则 14），改成软删。
        # 新前端走 /api/docs/{did}，这里留着只为兼容旧调用方。
        if not store.docs.soft_delete_doc(did):
            raise HTTPException(404, "研报不存在")
        return {"ok": True, "soft": True}

    # ---------- 研报归档库（ROUND3 B4）----------
    docs_dir = reports_dir(store, workspace_root)

    def _row(payload: dict[str, Any]) -> dict[str, Any]:
        """回给前端的 DocRow。`id/title/...` 与 `api.ts:DocRow` 对齐。"""
        return {
            "id": payload["id"],
            "title": payload["title"],
            "source_path": payload.get("source_path", ""),
            "kind": payload.get("kind", "note"),
            "tags": payload.get("tags", ""),
            "file_path": payload.get("file_path", ""),
            "bytes": payload.get("bytes", 0),
            "mime": payload.get("mime", ""),
            "created_at": payload["created_at"],
        }

    @router.get("/docs")
    def list_docs() -> list:
        return store.docs.list_docs()

    # `/docs/note` 必须写在 `/docs/{did}` 之前：FastAPI 按注册顺序匹配。
    @router.post("/docs/note")
    def create_doc_note(body: DocNoteIn) -> dict:
        title = body.title.strip()
        if not title:
            raise HTTPException(400, "标题不能为空")
        did = store.docs.add_doc(
            title, "manual", body.text, kind="note", tags=body.tags.strip()
        )
        doc = store.docs.get_doc(did)
        assert doc is not None  # 刚插入的行不可能取不到
        return _row(doc)

    @router.post("/docs")
    async def upload_doc(
        file: Annotated[UploadFile, File()],
        title: Annotated[str, Form()] = "",
        tags: Annotated[str, Form()] = "",
    ) -> dict:
        """multipart 上传。校验顺序：大小（流式读时卡）→ 白名单 → 落盘。

        409 不适用：同名文件不冲突（文件名是 id），想重传就重传。
        """
        data = await _read_capped(file)
        name = file.filename or ""
        kind, mime = classify_upload(name, data)
        ext = Path(name).suffix.lower()
        stem = Path(name).stem.strip()

        did = store.docs.add_doc(
            (title.strip() or stem or "未命名归档"),
            name,  # source_path 存用户看到的原文件名，便于列表里认出来
            "",
            kind=kind,
            tags=tags.strip(),
            bytes_=len(data),
            mime=mime,
        )

        # 文件名要 `<did><ext>`，而 did 由 add_doc 内部生成（uuid），插入前不可预知；
        # DocRepo 没有「补 file_path」的公开方法（update_doc_meta 只改 title/tags），
        # 所以这里直接补三列。改 store.py 不在 B4 的文件所有权内。
        rel_name = f"{did}{ext}"
        try:
            docs_dir.mkdir(parents=True, exist_ok=True)
            (docs_dir / rel_name).write_bytes(data)
            store.conn.execute(
                "UPDATE doc SET file_path=?, bytes=?, mime=? WHERE id=?",
                (rel_name, len(data), mime, did),
            )
            store.conn.commit()
        except OSError as e:
            # 落盘失败就把刚插的行收回 —— 一条只有元信息、没有文件的归档
            # 在列表里看起来完全正常，点开才报错，比直接报错更难排查。
            store.docs.delete_doc(did)
            raise HTTPException(500, f"附件写入失败: {e}") from e

        doc = store.docs.get_doc(did)
        assert doc is not None
        return _row(doc)

    @router.get("/docs/{did}")
    def get_doc(did: str) -> dict:
        doc = store.docs.get_doc(did)
        # 软删的对外不存在；restore 走的是另一个端点（它用同一份 get_doc 找到行）。
        if doc is None or doc.get("deleted_at"):
            raise HTTPException(404, "研报不存在或已删除")
        out = _row(doc)
        out["text"] = doc.get("text", "")
        return out

    @router.patch("/docs/{did}")
    def patch_doc(did: str, body: DocMetaIn) -> dict:
        if store.docs.get_doc(did) is None:
            raise HTTPException(404, "研报不存在")
        title = body.title.strip() if body.title is not None else None
        if title is not None and not title:
            raise HTTPException(400, "标题不能为空")
        if title is None and body.tags is None:
            raise HTTPException(400, "没有要改的字段")
        store.docs.update_doc_meta(
            did, title=title, tags=body.tags.strip() if body.tags is not None else None
        )
        return {"ok": True}

    @router.get("/docs/{did}/file")
    def get_doc_file(did: str):
        """原文件。`<img src>` / `<iframe src>` 直接指这里，所以**不能**带
        Content-Disposition: attachment（那会变成下载而不是预览）。"""
        doc = store.docs.get_doc(did)
        if doc is None:
            raise HTTPException(404, "研报不存在")
        rel = str(doc.get("file_path") or "").strip()
        if not rel:
            raise HTTPException(404, "该条目没有附件")
        # 防御：库被写坏时（或未来有人存了路径）不能变成任意文件读取。
        # file_path 的契约是**纯文件名**，出现分隔符即为非法数据。
        if Path(rel).name != rel or rel in (".", ".."):
            raise HTTPException(400, "非法的附件路径")
        path = docs_dir / rel
        if not path.is_file():
            raise HTTPException(404, "附件文件已丢失")
        return FileResponse(path, media_type=str(doc.get("mime") or "application/octet-stream"))

    @router.delete("/docs/{did}")
    def remove_doc(did: str) -> dict:
        if not store.docs.soft_delete_doc(did):
            raise HTTPException(404, "研报不存在或已删除")
        return {"ok": True, "soft": True}

    @router.post("/docs/{did}/restore")
    def restore_doc(did: str) -> dict:
        if not store.docs.restore_doc(did):
            raise HTTPException(404, "研报不存在或未被删除")
        return {"ok": True}

    # ---------- 模拟组合（雪球式调仓事件）----------
    @router.get("/portfolios")
    def list_portfolios() -> list:
        out = []
        for pf in store.portfolio.list():
            pf["rebalances"] = store.portfolio.list_rebalances(pf["id"])
            out.append(pf)
        return out

    @router.post("/portfolios")
    def create_portfolio(body: PortfolioIn) -> dict:
        if not body.name.strip():
            raise HTTPException(400, "组合名不能为空")
        pid = store.portfolio.create(body.name, body.benchmark, body.created_on)
        return {"id": pid}

    @router.delete("/portfolios/{pid}")
    def delete_portfolio(pid: str) -> dict:
        if not store.portfolio.delete(pid):
            raise HTTPException(404, "组合不存在")
        return {"ok": True}

    @router.post("/portfolios/{pid}/rebalance")
    def add_rebalance(pid: str, body: RebalanceIn) -> dict:
        if store.portfolio.get(pid) is None:
            raise HTTPException(404, "组合不存在")
        for code, w in body.weights.items():
            if not (len(code) == 6 and code.isdigit()):
                raise HTTPException(400, f"非法标的 {code!r}")
            if w < 0 or w > 1:
                raise HTTPException(400, f"{code} 权重 {w} 越界 [0,1]")
        total = sum(body.weights.values())
        if total > 1.0 + 1e-9:
            raise HTTPException(400, f"权重和 {total:.3f} > 1（超出部分应为现金）")
        rid = store.portfolio.add_rebalance(pid, body.effective_on, body.weights)
        return {"id": rid}

    @router.get("/portfolios/{pid}/nav")
    def portfolio_nav(pid: str) -> dict:
        """组合净值曲线 vs 基准（ECharts line option）。数据源不可用时优雅降级。"""
        from alpha import chart, data
        from alpha import portfolio as pf_calc

        pf = store.portfolio.get(pid)
        if pf is None:
            raise HTTPException(404, "组合不存在")
        events = store.portfolio.list_rebalances(pid)
        if not events:
            return {"option": chart.line([], {"组合净值": []}, title="尚无调仓事件")}
        codes = sorted({c for e in events for c in e["weights"]})
        price_map: dict[str, dict[str, float]] = {}
        for code in codes:
            try:
                rows = data.closes_with_dates(code, count=250)
            except Exception:  # noqa: BLE001
                rows = []
            price_map[code] = {d: c for d, c in rows}
        dates, nav = pf_calc.compute_nav(events, price_map)
        if not dates:
            return {"option": chart.line([], {"组合净值": []},
                                         title="行情数据源暂不可用，净值待计算")}
        series = {"组合净值": nav}
        try:
            brows = data.closes_with_dates(pf["benchmark"], count=250)
            bench = pf_calc.compute_benchmark_nav(dates, {d: c for d, c in brows})
            if bench:
                series[f"基准({pf['benchmark']})"] = bench
        except Exception:  # noqa: BLE001
            pass
        return {"option": chart.line(dates, series, title=f"{pf['name']} 净值")}

    return router
