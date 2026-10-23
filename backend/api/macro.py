"""宏观与利率数据（ROUND3 D4）。

宏观看板之前只有「一行数字 + 涨跌幅」，用户判定为**内容不足**而不是密度不够。
这里补的是能画成时间序列的东西 —— 孤立数字看不出「现在是高还是低」，
只有序列才能回答「PMI 连续几个月在荣枯线上」「10Y 国债从 2.7 掉到 2.0」。

数据源一律经 `alpha.vendor_bridge` 的子进程调用 data-service 的 vendor 能力
（唯一取数实现，AGENTS 反模式禁止另写 HTTP）。本模块**只做整形**：
vendor 返回什么就转成前端要的形状，不编造、不插值、不补 0。

⚠️ 取不到就 `available=False` + 非空 `reason` —— **绝不**返回空数组冒充成功
（空数组会被前端画成一条平线，比不画更误导）。这套纪律在两个已实测的坑里
得到验证（2026-10-22 实测）：
  - `lpr_history` 经 loader 加载后调用会抛 `NameError: EM_SESSION not defined`
    （东财共用 helper 的 `EM_SESSION = requests.Session()` 是带调用的赋值，
    被 loader 的「剥示例调用」规则连坐剥掉）；
  - 北向日频历史与全市场两融余额序列，vendor 当前**没有**能以合理成本
    给出近 60 交易日的端点（见各端点 docstring）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter

from alpha.vendor_bridge import VendorBridge, VendorError

# stage 常量的序列化形状：{"columns": [...], "rows": [[...], ...]}
logger = logging.getLogger(__name__)

_REPO_TENOR = "FR001"          # 隔夜资金利率（最活跃期限）
_REPO_LAST_N = 60              # 近 60 个交易日
_SF_LAST_N = 36                # 近 36 个月（整三个自然年）
_LPR_LAST_N = 36               # 近 36 个月


def build_macro_router(store: Any = None, bridge: VendorBridge | None = None) -> APIRouter:
    """宏观看板的取数路由。

    store 参数留空不用（宏观端点不落库；与商户路由签名对齐方便 app.py 注入）。
    bridge 默认 VendorBridge()；测试注入 FakeBridge 走进程边界这条缝。

    所有端点统一返回（与 frontend/src/lib/api.ts 的 MacroSeries / MacroCurve 对齐）：
      series → {"available", "reason", "unit", "points": [{period, value}]}
      curve  → {"available", "reason", "unit", "date", "points": [{tenor, value}]}
    """
    router = APIRouter(prefix="/api")
    # ⚠️ 必须在这里兜底构造：`app.py` 调的是 `build_macro_router(store)`，
    # 不传 bridge。曾经写成 `b = bridge`，结果生产路径上 b 是 None，
    # 每个端点都报 `'NoneType' object has no attribute 'invoke'` ——
    # 而**测试全绿**（测试都显式注入 FakeBridge），只有真启动才暴露。
    # 这类"测试覆盖了注入路径、没覆盖默认路径"的漏洞，只能靠真跑一次抓。
    b = bridge if bridge is not None else VendorBridge()
    if not b.available():
        # 显式记一笔：data-service 没就绪时所有宏观序列都会降级，
        # 排查时先看这行日志比逐个端点看 reason 快得多。
        logger.warning("macro: data-service 未就绪（%s），宏观序列将全部降级", b.data_service)

    def _invoke(name: str, args: list[Any] | None = None) -> Any:
        """vendor 能力调用；缺 venv / 子进程崩溃 / 上游抛错统一成 VendorError。"""
        return b.invoke(name, args=list(args or []), kwargs={})

    def _frame_columns(result: Any) -> dict[str, int] | None:
        """worker 序列化的 DataFrame → 列名→下标。"""
        if not isinstance(result, dict) or not isinstance(result.get("columns"), list):
            return None
        return {c: i for i, c in enumerate(result["columns"])}

    def _failure(reason: str, kind: str = "series", extra: dict[str, Any] | None = None) -> dict:
        body = {"available": False, "reason": reason, "kind": kind}
        if extra:
            body.update(extra)
        if kind == "curve":
            body.setdefault("date", "")
            body.setdefault("points", [])
        else:
            body.setdefault("unit", "")
            body.setdefault("points", [])
        return body

    def _series(unit: str, points: list[dict]) -> dict:
        return {"available": True, "reason": "", "unit": unit,
                "points": [{"period": p[0], "value": p[1]} for p in points]}

    def _safe(fn: Callable[[], dict], what: str, kind: str = "series") -> dict:
        """执行取数，任何异常都变成 available=False（页面永远不 500）。

        `kind` 必须透传：curve 与 series 的降级形状不同（前者要有 date 字段），
        不传的话失败时的响应会缺字段，前端拿到 undefined.date —— 又是一种
        「看起来正常、其实没数据」的状态。
        """
        try:
            return fn()
        except VendorError as e:
            return _failure(f"{what} vendor 调用失败：{e}", kind=kind)
        except Exception as e:  # noqa: BLE001 —— 形状不符也降级，页面永远不 500
            return _failure(f"{what} 返回形状异常：{e}", kind=kind)

    # ------------------------------------------------------------------ PMI ---
    @router.get("/macro/pmi")
    def pmi() -> dict:
        """§11.2 统计局 PMI。

        ⚠️ vendor 的 `nbs_pmi()` 只给**最新一期**（统计局「最新发布」页），
        没有月度历史能力（宏观日历 macro_calendar 同样在 loader 下调不通）。
        所以这里只能出**一个点** + 50 荣枯线：能看见「本月在线上还是线下」，
        看不见「连续几个月」。reason 里说实话，不假装历史存在。
        """
        def fetch() -> dict:
            r = _invoke("nbs_pmi")
            if not isinstance(r, dict):
                return _failure("PMI vendor 返回不是对象")
            period, value = r.get("period"), r.get("manufacturing_pmi")
            if not period or value is None:
                return _failure("PMI 正文解析不到制造业数值（统计局措辞可能已变更）")
            note = ("vendor 仅提供最新一期 PMI（无月度历史能力），"
                    "图表只有单点 + 50 荣枯线；历史序列待上游补充。")
            return {
                "available": True,
                "reason": note,
                "unit": "%",
                "points": [{"period": period, "value": float(value)}],
            }

        return _safe(fetch, "PMI")

    # ---------------------------------------------------------------- 社融 ---
    @router.get("/macro/social-financing")
    def social_financing() -> dict:
        """§11.1 人民银行社融增量，近 36 个月（三个自然年拼接）。

        vendor 按年取整张表；三次调用并行（每次 ~1.5s，串行 ~5s 太拖）。
        某一年失败只缩段不整条报废（<12 个月可画的图意义不大，故失败）。
        """
        years = [date.today().year - i for i in range(3)]

        def one(year: int) -> list[list[tuple[str, float]]] | VendorError:
            try:
                r = _invoke("pboc_social_financing", [year])
            except VendorError as e:
                return e
            cols = _frame_columns(r)
            if cols is None or "month" not in cols or "afre_total" not in cols:
                return VendorError(f"{year} 年社融表列名不符")
            out = []
            for row in r["rows"]:
                try:
                    raw_m = row[cols["month"]]
                    v = row[cols["afre_total"]]
                    # ⚠️ 必须先判 None 再 str()：`str(None)` 是**真值** "None"，
                    # 直接把它当月份会凭空造出一个 "None" 数据点（实测多出 1 条，
                    # 图上多一个尖峰）。同理会混进 NaN/NaT 这类空值标记。
                    if raw_m is None or v is None:
                        continue
                    m = str(raw_m).strip()
                    if not m or m.lower() in ("none", "nan", "nat"):
                        continue
                    out.append((m, float(v)))
                except (TypeError, ValueError, IndexError):
                    continue  # 未发布月份的整行空：vendor 本来就会丢，这里兜底
            return out

        def fetch() -> dict:
            with ThreadPoolExecutor(max_workers=3) as pool:
                parts = list(pool.map(one, years))

            ok: list[tuple[str, float]] = []
            errs: list[str] = []
            for year, part in zip(years, parts, strict=True):
                if isinstance(part, VendorError):
                    errs.append(f"{year}：{part}")
                else:
                    ok.extend(part)
            ok.sort(key=lambda t: t[0])
            seen: dict[str, float] = dict(ok)  # 去重（历史区意外跨年时按后取的®准）
            pts = sorted(seen.items())[-_SF_LAST_N:]
            if not pts:
                return _failure("社融 vendor 调用全部失败：" + "；".join(errs))
            body = _series("亿元", pts)
            if errs:
                body["available"] = True
                body["reason"] = f"部分年份数据不完整（{'；'.join(errs[:2])}）"
            return body

        return _safe(fetch, "社融")

    # -------------------------------------------------------- 中债收益率 ---
    @router.get("/macro/cn-yields")
    def cn_yields() -> dict:
        """§11.3 中债国债收益率**曲线**：最新一个交易日的 8 个期限。

        为什么是「曲线」不是「序列」：收益率曲线的意义在**形状**
        （正常/平坦/倒挂），单看 10Y 一个数字看不出倒挂。
        """
        tenors = ["3m", "6m", "1y", "3y", "5y", "7y", "10y", "30y"]

        def fetch() -> dict:
            start = date.today() - timedelta(days=_REPO_LAST_N * 2)
            r = _invoke("chinabond_yield_curve", [start.isoformat()])
            cols = _frame_columns(r)
            if cols is None or "date" not in cols:
                return _failure("中债收益率 vendor 返回列名不符", kind="curve")
            rows = r.get("rows") or []
            if not rows:
                return _failure("中债近 60 日没有返回任何曲线行", kind="curve")

            # 升序取最后一个交易日：vendor 的返回顺序不保证（曾按「最新在前」）。
            try:
                rows = sorted(rows, key=lambda x: str(x[cols["date"]]))
            except (IndexError, TypeError):
                return _failure("中债收益率行结构与列名不匹配", kind="curve")
            latest = str(rows[-1][cols["date"]])[:10]
            last_row = next(
                (x for x in reversed(rows) if str(x[cols["date"]])[:10] == latest), None
            )
            if last_row is None:
                return _failure("中债收益率找不到最新一日的行", kind="curve")

            points: list[dict] = []
            for t in tenors:
                i = cols.get(t)
                if i is None:
                    continue
                v = last_row[i] if i < len(last_row) else None
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    points.append({"tenor": t, "value": float(v)})
            if not points:
                return _failure("中债收益率最新一行没有可用的期限数值", kind="curve")
            return {
                "available": True, "reason": "", "unit": "%",
                "kind": "curve", "date": latest, "points": points,
            }

        return _safe(fetch, "中债收益率", kind="curve")

    # ------------------------------------------------------------ 回购利率 ---
    @router.get("/macro/repo")
    def repo() -> dict:
        """§11.4 银行间回购定盘利率（FR001 隔夜），近 60 个交易日。

        选 FR001 的理由：隔夜是最活跃期限，最能反映资金面松紧；
        FR007/FR014 在图上几乎重合，一起画只会糊成一条。
        """
        def fetch() -> dict:
            r = _invoke("repo_fixing_rates")
            cols = _frame_columns(r)
            if cols is None or "date" not in cols or _REPO_TENOR not in cols:
                return _failure(f"回购定盘利率 vendor 返回缺少 {_REPO_TENOR} 列")
            out: list[tuple[str, float]] = []
            for row in r.get("rows") or []:
                try:
                    d = str(row[cols["date"]])[:10]
                    v = row[cols[_REPO_TENOR]]
                    if d and isinstance(v, (int, float)) and not isinstance(v, bool):
                        out.append((d, float(v)))
                except (IndexError, TypeError, KeyError):
                    continue
            if not out:
                return _failure("回购定盘利率没有可解析的行")
            # 先按日期排序再截尾 —— 依赖上游顺序会在它改序时静默画错区间。
            out.sort(key=lambda t: t[0])
            return _series("%", out[-_REPO_LAST_N:])

        return _safe(fetch, "回购定盘利率")

    # ------------------------------------------------------------------ LPR ---
    @router.get("/macro/lpr")
    def lpr() -> dict:
        """§11.5 LPR 1Y 全历史 → 月度点，近 36 个月。

        ⚠️ 实测（2026-10-22）：`lpr_history` 经 loader 加载后调用会抛
        `NameError: EM_SESSION not defined` —— 东财共用 helper 的
        `EM_SESSION = requests.Session()` 是「带调用的赋值」，被 loader 的
        「剥掉示例调用」规则连坐剥掉。端点因此会降级成 available=False，
        这是**如实反映**，不是本模块的 bug。上游修好后此端点自动恢复正常。
        """
        def fetch() -> dict:
            r = _invoke("lpr_history")
            cols = _frame_columns(r)
            if cols is None or "date" not in cols or "lpr_1y" not in cols:
                return _failure("LPR vendor 返回缺少 lpr_1y 列")
            out: list[tuple[str, float]] = []
            for row in r.get("rows") or []:
                try:
                    d = str(row[cols["date"]])[:10]
                    v = row[cols["lpr_1y"]]
                    if len(d) >= 7 and isinstance(v, (int, float)) and not isinstance(v, bool):
                        out.append((d[:7], float(v)))
                except (IndexError, TypeError, KeyError):
                    continue
            if not out:
                return _failure("LPR 没有可解析的行")
            out.sort(key=lambda t: t[0])
            # 同一月有多条报价（LPR 每月 20 日报一次，理论上不会重）→ 后者胜
            dedup: dict[str, float] = dict(out)
            return _series("%", sorted(dedup.items())[-_LPR_LAST_N:])

        return _safe(fetch, "LPR")

    # -------------------------------------------------------- 北向 / 两融 ---
    #
    # 这两个**刻意不发起 vendor 调用**（测试也断言 `not b.calls`）：
    # 明知拿不到还去打一次，只会让用户多等一个超时。
    #
    # 拿不到的原因各不相同（都是 2026-10-22 实测，不是猜的）：
    #   北向：vendor 的 hsgtApi 只给**盘中分钟流向**，历史靠本地自缓存 CSV；
    #         而本机缓存是空的，上游自 2024-08 起也不再逐日披露实时净买入。
    #   两融：vendor 只有①单股明细（loader 下调不通）②交易所官方**单日快照**
    #         （逐日逐所拉全市场，60 个交易日 = 120+ 次子进程调用，不可行）。
    # 与其返回一条「0 附近平线」假装有数据，不如说清楚为什么没有。

    @router.get("/macro/northbound")
    def northbound() -> dict:
        return _failure(
            "北向资金：vendor 仅提供盘中分钟流向（历史依赖本地自缓存 CSV，当前为空）；"
            "上游自 2024-08 起不再逐日披露实时净买入，暂无可靠的日频历史序列。",
            extra={"points": []},
        )

    @router.get("/macro/margin")
    def margin() -> dict:
        return _failure(
            "两融余额：vendor 仅有单股明细（loader 下调不通）与交易所官方单日快照；"
            "逐日逐所拉全市场 60 个交易日需 120+ 次子进程调用，成本不合理，故不做。",
            extra={"points": []},
        )

    return router
