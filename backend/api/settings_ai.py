"""AI 运行时设置（ROUND2 §13，A3）。

**能改的只有 model —— 这是唯一真的生效的设置**（`agent/providers/pi.py:202`
把它拼成 `--provider X --model Y`）。

不做 baseURL / apiKey 表单，理由（ADR-0010 + `agent/provider.py:81` 明确写着）：
PiProvider **不消费**这两个字段，端点与凭据由 Pi 自己从 `~/.pi/agent/models.json`
与 `auth.json` 读。给它们做输入框 = 让人填完无效，是「UI 撒谎」，
比不做更糟（用户会以为改了）。

模型列表从 `~/.pi/agent/models.json` **现读**，不维护代码内的白名单 ——
硬编码的模型清单一定会过期，而过期的清单会让人以为「我没有那个模型」。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# key 放在 setting 表里。用 k/v 而不是加列：设置项会增减，
# 每加一项就 ALTER TABLE 是错的（SQLite 的 ALTER 能力还很弱）。
SETTING_KEY = "ai.model"


def _models_json_path() -> Path:
    """Pi 的模型注册表位置。

    优先环境变量（测试与非常规安装用），否则 `~/.pi/agent/models.json`。
    **不要**用 `PI_CODING_AGENT_DIR` 指到项目里 —— 那会让 Pi 丢掉
    models.json/auth.json（AGENTS 反模式清单里实测记着）。
    """
    override = os.environ.get("ALPHACOPILOT_MODELS_JSON")
    if override:
        return Path(override)
    return Path.home() / ".pi" / "agent" / "models.json"


def _from_cli() -> list[dict[str, Any]]:
    """`pi --list-models` 解析（**权威来源**）。

    为什么优先用它而不是 models.json：models.json 只登记了 magpie 一个 provider
    （本机实测），而 `pi --list-models` 还会带出内置 provider（deepseek 等）。
    只读 models.json 会让界面里少掉一半可用模型，用户以为自己没有。
    实测耗时 0.27s，同步调用可接受。
    """
    exe = shutil.which("pi")
    if not exe:
        return []
    try:
        out = subprocess.run(  # noqa: S603 —— exe 来自 which，参数固定
            [exe, "--list-models"],
            capture_output=True, text=True, timeout=8, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    lines = (out.stdout or "").splitlines()
    if not lines or "provider" not in lines[0].lower():
        return []
    out_models: list[dict[str, Any]] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        provider, model = parts[0], parts[1]
        # 列顺序：provider model context max-out thinking images（后四列可能缺）
        tail = parts[2:]
        out_models.append({
            "id": f"{provider}/{model}",
            "provider": provider,
            "model": model,
            "label": f"{provider} / {model}",
            # 末列是 images（是否支持图片输入）
            "vision": len(tail) >= 4 and tail[3].lower() in ("yes", "true", "✓"),
        })
    return out_models


def available_models() -> list[dict[str, Any]]:
    """列出 Pi 已注册的模型 → [{id, provider, model, label, vision}]。

    两条来源按优先级尝试：`pi --list-models`（权威、含内置 provider）→
    解析 `models.json`（`pi` 不在 PATH 时的兜底）。都失败返回 `[]`，
    让界面显示「读不到模型清单」而不是 500 —— 这个端点失败不该让整页崩。
    """
    cli = _from_cli()
    if cli:
        return cli
    return _from_json()


def _from_json() -> list[dict[str, Any]]:
    """解析 `~/.pi/agent/models.json`（兜底路径）。"""
    path = _models_json_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    providers = raw.get("providers") if isinstance(raw, dict) else None
    if not isinstance(providers, dict):
        return []

    out: list[dict[str, Any]] = []
    for pname, pcfg in providers.items():
        if not isinstance(pcfg, dict):
            continue
        models = pcfg.get("models")
        if isinstance(models, dict):
            # 形态 A：{"models": {"<id>": {...}}}
            items = [(mid, cfg or {}) for mid, cfg in models.items()]
        elif isinstance(models, list):
            # 形态 B：{"models": [{"id": "..."}]}
            items = [
                (m.get("id") or m.get("name") or "", m)
                for m in models
                if isinstance(m, dict)
            ]
        else:
            items = []
        for mid, cfg in items:
            if not isinstance(mid, str) or not mid:
                continue
            mod_id = f"{pname}/{mid}"
            has = isinstance(cfg, dict)
            out.append({
                "id": mod_id,
                "provider": pname,
                # model 段保留原样（可能自身含斜线，如 commandcode-plan/z-ai/xxx）
                "model": mid,
                "label": (cfg.get("name") or mod_id) if has else mod_id,
                "vision": bool(cfg.get("vision") or cfg.get("supportsVision")) if has else False,
            })
    out.sort(key=lambda d: (d["provider"], d["model"]))
    return out


def resolve_model(store: Any, fallback: str | None = None) -> str | None:
    """本次会话该用哪个模型：setting 表优先，其次进程启动时的环境变量。

    为什么不是「改了就重建 SessionManager」：那样改了要重启后端，
    而「换个模型试试」是高频操作 —— 只有新建会话时读一次才算真能改。
    """
    try:
        saved = store.settings.get(SETTING_KEY, "")
    except Exception:  # noqa: BLE001 —— 设置读失败不该拦住建会话
        saved = ""
    return saved or fallback


class ModelIn(BaseModel):
    model: str


def build_settings_router(store: Any) -> APIRouter:
    """AI 设置路由（A3）。

      GET /api/settings/ai  -> {current, options:[...]}
      PUT /api/settings/ai  -> {current}   # body: {model: "provider/model"}
    """
    router = APIRouter(prefix="/api")

    @router.get("/settings/ai")
    def get_ai_settings() -> dict:
        options = available_models()
        current = resolve_model(store, "") or ""
        # 存过但清单里没有（模型下线/改了名）→ 仍然回显，同时如实标注
        # `known: false`，让前端能提示「当前模型不在清单里」。静默换成第一个
        # 是最糟的：用户以为还是自己选的那个。
        known = any(o["id"] == current for o in options) if current else False
        return {"current": current, "known": known, "options": options}

    @router.put("/settings/ai")
    def set_ai_settings(body: ModelIn) -> dict:
        model = (body.model or "").strip()
        if not model:
            raise HTTPException(400, "model 不能为空")
        # 只允许选清单里存在的模型：否则 Pi 启动会报 Model not found，
        # 而错误发生在**下一次聊天**，用户完全联想不到是这里选错的。
        ids = {o["id"] for o in available_models()}
        if ids and model not in ids:
            raise HTTPException(400, f"模型不在注册表里：{model}")
        store.settings.set(SETTING_KEY, model)
        return {"current": model}

    return router
