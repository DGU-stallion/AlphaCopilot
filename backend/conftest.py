"""pytest 全局配置：注入 dsh SDK/runtime 路径 + 默认 node carrier（开发）。

harness 测试需要 deepseek_harness SDK 与已构建的 node 运行时闭包。SDK 未安装进
site-packages，用源码路径注入；DSH_RUNTIME_MODE=node 用系统 node carrier（开发模式）。
"""

import os
import sys
from pathlib import Path

_SDK_PATHS = [
    "/Users/a19150/Project/deepseek-harness/python/sdk/src",
    "/Users/a19150/Project/deepseek-harness/python/sdk-runtime/src",
]
for _p in _SDK_PATHS:
    if Path(_p).exists() and _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("DSH_RUNTIME_MODE", "node")
