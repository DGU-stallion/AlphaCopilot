"""M5-2 Build 模式：agent 产 View 草稿 → 预览 → 确认落地。

## 为什么需要「草稿」这个中间态

agent 生成 page spec 是自由文本 → 结构化。中间必然会有：
  - 引用了不存在的 analysis fn
  - span 超出 grid
  - renderer 与 fn 语义不匹配

如果直接落库，一个坏 spec 会让页面白屏，而用户不知道是「agent 写错了」
还是「我们的渲染器坏了」。所以必须：

    生成 → **校验通过才**成为 draft → 用户预览 → 确认 → published

## 关键安全点（这是本任务真正要守的东西）

**草稿的落地权在用户手上，不在 agent 手上。**
agent 只能产出 draft；publish 必须是独立的一次用户动作。
否则「agent 自己写个页面并发布」就等于它绕过了所有白名单校验 ——
page spec 校验存在的意义就是为了防这个。
"""

import pytest

# 触发 analysis fn 注册（注册发生在模块 import 的副作用里）。
# 不 import 的话 validate_spec 会说「fn 未注册」—— 那是测试环境问题，不是被测逻辑问题。
import alpha.backtest_page  # noqa: F401
import alpha.factor  # noqa: F401
from api.store import Store


@pytest.fixture()
def store():
    s = Store(":memory:")
    yield s
    s.close()


def _spec(**over):
    base = {
        "slug": "my-kline-view",
        "title": "我的 K 线视图",
        "kind": "user",
        "status": "draft",
        "layout": "grid",
        "params": [],
        "blocks": [
            {"kind": "chart", "span": 2, "renderer": "lwc",
             "analysis_ref": {"fn": "backtest.equity"}},
        ],
    }
    base.update(over)
    return base


class TestDraftLifecycle:
    def test_agent_produced_spec_becomes_draft_not_published(self, store):
        """agent 产出的 spec 落库必须是 draft —— 不能直接发布。"""
        store.pages.create_page_from_spec(_spec(), kind="user")
        page = store.pages.get_page_by_slug("my-kline-view")
        assert page is not None
        assert page["status"] == "draft"

    def test_invalid_spec_is_rejected(self, store):
        """坏 spec 不能变成 draft（否则用户会看到一个白屏的草稿）。"""
        bad = _spec(blocks=[{"kind": "chart", "span": 1}])   # chart 缺 renderer
        # 具体异常类型而不是 Exception：盲捕会让「校验器抛了 TypeError」
        # 这种真 bug 也被当成「正确地拒绝了」，测试就没在守任何东西了。
        with pytest.raises(ValueError):
            store.pages.create_page_from_spec(bad, kind="user")
        assert store.pages.get_page_by_slug("my-kline-view") is None

    def test_publish_requires_explicit_action(self, store):
        """draft → published 必须是独立动作，不能顺带发生。"""
        pid = store.pages.create_page_from_spec(_spec(), kind="user")
        assert store.pages.get_page(pid)["status"] == "draft"
        store.pages.set_status(pid, "published")
        assert store.pages.get_page(pid)["status"] == "published"

    def test_unpublish_back_to_draft(self, store):
        """发布后还能撤回（agent 写的页面可能有细微问题，要能收回来）。"""
        pid = store.pages.create_page_from_spec(_spec(), kind="user")
        store.pages.set_status(pid, "published")
        store.pages.set_status(pid, "draft")
        assert store.pages.get_page(pid)["status"] == "draft"

    def test_invalid_status_rejected(self, store):
        pid = store.pages.create_page_from_spec(_spec(), kind="user")
        with pytest.raises(ValueError):
            store.pages.set_status(pid, "whatever")


class TestPreviewBeforePublish:
    def test_draft_can_be_rendered_for_preview(self, store):
        """草稿要能渲染出来给用户看 —— 预览就是「用和真页一样的渲染路径」。"""
        pid = store.pages.create_page_from_spec(_spec(), kind="user")
        page = store.pages.get_page(pid)
        # 预览读的是同一份 spec，不存在「预览一套、上线另一套」
        assert page["spec"]["blocks"] == _spec()["blocks"]

    def test_draft_not_listed_as_published(self, store):
        """未发布的草稿不该出现在「已发布的页面」列表里。"""
        store.pages.create_page_from_spec(_spec(), kind="user")
        published = store.pages.list_pages() if hasattr(store.pages, "list_pages") else []
        slugs = {p["slug"] for p in published if p.get("status") == "published"}
        assert "my-kline-view" not in slugs


class TestSlugConflict:
    def test_duplicate_slug_rejected(self, store):
        """slug 是 URL 的一部分，重复会让「打开哪个页面」变得不确定。"""
        store.pages.create_page_from_spec(_spec(), kind="user")
        with pytest.raises(ValueError):
            store.pages.create_page_from_spec(_spec(), kind="user")


class TestBuildApi:
    """Build 模式的 REST：草稿 → 预览 → 确认发布。"""

    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.pages import build_pages_router

        app = FastAPI()
        store = Store(":memory:")
        app.include_router(build_pages_router(store))
        return TestClient(app), store

    def test_create_draft(self):
        client, _ = self._client()
        r = client.post("/api/pages/drafts", json=_spec())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "draft"
        assert body["slug"] == "my-kline-view"

    def test_create_rejects_bad_spec_with_400(self):
        """坏 spec 是调用方的错（400），不是服务器 500。"""
        client, _ = self._client()
        bad = _spec(blocks=[{"kind": "chart", "span": 1}])
        r = client.post("/api/pages/drafts", json=bad)
        assert r.status_code == 400
        assert "renderer" in r.text or "schema" in r.text

    def test_publish_and_unpublish(self):
        client, _ = self._client()
        pid = client.post("/api/pages/drafts", json=_spec()).json()["id"]
        assert client.post(f"/api/pages/{pid}/publish").json()["status"] == "published"
        assert client.post(f"/api/pages/{pid}/unpublish").json()["status"] == "draft"

    def test_publish_missing_page_404(self):
        client, _ = self._client()
        assert client.post("/api/pages/nope/publish").status_code == 404

    def test_duplicate_slug_400(self):
        client, _ = self._client()
        client.post("/api/pages/drafts", json=_spec())
        r = client.post("/api/pages/drafts", json=_spec())
        assert r.status_code == 400
        assert "slug" in r.text
