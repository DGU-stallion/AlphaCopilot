"""展示页 REST（T45，ADR-0007 承诺 B）——工具层零业务逻辑。

四个端点，挂在 /api 下（与会话接口同风格）：
  GET  /api/pages                 -> list_pages()
  GET  /api/pages/{slug}          -> get_page_by_slug，404 若无
  POST /api/pages                 -> create_page_from_spec（validate_spec 抛 ValueError → 400）
  POST /api/pages/{slug}/render   -> 按参数值算各 block 的 option JSON

render 安全边界（ADR-0007 决策 3）：block.analysis_ref.fn 只经 alpha.registry 白名单
解析（registry.get，未注册抛 KeyError → 400）；参数值经该 fn 声明的 ParamSpec 校验
（缺失取 default，越界/类型错抛 ValueError → 400）。禁止 importlib/eval 动态解析。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alpha import registry
from api.page_spec import normalize_spec
from api.store import Store


class CreatePageIn(BaseModel):
    spec: dict[str, Any]
    kind: str = "user"


def _render_block(block: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """算单个 block 的渲染结果。markdown 直接回 text；analysis_ref 经白名单算 option。

    M2-7：chart 块回传 renderer 判别符，前端据此分派 LWC / ECharts 渲染
    （ADR-0012 未决 1；renderer 由 spec 校验层保证与 fn 语义匹配）。
    """
    out: dict[str, Any] = {"kind": block["kind"], "span": block.get("span", 1)}
    if block.get("kind") == "chart" and "renderer" in block:
        out["renderer"] = block["renderer"]
    ref = block.get("analysis_ref")
    if ref is None:
        # markdown / 引用型 block：无动态计算，回传声明的 text（若有）。
        if "text" in block:
            out["text"] = block["text"]
        return out
    try:
        reg = registry.get(ref["fn"])
    except KeyError as e:
        raise HTTPException(400, f"未注册的分析函数: {ref['fn']!r}") from e
    kwargs: dict[str, Any] = {}
    for p in reg.params:
        raw = values.get(p.name, p.default)
        try:
            kwargs[p.name] = p.coerce(raw)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    result = reg.fn(**kwargs)
    # 按 block.kind 映射分析结果的形状：
    #   markdown -> {text}；table -> {columns, rows}；metric -> {items}；其它 -> ECharts option。
    kind = block["kind"]
    if kind == "markdown" and isinstance(result, dict) and "text" in result:
        out["text"] = result["text"]
    elif kind == "table" and isinstance(result, dict):
        out["table"] = result
    elif kind == "metric" and isinstance(result, dict):
        out["metric"] = result
    else:
        out["option"] = result
        # renderer=lwc 时**额外**产出时间序列（ADR-0014 §6）：前端 LWC 直接吃
        # {time,value}，不用反解 ECharts option。option 仍保留给 ECharts 消费方，
        # 两条路并存但数据只有一个来源（同一份 result）。
        if out.get("renderer") == "lwc":
            from alpha.lwc import lwc_payload
            from api.page_spec import wants_drawdown

            # 回撤**按 fn 白名单**决定要不要算（DRAWDOWN_FNS）。
            # 曾默认对每条时间序列都算，导致同一屏两份回撤：净值图自带一份，
            # 后面的 backtest.drawdown 块又画一份（截图发现）。
            fn = (ref or {}).get("fn")
            out["lwc"] = lwc_payload(result, with_drawdown=wants_drawdown(fn))
    if isinstance(result, dict) and "title" in result and kind != "markdown":
        # block.title 是给前端 <h3> 的展示字符串；chart helper 里 title 是 ECharts
        # 结构 {"text": ...}，这里取其 text，避免把对象塞进 title 让 React 渲染时崩溃。
        t = result["title"]
        out.setdefault("title", t.get("text", "") if isinstance(t, dict) else t)
    return out


def build_pages_router(store: Store) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/pages")
    def list_pages() -> list:
        return store.list_pages()

    # 注：M5-2 的 Build 模式（POST /pages/drafts、/pages/{pid}/publish、
    # /unpublish）已于 ROUND2-B1 删除。原因：前端从来没有渲染 published
    # page 的路由 —— 发布只写库，用户永远看不见，整个链路是空转的。
    # 用户决策「固定图表不如直接改代码」，故删页不补路由（ROUND2-BRIEF §3）。

    @router.get("/pages/{slug}")
    def get_page(slug: str) -> dict:
        page = store.pages.get_page_by_slug(slug)
        if page is None:
            raise HTTPException(404, "page not found")
        # M2-7：读时按 fn 映射补全老 spec 缺失的 renderer（不写迁移脚本，见 normalize_spec）。
        page["spec"] = normalize_spec(page["spec"])
        return page

    @router.post("/pages")
    def create_page(body: CreatePageIn) -> dict:
        try:
            pid = store.pages.create_page_from_spec(body.spec, kind=body.kind)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"page_id": pid}

    @router.delete("/pages/{pid}")
    def delete_page(pid: str) -> dict:
        """删一个自定义页。

        为什么必须有：ADR-0016 之后建一个页面的成本极低（agent 一条 POST），
        没有删除就等于只增不减，实验页会永久占着导航栏。

        内置页（kind=builtin）拒删：它们由 `register_builtin_pages` 在每次
        create_app 时幂等 upsert，删了下次启动就会重新出现。
        允许删只会让用户看到「删了又回来了」的诡异行为。
        """
        page = store.pages.get_page(pid)
        if page is None:
            raise HTTPException(404, f"page not found: {pid}")
        if page.get("kind") == "builtin":
            raise HTTPException(
                400,
                f"不能删内置页 {page['slug']!r}（它会在下次启动时自动重建）；"
                "若不想看到它，请从导航隐藏而不是删除",
            )
        if not store.pages.delete_page(pid):
            raise HTTPException(404, f"page not found: {pid}")
        return {"ok": True, "id": pid, "soft": True}

    @router.post("/pages/{pid}/restore")
    def restore_page(pid: str) -> dict:
        """恢复软删的页（ROUND2 §9 事故后补）。

        为什么需要：删除曾经是**硬删除 + 无确认框**，理由是「页面内容是 spec，
        可再生」。那个理由是错的 —— 实际造成一个用户手写的页被删后不可恢复。

        409 = 删除后已有人建了同名 slug（URL 不能对应两个页）。
        """
        ok, reason = store.pages.restore_page(pid)
        if not ok:
            if reason == "not found":
                raise HTTPException(404, f"page not found: {pid}")
            raise HTTPException(409, reason)
        return {"ok": True, "id": pid}

    @router.post("/pages/{slug}/render")
    def render_page(slug: str, values: dict[str, Any]) -> dict:
        page = store.pages.get_page_by_slug(slug)
        if page is None:
            raise HTTPException(404, "page not found")
        try:
            # M2-7：render 前 normalize，老 spec 缺 renderer 也按映射补全后回传。
            blocks = [_render_block(b, values)
                      for b in normalize_spec(page["spec"]).get("blocks", [])]
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            # analysis fn 内部失败（最常见：底层行情数据源不可达）。不暴露为 500，
            # 回 503 + 清晰信息，让前端提示「数据源暂不可用」而非崩溃。
            raise HTTPException(
                503, f"分析计算失败（数据源可能暂不可用）: {type(e).__name__}: {e}"
            ) from e
        return {"blocks": blocks}

    return router
