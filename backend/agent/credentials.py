"""凭据读取 —— AGNES_API_KEY（T42）。

优先级：环境变量 > ~/.dsh/.credentials.yaml。
密钥值只返回给调用方（provider 注入子进程 env），**不写入文件、不进日志、不进仓库**。
credentials.yaml 是 `KEY: value` 的扁平 YAML；这里用最小行解析，不引 pyyaml 依赖。
"""

from __future__ import annotations

import os
from pathlib import Path

_CREDENTIALS_PATH = Path.home() / ".dsh" / ".credentials.yaml"


def read_api_key(env_var: str, credentials_path: Path | None = None) -> str | None:
    """按 env_var 名取密钥：先查环境变量，再查 ~/.dsh/.credentials.yaml 里同名键。

    返回 None 表示两处都没有；调用方决定如何处理缺失。不记录密钥值。
    """
    val = os.environ.get(env_var)
    if val:
        return val.strip()
    path = credentials_path or _CREDENTIALS_PATH
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        if key.strip() == env_var:
            secret = raw.strip().strip('"').strip("'")
            return secret or None
    return None
