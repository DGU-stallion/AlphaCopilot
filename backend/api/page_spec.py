"""参数化 Page Spec 契约（ADR-0007）——**契约桩，schema 已定稿，校验实现见 T45**。

承诺 B 的交互式扩展：新增展示页 = 插一条 page spec 记录（含 params + analysis_ref），
通用 PageRenderer 据 params 自动生成控件，据 blocks[].analysis_ref.fn 经白名单注册表
（alpha.registry）算出各 block 的 option。不为单个页面写组件（AGENTS 硬规则 6）。

安全（ADR-0007 决策 3）：validate_spec 必须校验每个 analysis_ref.fn 都已在
alpha.registry 注册；未注册即拒（业务层不信任 AI 建的 draft spec）。
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft7Validator, ValidationError

from alpha import registry

# 完整 page spec 的 JSON schema（校验形状；fn 白名单校验在 validate_spec 里另做）。
PAGE_SPEC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["slug", "title", "kind", "layout", "blocks"],
    "properties": {
        "id": {"type": "string"},
        "slug": {"type": "string", "pattern": "^[a-z0-9-]+$"},
        "title": {"type": "string", "minLength": 1},
        "kind": {"type": "string", "enum": ["builtin", "user"]},
        "status": {"type": "string", "enum": ["draft", "published"]},
        "layout": {"type": "string", "enum": ["grid", "stack"]},
        "params": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "type"],
                "properties": {
                    "name": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["symbol_list", "int", "float", "date_range", "str", "enum"],
                    },
                    "label": {"type": "string"},
                    "default": {},
                    "min": {"type": "number"},
                    "max": {"type": "number"},
                    "choices": {"type": "array"},
                },
            },
        },
        "blocks": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["kind"],
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["chart", "table", "markdown", "metric"],
                    },
                    "span": {"type": "integer", "minimum": 1, "maximum": 3},
                    # 三选一：analysis_ref(动态算) / artifact_id(引用产出) / text(md)
                    "analysis_ref": {
                        "type": "object",
                        "required": ["fn"],
                        "properties": {"fn": {"type": "string"}},
                    },
                    "artifact_id": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
        },
        "refresh": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["manual", "on_open", "cron"]},
                "cron": {"type": "string"},
            },
        },
    },
    "additionalProperties": True,
}


def validate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """校验 page spec：① 符合 schema ② 每个 analysis_ref.fn 已在 alpha.registry 注册。

    不符合抛 ValueError（api 层转 400，不信任 AI 建的 draft）。返回原 spec。

    安全边界（ADR-0007 决策 3）：fn 只经白名单注册表核验，不做 importlib/eval 动态解析。
    """
    try:
        Draft7Validator(PAGE_SPEC_SCHEMA).validate(spec)
    except ValidationError as e:
        raise ValueError(f"page spec 不符合 schema: {e.message}") from e

    for i, block in enumerate(spec.get("blocks", [])):
        ref = block.get("analysis_ref")
        if ref is None:
            continue
        fn = ref.get("fn")
        if not registry.is_registered(fn):
            raise ValueError(
                f"blocks[{i}].analysis_ref.fn 未注册: {fn!r}（不在 alpha.registry 白名单内）"
            )
    return spec
