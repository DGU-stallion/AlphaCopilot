"""后端侧的 vendor 桥（M3-V5）：起子进程调用 data-service 的 venv。

**为什么是子进程而不是 import**：两个环境的 httpx 版本区间不相交
（vendor 的 mootdx 要 <0.26，主环境 mcp 要 >=0.27），同一个解释器装不下。
这个限制有实测证据，见 data-service/README.md 与 AGENTS 的 M3-V1 说明。

**为什么错误走 JSON 而不是退出码**：一个数字区分不了
「缺 mootdx」「参数错」「数据源不可用」，上层就没法决定降级还是报错。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

# data-service 相对仓库根的位置（backend/alpha/vendor_bridge.py → 仓库根 → data-service）
DEFAULT_DATA_SERVICE = Path(__file__).resolve().parents[2] / "data-service"

# 单次调用的超时。取数可能慢（上游要抓交易所文件），但不能无限等 ——
# 卡死的子进程会把后端线程池占满。
DEFAULT_TIMEOUT_S = 120


class VendorError(RuntimeError):
    """vendor 调用失败。消息里必须带足够定位问题的信息（函数名 / 原始异常类型）。"""


class VendorBridge:
    def __init__(
        self,
        data_service: Path | str = DEFAULT_DATA_SERVICE,
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.data_service = Path(data_service)
        self.timeout_s = timeout_s
        self._python = self.data_service / ".venv" / "bin" / "python"
        self._worker = self.data_service / "src" / "worker.py"

    def available(self) -> bool:
        """data-service 是否已就绪（venv + worker 都在）。

        不抛错、只返回 bool：调用方（比如 API 层）可能想在服务不可用时
        优雅降级（页面照常用 curated 端点），而不是整个启动失败。
        """
        return self._python.is_file() and self._worker.is_file()

    def _call(self, payload: dict[str, Any]) -> Any:
        if not self.available():
            raise VendorError(
                f"data-service 未就绪（缺 {self._python} 或 {self._worker}）。"
                "见 data-service/README.md 的 venv 创建步骤。"
            )
        try:
            proc = subprocess.run(
                [str(self._python), str(self._worker)],
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired as e:
            what = payload.get("name") or payload.get("action")
            raise VendorError(
                f"vendor 调用超时（>{self.timeout_s}s）：{what}"
            ) from e

        stdout = (proc.stdout or "").strip()
        if not stdout:
            # 没有输出通常意味着子进程在 import 阶段就崩了（比如 venv 坏了）
            raise VendorError(
                f"vendor 子进程无输出（退出码 {proc.returncode}）。stderr 尾部："
                f"{(proc.stderr or '')[-600:]}"
            )
        try:
            out = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise VendorError(
                f"vendor 子进程输出不是 JSON（退出码 {proc.returncode}）：{stdout[:300]}"
            ) from e

        if not out.get("ok"):
            raise VendorError(out.get("error") or "vendor 调用失败（无错误信息）")
        return out.get("result")

    def capabilities(self) -> list[dict[str, str]]:
        """vendor 能做什么（给 agent 的清单）。"""
        result = self._call({"action": "list"})
        return result if isinstance(result, list) else []

    def invoke(self, name: str, *, args: list[Any] | None = None,
               kwargs: dict[str, Any] | None = None) -> Any:
        """调一个 vendor 能力。

        私有函数（`_` 开头）由 worker 侧拒绝 —— 这里不预先过滤，
        因为「谁有权决定哪些能暴露」应该只有一处（worker），
        两处判断迟早不一致。
        """
        return self._call({
            "action": "invoke",
            "name": name,
            "args": args or [],
            "kwargs": kwargs or {},
        })
