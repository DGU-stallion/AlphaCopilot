"""开发/E2E 启动入口：uvicorn 起 FastAPI（127.0.0.1:8900）。

环境变量：
  ALPHACOPILOT_DB          SQLite 路径（默认 workspace/alphacopilot.db）
  ALPHACOPILOT_WORKSPACE   workspace 根（默认 <repo>/workspace）
  DEEPSEEK_BASE_URL        模型端点（keyless mock 时指向 mock /v1）
  DEEPSEEK_API_KEY         模型 key（keyless 时任意占位）

用法：
  python -m api.main
  # keyless E2E：先起 mock /v1，再
  DEEPSEEK_BASE_URL=http://127.0.0.1:PORT/v1 DEEPSEEK_API_KEY=sk-mock python -m api.main
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
        base_url=os.environ.get("DEEPSEEK_BASE_URL"),
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
    )


def main() -> None:
    uvicorn.run(build_app(), host="127.0.0.1", port=8900, log_level="info")


if __name__ == "__main__":
    main()
