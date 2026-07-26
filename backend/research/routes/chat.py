"""Chat route sub-module — /chat endpoint."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from research.caches import ResearchCaches
from research.models import ChatReq

import research.chat as chat_layer
import research.cli_runtime as cli_runtime


def register_chat_routes(router: APIRouter, *, caches: ResearchCaches) -> None:
    """Attach chat endpoints to the given router."""

    @router.post("/chat")
    def chat(req: ChatReq):
        """系统 AI 对话，流式 NDJSON。"""
        if not req.messages:
            raise HTTPException(400, "messages 不能为空")
        if not req.llm.model:
            raise HTTPException(400, "缺少模型配置，请先在「接入 AI」里选择")

        is_cli = req.llm.provider.startswith("cli-")
        if is_cli:
            kind = req.llm.provider[4:]
            if not cli_runtime.detect_cli(kind):
                raise HTTPException(
                    400,
                    f"未检测到「{kind}」对应的本机命令。请先安装并登录该 CLI，或改用「API 接入」。",
                )
        elif not req.llm.apiKey or not req.llm.baseURL:
            raise HTTPException(400, "缺少 Base URL 或 API Key，请先在「接入 AI」里填写")

        cfg = req.llm.model_dump()

        def gen():
            try:
                events = (
                    chat_layer.run_chat_cli_stream if is_cli else chat_layer.run_chat_stream
                )(cfg, req.messages, req.context)
                for ev in events:
                    yield json.dumps(ev, ensure_ascii=False) + "\n"
            except Exception as e:
                yield json.dumps(
                    {"type": "error", "message": f"对话失败：{e}"}, ensure_ascii=False
                ) + "\n"

        return StreamingResponse(gen(), media_type="application/x-ndjson")
