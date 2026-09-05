"""共用工具：中国时区时间 + 交易日/收盘判据（原样搬运自 vibe-astock/duanxian/util.py）。

只搬 session/overseas/live-emotion 三个端点用到的时间与收盘判据部分，保持原口径不变。
"""

from __future__ import annotations

import datetime

try:
    from zoneinfo import ZoneInfo

    _CN_TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001  拿不到时区库时退回本机时间（聊胜于无）
    _CN_TZ = None


def china_now() -> datetime.datetime:
    return datetime.datetime.now(_CN_TZ) if _CN_TZ else datetime.datetime.now()


def china_today() -> str:
    return china_now().strftime("%Y-%m-%d")


def is_a_share_closed() -> bool:
    """A 股是否已收盘（上海时间 15:05 后）。"""
    n = china_now()
    return (n.hour, n.minute) >= (15, 5)


def is_weekend(date: str) -> bool:
    """周六日 → True（非交易日的廉价判据；节假日靠空数据兜底）。"""
    return datetime.datetime.strptime(date, "%Y-%m-%d").date().weekday() >= 5


def is_today(date: str) -> bool:
    return date == china_today()  # 上海时区
