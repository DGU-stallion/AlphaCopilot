"""M3-V5 vendor 桥：后端起子进程调 data-service 的 venv 执行 vendor 能力。

## 为什么是子进程

两个环境必须隔离（有实测证据）：
  - vendor 依赖 `mootdx` → `httpx<0.26`
  - 主环境 `mcp>=1.9` → `httpx>=0.27`
区间不相交，同一个解释器里装不下。子进程是唯一不打架的接法。

代价是每次调用一个进程。但取数本身就是网络 IO（几十到几百 ms），
进程启动（~30ms）不是瓶颈。相比之下，「为了省 30ms 而把依赖冲突塞回主环境」
是更贵的错误。

## 契约

后端 → 子进程：JSON over stdin `{"name": "...", "args": [...], "kwargs": {...}}`
子进程 → 后端：JSON over stdout `{"ok": true, "result": ...}` 或 `{"ok": false, "error": "..."}`

**错误必须走 JSON 而不是靠退出码**：退出码只有一个数字，
「缺 mootdx」「参数错」「数据源不可用」区分不开，上层就没法决定是降级还是报错。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

DATA_SERVICE = BACKEND.parent / "data-service"


class TestVendorRunner:
    def test_exists_checks_data_service(self):
        """data-service 不存在时必须明确报「未安装」，而不是 ImportError。"""
        from alpha.vendor_bridge import VendorBridge
        b = VendorBridge(data_service=Path("/nonexistent-xyz"))
        assert b.available() is False

    def test_real_data_service_is_available(self):
        from alpha.vendor_bridge import VendorBridge
        b = VendorBridge(data_service=DATA_SERVICE)
        assert b.available() is True, f"data-service 未就绪：{DATA_SERVICE}"

    def test_list_capabilities_via_subprocess(self):
        """真实跨进程调用：拿到 100 个左右的能力清单。"""
        from alpha.vendor_bridge import VendorBridge
        b = VendorBridge(data_service=DATA_SERVICE)
        caps = b.capabilities()
        assert isinstance(caps, list) and len(caps) > 50
        assert all({"name", "doc"} <= set(c) for c in caps[:5])

    def test_invoke_unknown_capability_raises_with_reason(self):
        """调不存在的能力要抛带原因的错，不是返回 None。"""
        from alpha.vendor_bridge import VendorBridge, VendorError
        b = VendorBridge(data_service=DATA_SERVICE)
        with pytest.raises(VendorError) as ei:
            b.invoke("definitely_not_a_real_function_xyz", args=[])
        # 错误信息里要有函数名，否则排查时不知道调错了什么
        assert "definitely_not_a_real_function_xyz" in str(ei.value)

    def test_invoke_rejects_private_names(self):
        """以 _ 开头的内部函数不暴露 —— 它们不是能力入口。"""
        from alpha.vendor_bridge import VendorBridge, VendorError
        b = VendorBridge(data_service=DATA_SERVICE)
        with pytest.raises(VendorError):
            b.invoke("_defs_only", args=[])


class TestWorkerContract:
    """worker 脚本本身的契约（不依赖网络）。"""

    def _run_worker(self, payload: dict) -> dict:
        proc = subprocess.run(
            [str(DATA_SERVICE / ".venv" / "bin" / "python"),
             str(DATA_SERVICE / "src" / "worker.py")],
            input=json.dumps(payload),
            capture_output=True, text=True, timeout=120,
        )
        # stdout 必须是**纯 JSON**（vendor 里有 print 会污染 stdout —— 见 worker 注释）
        return json.loads(proc.stdout)

    def test_list_action(self):
        out = self._run_worker({"action": "list"})
        assert out["ok"] is True
        assert isinstance(out["result"], list)

    def test_bad_json_input_returns_error_not_crash(self):
        proc = subprocess.run(
            [str(DATA_SERVICE / ".venv" / "bin" / "python"),
             str(DATA_SERVICE / "src" / "worker.py")],
            input="not json at all",
            capture_output=True, text=True, timeout=120,
        )
        out = json.loads(proc.stdout)
        assert out["ok"] is False
        assert "error" in out

    def test_unknown_action(self):
        out = self._run_worker({"action": "nonsense"})
        assert out["ok"] is False


class TestVendorRouter:
    """REST 层的错误语义必须能区分「环境没装」「调错了」「上游挂了」。"""

    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from alpha.vendor_bridge import VendorBridge
        from api.vendor import build_vendor_router

        app = FastAPI()
        app.include_router(build_vendor_router(VendorBridge(data_service=DATA_SERVICE)))
        return TestClient(app)

    def test_capabilities_ok(self):
        r = self._client().get("/api/v1/capabilities")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] > 50
        assert isinstance(body["capabilities"], list)

    def test_invoke_unknown_is_400_not_502(self):
        """调错函数名是**调用方**的错（400），不是上游挂了（502）。"""
        r = self._client().post("/api/v1/invoke", json={"name": "no_such_thing_xyz"})
        assert r.status_code == 400

    def test_invoke_private_is_400(self):
        r = self._client().post("/api/v1/invoke", json={"name": "_defs_only"})
        assert r.status_code == 400

    def test_not_ready_is_503_not_empty_list(self):
        """没装 vendor 时必须 503。空清单会被 agent 理解成「什么都不能做」。"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from alpha.vendor_bridge import VendorBridge
        from api.vendor import build_vendor_router

        app = FastAPI()
        app.include_router(build_vendor_router(VendorBridge(data_service=Path("/nonexistent-xyz"))))
        c = TestClient(app)
        assert c.get("/api/v1/capabilities").status_code == 503
        assert c.post("/api/v1/invoke", json={"name": "x"}).status_code == 503


class TestSilentEmptyResults:
    """静默返回空 → 调用方会以为「真没数据」→ 自己去编。

    本项目已经栽过一次（取数失败静默返回空 → 模型造出 r=0.7716）。
    所以「参数传错」必须报错，不能给一个看起来像「查询成功但无结果」的空值。
    """

    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from alpha.vendor_bridge import VendorBridge
        from api.vendor import build_vendor_router

        app = FastAPI()
        app.include_router(build_vendor_router(VendorBridge(data_service=DATA_SERVICE)))
        return TestClient(app)

    def test_wrong_arg_name_is_400(self):
        """参数名写错（codes → code）要报错，不能静默空。"""
        r = self._client().post(
            "/api/v1/invoke",
            json={"name": "tencent_quote", "kwargs": {"code": ["600519"]}},
        )
        assert r.status_code == 400, r.text
        assert "tencent_quote" in r.text or "参数" in r.text

    def test_missing_required_arg_is_400(self):
        r = self._client().post("/api/v1/invoke", json={"name": "tencent_quote", "kwargs": {}})
        assert r.status_code == 400, r.text
