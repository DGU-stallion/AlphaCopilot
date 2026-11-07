"""OpenAPI schema 可生成性测试（M0-3）。

背景：`/openapi.json` 曾返回 500，根因是 `api/app.py` 在**函数体内**定义
`class BacktestIn(BaseModel)`，导致 Pydantic 无法解析其 ForwardRef。

为什么值得一条测试：OpenAPI schema 是 FastAPI 的**公开产物**——前端 codegen、
Swagger UI、以及任何按 schema 生成的客户端都依赖它。它坏掉不会让任何业务
端点变红，只会让工具链静默失效，所以必须在 CI 里显式盯住。

seam：`create_app()` 返回的 FastAPI 实例的 `/openapi.json` 端点。
这是公开接口，不依赖任何内部实现细节——无论 `BacktestIn` 被挪到哪里，
只要 schema 能生成，测试就绿。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=":memory:", workspace_root=tmp_path)
    with TestClient(app) as c:
        yield c


def test_openapi_schema_is_generated(client):
    """schema 必须能生成，否则整个工具链（Swagger/codegen）失效。"""
    r = client.get("/openapi.json")

    assert r.status_code == 200, (
        f"/openapi.json 返回 {r.status_code}，schema 生成失败。"
        f"常见根因：在函数体内定义 BaseModel 子类。body={r.text[:500]}"
    )
    body = r.json()
    assert body.get("openapi"), "响应不像 OpenAPI 文档（缺 openapi 版本字段）"
    assert body.get("paths"), "paths 为空，schema 未收集到任何路由"


def test_openapi_documents_backtest_job_endpoint(client):
    """`/api/jobs/backtest` 及其请求体必须在 schema 里出现。

    这条锁住原 bug 的具体位置：`BacktestIn` 曾经因为是函数内定义的局部类，
    既让 schema 生成失败，又无法被文档化。断言它出现在 components 里，
    就等于断言「它已经是一个模块级、可被解析的模型」。
    """
    schema = client.get("/openapi.json").json()

    assert "/api/jobs/backtest" in schema["paths"], (
        f"schema 里没有 /api/jobs/backtest，实际路径：{sorted(schema['paths'])[:20]}"
    )

    post = schema["paths"]["/api/jobs/backtest"]["post"]
    # 请求体应当引用 components.schemas 里的某个模型，而不是内联的空 object
    schema_ref = post["requestBody"]["content"]["application/json"]["schema"]
    assert "$ref" in schema_ref, f"请求体未被文档化为具名模型，实际：{schema_ref}"

    model_name = schema_ref["$ref"].rsplit("/", 1)[-1]
    assert model_name in schema["components"]["schemas"], (
        f"$ref 指向的 {model_name} 不在 components.schemas 里，实际："
        f"{sorted(schema['components']['schemas'])}"
    )

    props = schema["components"]["schemas"][model_name]["properties"]
    # 字段名来自 BacktestIn 的定义；用途是确认这个模型就是它，而不是同名巧合
    assert {"closes", "fast", "slow"} <= set(props), f"字段不符，实际：{sorted(props)}"
