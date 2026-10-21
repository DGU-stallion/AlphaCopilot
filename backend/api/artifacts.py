"""Artifact 入库与投递（T34，业务层）。

架构边界（AGENTS 硬规则 3）：agent 不直接写库。它把产出写到 workspace/runs/<run_id>/
（含 manifest.json），业务层**校验后**落库。这里不信任 agent 输出：非法 manifest 被拒。

manifest.json 契约（PLAN §三契约）：
  {
    "run_id": "...",
    "artifacts": [{"id","kind","title","path","inputs"(可选),"created_at"(可选)}],
    "code_ref": "code.py",
    "session_id": "...", "message_id": "..."
  }

校验：JSON 合法 + 必填字段 + kind 合法 + path 存在于 run_dir 内（防目录穿越）+
chart 类 payload 可 JSON 反序列化且不超限。通过后逐条 store.add_artifact + attach 到消息。

## provenance 与盖章权（ADR-0012「已决 1」）

每个 artifact **必须**带 provenance，且 `kind = "deterministic"` 的章只能由**服务端**
铸造（`ingest_run(..., server_stamped=True)`，只有业务层自己算出的产物才走这条路）。

agent 交来的 manifest 里若声称 deterministic，一律**降级为 agent** 并记下
`claimedKind`。理由：agent 有 bash，可以自己算夏普而不经 `alpha.registry`，
事后 review 抓不到，而「这段代码算不算绕开库函数」写不成规则。
所以执法点后移到产物上：自己算的数字照样能显示，但必须挂 AI 角标。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.store import Store

_ALLOWED_KINDS = {"chart", "table", "markdown", "metric", "image"}
_MAX_PAYLOAD_BYTES = 2_000_000  # 单个 artifact 内联/文件上限（2MB）


class ManifestError(ValueError):
    """manifest 校验失败（业务层拒绝不可信的 agent 产出）。"""


def _validate_manifest(manifest: Any, run_dir: Path) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ManifestError("manifest 必须是对象")
    arts = manifest.get("artifacts")
    if not isinstance(arts, list) or not arts:
        raise ManifestError("manifest.artifacts 必须是非空数组")
    for i, a in enumerate(arts):
        if not isinstance(a, dict):
            raise ManifestError(f"artifacts[{i}] 必须是对象")
        kind = a.get("kind")
        if kind not in _ALLOWED_KINDS:
            raise ManifestError(f"artifacts[{i}].kind 非法: {kind!r}")
        path = a.get("path")
        if not isinstance(path, str) or not path:
            raise ManifestError(f"artifacts[{i}].path 缺失")
        # 防目录穿越：path 必须解析在 run_dir 内。
        resolved = (run_dir / path).resolve()
        if not str(resolved).startswith(str(run_dir.resolve())):
            raise ManifestError(f"artifacts[{i}].path 越界: {path!r}")
        if not resolved.exists():
            raise ManifestError(f"artifacts[{i}].path 文件不存在: {path!r}")
        if resolved.stat().st_size > _MAX_PAYLOAD_BYTES:
            raise ManifestError(f"artifacts[{i}] 超过大小上限")
    return manifest


_ALLOWED_PROVENANCE_KINDS = {"deterministic", "agent"}


def _validate_provenance(raw: Any, index: int) -> dict[str, Any]:
    """校验 provenance 形状。缺失/空/kind 非法一律拒收。"""
    if not isinstance(raw, dict) or not raw:
        raise ManifestError(
            f"artifacts[{index}].provenance 缺失或为空。"
            "每个 artifact 必须声明 provenance（ADR-0012 §1，唯一硬约束）"
        )
    kind = raw.get("kind")
    if kind not in _ALLOWED_PROVENANCE_KINDS:
        raise ManifestError(
            f"artifacts[{index}].provenance.kind 非法: {kind!r}；"
            f"只允许 {sorted(_ALLOWED_PROVENANCE_KINDS)}"
        )
    return dict(raw)


def _stamp_provenance(raw: dict[str, Any], *, server_stamped: bool) -> dict[str, Any]:
    """盖章：决定这条 artifact 的 provenance 最终是什么。

    **这是「盖章权」的唯一实现点。** 规则只有一句：
    `deterministic` 只能由服务端铸造，agent 无权自称。

    - `server_stamped=True`：服务端自己调 `alpha.registry` 算出来的产物。
      保留 deterministic，但要求带 `fn` + `dataAsOf`（否则「可复现」这句话是空的）。
    - 否则（agent 交来的 manifest）：无论它写什么，一律改成 `agent`，
      并记下 `claimedKind` 便于事后审计「有多少 agent 在试图自称可信」。
    """
    kind = raw["kind"]

    if server_stamped and kind == "deterministic":
        fn = raw.get("fn")
        if not isinstance(fn, str) or not fn:
            raise ManifestError("deterministic provenance 必须带 fn（调用了哪个注册函数）")
        if not raw.get("dataAsOf"):
            raise ManifestError("deterministic provenance 必须带 dataAsOf（数据截止时点）")
        return raw

    if server_stamped and kind == "agent":
        return raw

    # ---- agent 交来的一切：不采信其声明 ----
    stamped = dict(raw)
    stamped["kind"] = "agent"
    if kind != "agent":
        stamped["claimedKind"] = kind
    return stamped


def _load_payload(kind: str, file_path: Path) -> Any:
    """chart 内联为 JSON（前端 setOption 直接用）；其余不内联（走 path 读取）。"""
    if kind == "chart":
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ManifestError(f"chart artifact 不是合法 JSON: {e}") from e
    return None


def ingest_run(
    store: Store,
    run_dir: str | Path,
    message_id: str,
    *,
    server_stamped: bool = False,
) -> list[str]:
    """读取 run_dir/manifest.json，校验后把 artifacts 落库并挂到 message_id。

    `server_stamped=True` 是**服务端铸造确定性产物**的唯一入口 —— 只有业务层
    自己调过 `alpha.registry` 里函数时才能传。默认 False 表示「这是 agent 交来的」，
    其 provenance 中的 deterministic 会被降级（见 `_stamp_provenance`）。

    返回创建的 artifact id 列表。manifest 非法 → 抛 ManifestError（不落任何库）。
    """
    run_dir = Path(run_dir)
    manifest_file = run_dir / "manifest.json"
    if not manifest_file.exists():
        raise ManifestError("run_dir 下无 manifest.json")
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ManifestError(f"manifest.json 不是合法 JSON: {e}") from e

    manifest = _validate_manifest(manifest, run_dir)
    run_id = manifest.get("run_id") or run_dir.name

    # 先校验全部 provenance 再落库：避免「前几条已入库、后一条非法」的半成品状态。
    provenances = [
        _stamp_provenance(_validate_provenance(a.get("provenance"), i), 
                          server_stamped=server_stamped)
        for i, a in enumerate(manifest["artifacts"])
    ]

    created: list[str] = []
    for a, provenance in zip(manifest["artifacts"], provenances, strict=True):
        kind = a["kind"]
        file_path = (run_dir / a["path"]).resolve()
        payload = _load_payload(kind, file_path)
        aid = store.add_artifact(
            run_id=run_id,
            kind=kind,
            path=str(file_path),
            message_id=message_id,
            title=a.get("title", ""),
            payload=payload,
            inputs=a.get("inputs"),
            provenance=provenance,
        )
        created.append(aid)
    return created
