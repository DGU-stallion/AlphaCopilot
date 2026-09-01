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


def _load_payload(kind: str, file_path: Path) -> Any:
    """chart 内联为 JSON（前端 setOption 直接用）；其余不内联（走 path 读取）。"""
    if kind == "chart":
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ManifestError(f"chart artifact 不是合法 JSON: {e}") from e
    return None


def ingest_run(store: Store, run_dir: str | Path, message_id: str) -> list[str]:
    """读取 run_dir/manifest.json，校验后把 artifacts 落库并挂到 message_id。

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

    created: list[str] = []
    for a in manifest["artifacts"]:
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
        )
        created.append(aid)
    return created
