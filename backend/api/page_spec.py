"""参数化 Page Spec 契约（ADR-0007）——**契约桩，schema 已定稿，校验实现见 T45**。

承诺 B 的交互式扩展：新增展示页 = 插一条 page spec 记录（含 params + analysis_ref），
通用 PageRenderer 据 params 自动生成控件，据 blocks[].analysis_ref.fn 经白名单注册表
（alpha.registry）算出各 block 的 option。不为单个页面写组件（AGENTS 硬规则 6）。

安全（ADR-0007 决策 3）：validate_spec 必须校验每个 analysis_ref.fn 都已在
alpha.registry 注册；未注册即拒（业务层不信任 AI 建的 draft spec）。

M2-7（ADR-0012 未决 1 缝合 ADR-0014 §6）：chart block 必须声明 renderer
（"lwc" | "echarts"），且必须与本文件的 RENDERER_BY_FN 白名单映射一致——
fn 与 renderer 的绑定由服务端裁决，不信任 agent/调用方自行声明。
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft7Validator, ValidationError

from alpha import registry

# ---------------------------------------------------------------------------
# fn → renderer 白名单映射（M2-7 裁决表）
#
# 判据（ADR-0014 §6 的图形分工，按「图形语义」而非「当前 payload 格式」）：
#   · lwc     —— 时间序列轨迹类：K 线 / 净值 / 回撤 / 买卖点。需要金融坐标轴、
#                时间缩放、十字光标、pane 分区（净值+回撤同实例）。
#   · echarts —— 二维聚合 / 统计对比类：热力图 / 分层 / 散点 / 归因 / 矩阵。
#
# ADR-0012「未决 1」的明确裁决：backtest.equity / backtest.drawdown 产 LWC 输入，
# correlation.* 一类产 ECharts option。逐 fn 理由：
#
#   backtest.equity      → lwc      净值曲线（含策略 vs 买入持有多条线），
#                                   金融时间序列，未来与回撤同 chart 多 pane（M2-6）。
#   backtest.drawdown    → lwc      回撤曲线，净值域内同一金融坐标语义，pane 1。
#   correlation.overlay  → echarts  多标的归一化相对强弱对比，ADR-0012 点名 ECharts
#                                   option；是统计对比而非单资产价格轨迹。
#   correlation.matrix   → echarts  相关矩阵热力图，二维聚合，LWC 无此图形。
#   correlation.rolling  → echarts  滚动相关系数（有争议，见下）：它本质是统计衍生
#                                   序列随时间变化，语义上偏时间序列；但它是两个标的
#                                   收益率的衍生统计（非价格轨迹），payload 现为
#                                   ECharts option，且与 matrix/overlay 同属相关性族
#                                   的指标轴（%格式、统计口径）。裁决为 echarts；
#                                   若未来要与净值同 pane 共享十字光标缩放再迁 lwc。
#
# 不在表里的：backtest.metrics 是 metric block（非 chart，无 renderer）；
# 未注册的 fn 根本到不了这里（registry 校验先行）。
#
# 新增 fn 的纪律：注册进 alpha.registry 时必须同时在这里登记 renderer，
# 否则引用它的 chart spec 全部拒收（见 validate_spec）。
# ---------------------------------------------------------------------------
RENDERER_LWC = "lwc"
RENDERER_ECHARTS = "echarts"
ALLOWED_RENDERERS = (RENDERER_LWC, RENDERER_ECHARTS)

RENDERER_BY_FN: dict[str, str] = {
    # LWC 语义：金融时间序列轨迹
    "backtest.equity": RENDERER_LWC,
    "backtest.drawdown": RENDERER_LWC,
    # ECharts 语义：聚合 / 统计对比
    "correlation.overlay": RENDERER_ECHARTS,
    "correlation.matrix": RENDERER_ECHARTS,
    "correlation.rolling": RENDERER_ECHARTS,
}


def renderer_for_fn(fn: str | None) -> str | None:
    """已注册 fn 的权威 renderer；未注册/未登记返回 None。"""
    if fn is None:
        return None
    return RENDERER_BY_FN.get(fn)

# 完整 page spec 的 JSON schema（校验形状；fn 白名单校验在 validate_spec 里另做）。
# M2-7：renderer 只做形状外的语义校验（值域 + 与 fn 的映射一致性），schema 不锁它，
# 因为「非 chart 不允许带 renderer」是跨 block 字段约束，jsonschema 层表达不了。
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
    """校验 page spec：① 符合 schema ② analysis_ref.fn 已注册 ③ renderer 判别符（M2-7）。

    renderer 三条规则：
      a) kind=="chart" 必须显式声明 renderer ∈ ALLOWED_RENDERERS（不能默认猜——
         猜错就是同一图形两套实现，违背 ADR-0014 图表分工）。
      b) 非 chart 块（table/markdown/metric）不允许带 renderer（防噪音字段扩散——
         agent 写入时多带字段会变成事实上的弱 schema）。
      c) chart.renderer 必须与 RENDERER_BY_FN 映射一致；fn 已注册但未进映射 → 拒，
         报错要求先登记（不默认放行，避免「没人裁决」的歧义 fn 溜进渲染层）。

    注意 c) 只对「fn 已注册」的 analysis_ref 生效；只有 artifact_id / 无 fn 的 chart
    块（agent 产物引用）仍须声明 renderer，但不做 fn 一致性校验。

    不符合抛 ValueError（api 层转 400，不信任 AI 建的 draft）。返回原 spec。

    安全边界（ADR-0007 决策 3）：fn 只经白名单注册表核验，不做 importlib/eval 动态解析。
    """
    try:
        Draft7Validator(PAGE_SPEC_SCHEMA).validate(spec)
    except ValidationError as e:
        raise ValueError(f"page spec 不符合 schema: {e.message}") from e

    for i, block in enumerate(spec.get("blocks", [])):
        ref = block.get("analysis_ref")
        fn: str | None = None
        if ref is not None:
            fn = ref.get("fn")
            if not registry.is_registered(fn):
                raise ValueError(
                    f"blocks[{i}].analysis_ref.fn 未注册: {fn!r}（不在 alpha.registry 白名单内）"
                )
        if block.get("kind") == "chart":
            renderer = block.get("renderer")
            if renderer is None:
                raise ValueError(
                    f"blocks[{i}] kind=chart 缺 renderer 判别符（必填：'lwc' | 'echarts'，"
                    "不允许默认猜；ADR-0014 §6 图表分工由服务端裁决）"
                )
            if renderer not in ALLOWED_RENDERERS:
                raise ValueError(
                    f"blocks[{i}].renderer 非法: {renderer!r}（只允许 'lwc' | 'echarts'）"
                )
            declared = RENDERER_BY_FN.get(fn) if fn else None
            if fn is not None and declared is None:
                raise ValueError(
                    f"blocks[{i}].analysis_ref.fn 已注册但未登记 renderer 映射: {fn!r}——"
                    "请先在 api.page_spec.RENDERER_BY_FN 登记，再在 spec 中引用"
                )
            if declared is not None and renderer != declared:
                raise ValueError(
                    f"blocks[{i}] renderer 与 fn 不匹配: fn={fn!r} 属 {declared!r} 语义，"
                    f"却声明了 {renderer!r}（映射见 api.page_spec.RENDERER_BY_FN）"
                )
        elif "renderer" in block and block["renderer"] is not None:
            raise ValueError(
                f"blocks[{i}] kind={block['kind']!r} 不允许带 renderer（只 chart 块有权声明）"
            )
    return spec


def normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """老 spec 读时兼容（M2-7）：chart 块缺 renderer 时按 RENDERER_BY_FN 补全。

    策略：读时补全，不写迁移脚本。理由：
      · builtin 页在每次 create_app 时幂等 upsert（spec 已含 renderer），自愈；
      · user 页/历史 draft 无法保证有序迁移（备份恢复、agent 写入跨越版本），
        一旦有读路径绕过迁移脚本，校验就会撕裂；读时补全天然幂等、覆盖一切来源，
        且写路径 validate_spec 永远要求显式声明，两者不冲突。
      · 代价：未注册 fn（os.system 等非法 spec）补不了 renderer——返回原样，
        让上层渲染按缺失处理，不做兜底猜测（默认值即裁决，不能在读路径暗改）。

    不修改传入 spec，返回浅拷贝 + 新 blocks 列表（读路径安全加固）。
    """
    blocks: list[Any] = []
    changed = False
    for block in spec.get("blocks", []):
        if block.get("kind") == "chart" and "renderer" not in block:
            ref = block.get("analysis_ref")
            r = renderer_for_fn(ref.get("fn")) if ref else None
            if r is not None:
                block = {**block, "renderer": r}
                changed = True
        blocks.append(block)
    if not changed:
        return spec
    return {**spec, "blocks": blocks}
