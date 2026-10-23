"""研报归档库（ROUND3 B4）—— 上传落盘 / MIME 白名单 / 软删恢复 / 附件分发。

这一包把「我的研报」从「一个能粘文本的输入框」变成**归档库**：能收 PDF、Markdown、
图片，能按 kind 选预览器，能软删后撤销。

几条测试背后的真实风险：

  · **只信 Content-Type 等于没校验**：浏览器给的 Content-Type 由扩展名猜出来，
    把 `.html` 改名成 `.pdf` 照样报 `application/pdf`。所以真正决定 kind/mime 的
    必须是**文件字节**（magic number / UTF-8 可解码），扩展名只做一致性对照。
  · **file_path 只能存文件名**：存绝对路径会在备份/搬家后全部失效，还会把本机
    目录结构写进数据库。
  · **删除必须可撤销**：手写的研报笔记不是可再生资源（AGENTS 硬规则 14），
    所以 DELETE 是软删 + restore，不是硬删。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app

# 最小但**真的**是 PDF 的字节（magic %PDF + EOF 标记）
PDF_BYTES = (
    b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 40
MD_BYTES = "# 白酒行业 2025\n\n结论：高端酒动销好于次高端。\n".encode()
TXT_BYTES = b"just some plain text\n"


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "t.db"), workspace_root=tmp_path)
    with TestClient(app) as c:
        yield c


def _upload(client, name: str, data: bytes, mime: str, **form):
    return client.post(
        "/api/docs",
        files={"file": (name, data, mime)},
        data={k: v for k, v in form.items()},
    )


# ---------- 上传：落盘 + kind 判定 ----------

def test_upload_pdf_writes_file_and_records_kind(client, tmp_path):
    r = _upload(client, "白酒研报.pdf", PDF_BYTES, "application/pdf")
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["kind"] == "pdf"
    assert row["mime"] == "application/pdf"
    assert row["bytes"] == len(PDF_BYTES)

    # file_path 存的是**文件名**（相对 workspace/reports/），不是绝对路径
    assert row["file_path"] == f"{row['id']}.pdf"
    assert "/" not in row["file_path"] and "\\" not in row["file_path"]

    landed = tmp_path / "reports" / row["file_path"]
    assert landed.is_file()
    assert landed.read_bytes() == PDF_BYTES

    # 列表能看到它
    docs = client.get("/api/docs").json()
    assert [d["id"] for d in docs] == [row["id"]]


def test_upload_markdown_and_image_kind(client):
    md = _upload(client, "白酒.md", MD_BYTES, "text/markdown")
    assert md.status_code == 200, md.text
    assert md.json()["kind"] == "markdown"

    img = _upload(client, "k线.png", PNG_BYTES, "image/png")
    assert img.status_code == 200, img.text
    assert img.json()["kind"] == "image"
    assert img.json()["mime"] == "image/png"


def test_upload_title_defaults_to_filename_stem(client):
    row = _upload(client, "宏观周报.md", MD_BYTES, "text/markdown").json()
    assert row["title"] == "宏观周报"


def test_upload_accepts_explicit_title_and_tags(client):
    row = _upload(client, "a.md", MD_BYTES, "text/markdown",
                  title="自定义标题", tags="白酒,周报").json()
    assert row["title"] == "自定义标题"
    assert row["tags"] == "白酒,周报"


def test_upload_txt_is_rejected(client):
    r = _upload(client, "笔记.txt", TXT_BYTES, "text/plain")
    assert r.status_code == 400
    assert "只接受 PDF / Markdown / 图片" in r.json()["detail"]


def test_declared_content_type_is_not_trusted(client):
    # 客户端声称 application/pdf，实际是 html 文本 —— 必须按**内容**判定并拒绝
    r = _upload(client, "伪装.pdf", b"<html><body>not a pdf</body></html>", "application/pdf")
    assert r.status_code == 400, r.text
    assert "只接受 PDF / Markdown / 图片" in r.json()["detail"]


def test_extension_content_mismatch_is_rejected(client):
    # 真 PDF 内容 + .png 扩展名 → 拒绝（kind 决定预览器，错了就是白屏）
    r = _upload(client, "其实是pdf.png", PDF_BYTES, "image/png")
    assert r.status_code == 400
    assert "只接受 PDF / Markdown / 图片" in r.json()["detail"]


def test_binary_disguised_as_markdown_is_rejected(client):
    r = _upload(client, "假markdown.md", PNG_BYTES, "text/markdown")
    assert r.status_code == 400


def test_upload_over_20mb_is_413(client):
    big = PDF_BYTES + b"\x00" * (20 * 1024 * 1024 + 1)
    r = _upload(client, "超限.pdf", big, "application/pdf")
    assert r.status_code == 413


# ---------- 单条读写 ----------

def test_get_doc_returns_text_and_404(client):
    did = client.post("/api/docs/note",
                      json={"title": "估值判断", "text": "PE 分位 30%"}).json()["id"]
    r = client.get(f"/api/docs/{did}")
    assert r.status_code == 200
    assert r.json()["text"] == "PE 分位 30%"
    assert r.json()["kind"] == "note"
    assert client.get("/api/docs/nope").status_code == 404


def test_note_requires_title(client):
    r = client.post("/api/docs/note", json={"title": "   ", "text": "x"})
    assert r.status_code == 400


def test_patch_updates_title_and_tags(client):
    did = client.post(
        "/api/docs/note", json={"title": "旧标题", "text": "x", "tags": "旧"}
    ).json()["id"]
    r = client.patch(f"/api/docs/{did}", json={"title": "新标题", "tags": "新,归档"})
    assert r.status_code == 200
    row = client.get(f"/api/docs/{did}").json()
    assert row["title"] == "新标题" and row["tags"] == "新,归档"


def test_patch_404_and_empty_title_400(client):
    assert client.patch("/api/docs/nope", json={"title": "x"}).status_code == 404
    did = client.post("/api/docs/note", json={"title": "标题", "text": ""}).json()["id"]
    assert client.patch(f"/api/docs/{did}", json={"title": "  "}).status_code == 400


# ---------- 软删 / 恢复 ----------

def test_delete_is_soft_and_undoable(client):
    did = _upload(client, "待删.pdf", PDF_BYTES, "application/pdf").json()["id"]
    r = client.delete(f"/api/docs/{did}")
    assert r.status_code == 200 and r.json() == {"ok": True, "soft": True}
    assert client.get("/api/docs").json() == []

    # 软删不是消失：detail 404（对外不可见），但 restore 找得回来
    assert client.get(f"/api/docs/{did}").status_code == 404
    assert client.post(f"/api/docs/{did}/restore").status_code == 200
    assert [d["id"] for d in client.get("/api/docs").json()] == [did]


def test_delete_and_restore_404(client):
    assert client.delete("/api/docs/nope").status_code == 404
    assert client.post("/api/docs/nope/restore").status_code == 404
    did = client.post("/api/docs/note", json={"title": "没删过", "text": ""}).json()["id"]
    # 没删过的条目「恢复」是 404（不是静默 200 —— 否则前端撤销条会假装成功）
    assert client.post(f"/api/docs/{did}/restore").status_code == 404
    # 重复删除同样 404（第一次已经删掉了）
    assert client.delete(f"/api/docs/{did}").status_code == 200
    assert client.delete(f"/api/docs/{did}").status_code == 404


# ---------- 附件分发 ----------

def test_file_endpoint_serves_original_bytes_with_content_type(client):
    did = _upload(client, "白酒.pdf", PDF_BYTES, "application/pdf").json()["id"]
    r = client.get(f"/api/docs/{did}/file")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content == PDF_BYTES


def test_file_endpoint_404_for_note_without_attachment(client):
    did = client.post("/api/docs/note", json={"title": "只有正文", "text": "x"}).json()["id"]
    assert client.get(f"/api/docs/{did}/file").status_code == 404
    assert client.get("/api/docs/nope/file").status_code == 404


def test_file_endpoint_refuses_path_traversal(client, monkeypatch):
    """file_path 是库里的一列 —— 库被写坏时不能变成任意文件读取。"""
    from api.store import Store  # noqa: F401  （只为确认使用同一个 Store）

    did = _upload(client, "a.md", MD_BYTES, "text/markdown").json()["id"]
    store = client.app.state.store
    store.conn.execute("UPDATE doc SET file_path=? WHERE id=?", ("../../etc/passwd", did))
    store.conn.commit()
    r = client.get(f"/api/docs/{did}/file")
    assert r.status_code == 400


def test_file_endpoint_404_when_file_vanished(client, tmp_path):
    did = _upload(client, "a.md", MD_BYTES, "text/markdown").json()["id"]
    (tmp_path / "reports" / f"{did}.md").unlink()
    assert client.get(f"/api/docs/{did}/file").status_code == 404


# ---------- 与遗留 /api/reports 的关系 ----------

def test_legacy_reports_delete_is_soft_too(client):
    """老端点曾硬删文档行 —— 研报不是可再生资源，改成软删（可恢复）。"""
    did = client.post("/api/reports", json={"title": "老接口归档", "text": "x"}).json()["id"]
    assert client.delete(f"/api/reports/{did}").status_code == 200
    assert client.get("/api/reports").json() == []
    assert client.post(f"/api/docs/{did}/restore").status_code == 200
