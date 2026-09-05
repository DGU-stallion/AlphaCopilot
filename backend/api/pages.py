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
from api.store import Store


class CreatePageIn(BaseModel):
    spec: dict[str, Any]
    kind: str = "user"


def _render_block(block: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """算单个 block 的渲染结果。markdown 直接回 text；analysis_ref 经白名单算 option。"""
    out: dict[str, Any] = {"kind": block["kind"], "span": block.get("span", 1)}
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

    @router.get("/pages/{slug}")
    def get_page(slug: str) -> dict:
        page = store.pages.get_page_by_slug(slug)
        if page is None:
            raise HTTPException(404, "page not found")
        return page

    @router.post("/pages")
    def create_page(body: CreatePageIn) -> dict:
        try:
            pid = store.pages.create_page_from_spec(body.spec, kind=body.kind)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"page_id": pid}

    @router.post("/pages/{slug}/render")
    def render_page(slug: str, values: dict[str, Any]) -> dict:
        page = store.pages.get_page_by_slug(slug)
        if page is None:
            raise HTTPException(404, "page not found")
        try:
            blocks = [_render_block(b, values) for b in page["spec"].get("blocks", [])]
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
