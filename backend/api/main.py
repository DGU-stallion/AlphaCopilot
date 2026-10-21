"""开发/E2E 启动入口：uvicorn 起 FastAPI（127.0.0.1:8900）。

环境变量：
  ALPHACOPILOT_DB          SQLite 路径（默认 workspace/alphacopilot.db）
  ALPHACOPILOT_WORKSPACE   workspace 根（默认 <repo>/workspace）
  ALPHACOPILOT_MODEL       模型 id（形如 provider/model，Pi 侧拆开传）
  ALPHACOPILOT_BASE_URL    模型端点（可选；Pi 走自己的 models.json 时不必填）
  ALPHACOPILOT_API_KEY     模型 key（可选；同上）

用法：
  python -m api.main

密钥从哪来：Pi 自己读 `~/.pi/agent/auth.json`。本进程**不碰密钥**——
M1-6 删掉 dsh/agnes 那条链路后，这里不再有任何读凭证的代码。
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from api.app import create_app

_REPO_ROOT = Path(__file__).resolve().parents[1]


def build_app():
    db = os.environ.get("ALPHACOPILOT_DB", str(_REPO_ROOT / "workspace" / "alphacopilot.db"))
    ws = Path(os.environ.get("ALPHACOPILOT_WORKSPACE", str(_REPO_ROOT / "workspace")))
    ws.mkdir(parents=True, exist_ok=True)
    return create_app(
        db_path=db,
        workspace_root=ws,
        base_url=os.environ.get("ALPHACOPILOT_BASE_URL"),
        api_key=os.environ.get("ALPHACOPILOT_API_KEY"),
        model=os.environ.get("ALPHACOPILOT_MODEL"),
    )


def main() -> None:
    uvicorn.run(build_app(), host="127.0.0.1", port=8900, log_level="info")


if __name__ == "__main__":
    main()
