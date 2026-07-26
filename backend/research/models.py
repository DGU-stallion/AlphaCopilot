"""Shared Pydantic models for research route handlers."""

from __future__ import annotations

from pydantic import BaseModel


class LLMConfig(BaseModel):
    provider: str = ""
    baseURL: str = ""
    apiKey: str = ""
    model: str


class ChatReq(BaseModel):
    messages: list[dict]
    context: str = ""
    llm: LLMConfig


class HoldingIn(BaseModel):
    code: str
    shares: float
    cost: float


class CloseIn(BaseModel):
    code: str
    date: str
    price: float
    shares: float
    cost: float


class ReportIn(BaseModel):
    name: str
    content_b64: str
