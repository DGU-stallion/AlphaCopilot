"""数据层「静默返回空」的可观测性测试。

## 这条测试保护什么

实测发现的问题：`alpha.data.closes_with_dates('600519')` 在 run_python 通道内
（Seatbelt 禁网络）返回**空列表**，不抛异常。

后果非常具体：模型拿到空数据，以为「数据源挂了」，于是改用 bash 自己 curl 抓数据、
自己用 numpy 算皮尔逊相关——**绕开了 alpha.factor，违反了「数字只来自确定性函数」**。
整条链路上没有任何一步报错，只是模型的行为悄悄变差了。

这是「静默失败」的典型：错误被 `except: return []` 吞掉，调用方无法区分
「今天这只票没数据」和「这个环境根本取不到数」。

## 修法不是「让沙箱能联网」

那会破坏「取数走数据层 / 不绕过 as-of 与缓存」的设计意图，也让 run_python 的记录
失去意义。正确做法是**让失败可分辨**：

- 真取不到（网络、沙箱禁网、上游变更）→ 抛异常，带原因
- 真的没有数据（退市、停牌、代码错）→ 可以返回空，但那条路径要能区分出来

本文件只测第一层：**沙箱内取数必须抛错，不能返回空**。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_darwin_only = pytest.mark.skipif(
    sys.platform != "darwin", reason="run_python 通道依赖 macOS sandbox-exec"
)


@_darwin_only
def test_data_fetch_inside_channel_raises_instead_of_returning_empty(tmp_path):
    """run_python 通道内取 K 线：必须**抛错**而不是返回空列表。

    为什么必须抛：返回空和「成功但没数据」在调用方看来一模一样。模型会据此
    判断「数据源不可用」并绕路自己算——而它绕的那条路正是我们最不想要的。

    抛错则给了模型一条明确的出路：换方式（比如让业务层取数）或者向用户说明
    环境不支持，而不是静默降级成自行实现。
    """
    from mcpserver.runner import run_python

    code = (
        "from alpha import data\n"
        "rows = data.closes_with_dates('600519', count=10)\n"
        "if not rows:\n"
        "    print('EMPTY')          # ← 这正是要消灭的行为\n"
        "else:\n"
        "    print('GOT', len(rows))\n"
    )

    r = run_python(code, workspace=str(tmp_path), timeout=40)

    # 现状：stdout 里有 EMPTY，returncode == 0 —— 静默失败
    assert "EMPTY" not in r.stdout, (
        "run_python 通道内取数返回了空列表而没有报错。\n"
        "这会让模型误以为数据源不可用，转而去 bash 自己抓数据、自己算指标，\n"
        "绕开了 alpha.* 并违反「数字只来自确定性函数」。\n"
        "应当抛一个能说明原因（如网络被禁）的异常。\n"
        f"实际 stdout={r.stdout[:300]!r} stderr={r.stderr[:300]!r}"
    )
