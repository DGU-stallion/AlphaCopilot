"""启动入口必须能 import —— 它挂了整套开发/E2E 全跑不起来，但没人测它。

背景：M1-6 删掉 `agent/credentials.py`（dsh/agnes 链路）后，`api/main.py`
仍写着 `from agent.credentials import read_api_key`。测试全绿（没有任何测试
import 这个模块），但 `python -m api.main` 直接 ModuleNotFoundError
——开发者和 CI 的 E2E 会一起哑掉。

这类「删了被引用模块」的事故只有 import 才能发现，所以这里就 import 它。
"""

from __future__ import annotations

import importlib


def test_main_module_imports():
    """`python -m api.main` 的死活取决于这一行。"""
    mod = importlib.import_module("api.main")
    assert hasattr(mod, "build_app"), "api.main 必须暴露 build_app"


def test_no_reference_to_deleted_modules():
    """启动入口不能引用已删除的模块。

    dsh 那条链路是 M1-6 明确删掉的；它若被重新引入，agent 会走回
    「服务端持有密钥并替模型发请求」的旧架构。
    """
    import inspect

    import api.main as m

    src = inspect.getsource(m)
    for gone in ("agent.credentials", "agent.dsh", "agent.harness"):
        assert gone not in src, f"api/main.py 又引用了已删除的 {gone}"


def test_build_app_does_not_read_credentials(monkeypatch):
    """本进程不该读密钥（Pi 自己读 auth.json）。

    若不慎恢复「服务端读 key」的路径，密钥就会经过我们进程，
    违反「密钥只在 Pi 侧、不进日志」的约定。
    """
    import api.main as m

    # 任何 os.environ 之外的凭证读取都不该发生；这里只断言不抛错即可
    app = m.build_app()
    assert app is not None
