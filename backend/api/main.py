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

from agent.credentials import read_api_key
from api.app import create_app

_REPO_ROOT = Path(__file__).resolve().parents[1]

# agnes 端点（openai-completions）。settings.yaml 里 baseURL 开头有字面 \t，此处已 strip。
_AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
_AGNES_MODEL = "agnes-2.5-flash"


def _resolve_model_config() -> tuple[str | None, str | None, str | None]:
    """决定 (base_url, api_key, model)。

    优先级：显式 DEEPSEEK_* env（keyless mock / 官方）> agnes（AGNES_API_KEY 可用时）> 无。
    """
    ds_base = os.environ.get("DEEPSEEK_BASE_URL")
    ds_key = os.environ.get("DEEPSEEK_API_KEY")
    if ds_base or ds_key:
        return ds_base, ds_key, os.environ.get("DEEPSEEK_MODEL")
    agnes_key = read_api_key("AGNES_API_KEY")
    if agnes_key:
        return _AGNES_BASE_URL, agnes_key, _AGNES_MODEL
    return None, None, None


def build_app():
    db = os.environ.get("ALPHACOPILOT_DB", str(_REPO_ROOT / "workspace" / "alphacopilot.db"))
    ws = Path(os.environ.get("ALPHACOPILOT_WORKSPACE", str(_REPO_ROOT / "workspace")))
    ws.mkdir(parents=True, exist_ok=True)
    base_url, api_key, model = _resolve_model_config()
    return create_app(
        db_path=db,
        workspace_root=ws,
        base_url=base_url,
        api_key=api_key,
        model=model,
    )


def main() -> None:
    uvicorn.run(build_app(), host="127.0.0.1", port=8900, log_level="info")


if __name__ == "__main__":
    main()
