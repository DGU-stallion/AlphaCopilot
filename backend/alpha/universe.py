"""alpha.universe —— Universe as query（M3-2）：「标的池 = 条件」的确定性求值器。

设计动机：池若是存下来的代码串（["600519","000858"]），数据变了池不会跟着变，
也回答不了「这个回测用的是哪个池」。把池定义成 **条件**（board/PE/PB/市值/换手/…），
每次用时按当前数据重算，`describe()` 如实回答「池是什么」。

## 纯函数边界（本模块纪律）

- `resolve()` / `UniverseQuery` / `from_codes()` / `describe()` 是**纯函数**：
  不联网、不读环境、无状态，市场快照（snapshot）一律由调用方**参数注入**——
  这是让测试可以离线确定性跑通的前提（见 tests/test_universe.py，全部离线）。
- `load_snapshot()` 是唯一的联网适配器（复用 research.astock 的东财 em_get 通道），
  只被 API 层 / agent 门面调用；它同样**不持状态**（缓存归调用方管）。
- 零框架依赖：不 import fastapi / pydantic，不读 env。

## 「全市场快照」从哪来

`load_snapshot()` 一把抓沪深京 A 股的当日快照（东财行情中心 clist 接口，
fs=沪深主板+创业板+科创板+北交所，与 research.astock.market_turnover_rank 同源，
但取全量字段：代码/名称/PE-TTM/PB/总市值/换手率；pz=50000 单次全量取，
push2 失败降级 push2delay —— 与 astock 现有取数纪律一致）。
 reloading 时点即「数据时点」；快照里的行情是**当日最新**（盘中即实时、收盘后即当日收盘）。

## 失败可分辨（test_data_observability 的约定，本模块最重要的一条）

- 数据源不可用（网络 / 上游变更）→ `load_snapshot()` 抛 `DataUnavailable`
  （复用 research.astock.DataUnavailable 类型），`resolve()` **原样穿透**，绝不吞成 []。
  空列表与「今天真的没有符合条件的股票」无法区分 —— 吞成 [] 会让调用方把
  「环境取不到数」误读为「这个池今天为空」，进而 bash 自造数字（已踩过的坑）。
- 匹配 0 只（池真的为空）→ 正常返回 []。
- 条件涉及的字段缺值（亏损股 PE 为 `-` → None）→ **无法验证即不入选**，宁缺勿滥，
  并在 docstring 说明；这与「正常但 0 匹配」仍可由 describe() 描述的池定义区分。

## 空条件的行为：明确拒绝

`resolve(UniverseQuery(), snapshot=...)` 抛 ValueError，不默认全市场。
理由：全市场 ≈ 5000 只，「忘填条件」被静默当成「全 A 池」几乎肯定不是本意，
且与「条件真的匹配 0 只」无法分辨 —— 与 DataUnavailable 同款教训：**失败要能分辨**。
要全市场请显式写 board 等至少一个条件（或者将来明确加一个 all_market 开关）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from research.astock import UA, DataUnavailable, em_get

__all__ = ["UniverseQuery", "UniverseConditionError", "DataUnavailable",
           "resolve", "from_codes", "load_snapshot", "board_of", "QUERY_FIELDS"]

SNAP_ROW_KEYS = ("name", "pe", "pb", "mcap", "turnover")
"""快照行字段约定：name 名称；pe/pb 倍数；mcap 亿元；turnover %。缺值一律 None。"""


class UniverseConditionError(ValueError):
    """查询条件本身不成立（空条件 / 显式列表混入其他条件 / board 非法 / 代码非法）。"""


# ---------------------------------------------------------------------------
# 条件模型
# ---------------------------------------------------------------------------

BOARDS = ("主板", "创业板", "科创板")


@dataclass(frozen=True)
class UniverseQuery:
    """标的池的条件定义（不可变；所有字段 None/False 表示该条件不生效）。

    codes 与其余条件**互斥**：codes 是显式池定义（「我就是要这几只」），
    若同时给条件，语义会变成「没法回答用户到底要什么」，直接构造期报错。
    """

    codes: tuple[str, ...] = ()
    board: str | None = None
    pe_min: float | None = None
    pe_max: float | None = None
    pb_min: float | None = None
    pb_max: float | None = None
    mcap_min: float | None = None    # 亿元
    mcap_max: float | None = None
    turnover_min: float | None = None  # %
    turnover_max: float | None = None
    exclude_st: bool = False
    limit: int | None = None

    def __post_init__(self) -> None:
        if self.board is not None and self.board not in BOARDS:
            raise UniverseConditionError(
                f"board 必须是 {'/'.join(BOARDS)} 之一，得到 {self.board!r}")
        if self.codes and self._has_conditions():
            raise UniverseConditionError(
                "显式代码列表（codes）与其他条件互斥：显式列表就是池定义本身，"
                "再叠加条件会让「池是什么」无法如实回答")
        if self.limit is not None and (self.limit <= 0):
            raise UniverseConditionError(f"limit 必须是正整数，得到 {self.limit!r}")

    def _has_conditions(self) -> bool:
        metric = ("board", "pe_min", "pe_max", "pb_min", "pb_max",
                  "mcap_min", "mcap_max", "turnover_min", "turnover_max")
        return any(getattr(self, k) is not None for k in metric) or self.exclude_st

    def is_empty(self) -> bool:
        """既非显式列表、也没有任何生效条件（resolve 会拒绝这种查询）。"""
        return not self.codes and not self._has_conditions()

    def describe(self) -> str:
        """人类可读地描述这个池——前端要显示「你选的池是什么」，必须如实、不缩写。"""
        if self.codes:
            head = f"显式列表 {len(self.codes)} 只"
            if len(self.codes) <= 8:
                head += "（" + ",".join(self.codes) + "）"
            return head

        def rng(lo, hi, label: str, unit: str = "") -> str:
            if lo is not None and hi is not None:
                return f"{_fmt(lo)}≤{label}≤{_fmt(hi)}{unit}"
            if lo is not None:
                return f"{label}≥{_fmt(lo)}{unit}"
            return f"{label}≤{_fmt(hi)}{unit}"

        parts: list[str] = []
        if self.board:
            parts.append(self.board)
        if self.pe_min is not None or self.pe_max is not None:
            parts.append(rng(self.pe_min, self.pe_max, "PE"))
        if self.pb_min is not None or self.pb_max is not None:
            parts.append(rng(self.pb_min, self.pb_max, "PB"))
        if self.mcap_min is not None or self.mcap_max is not None:
            parts.append(rng(self.mcap_min, self.mcap_max, "市值", "亿"))
        if self.turnover_min is not None or self.turnover_max is not None:
            parts.append(rng(self.turnover_min, self.turnover_max, "换手", "%"))
        if self.exclude_st:
            parts.append("剔除ST")
        if self.limit is not None:
            parts.append(f"前{self.limit}只")
        return " · ".join(parts)


def _fmt(v: float) -> str:
    s = f"{v:g}" if isinstance(v, float) else str(v)
    return s


def from_codes(codes: list[str]) -> UniverseQuery:
    """「显式列表」也是一种 query：池 = 给定的代码串（明天数据变了它也不变——这正是它的语义）。

    代码必须是 6 位数字，否则构造失败（而不是静默不匹配）。
    """
    for c in codes:
        if not (isinstance(c, str) and len(c) == 6 and c.isdigit()):
            raise UniverseConditionError(f"代码必须是 6 位数字：{c!r}")
    return UniverseQuery(codes=tuple(codes))


def board_of(code: str) -> str | None:
    """6 位代码 → 板块名。60/00=主板，30=创业板，688=科创板；其余（北交所 4/8/92 等）→ None。"""
    if code.startswith("688"):
        return "科创板"
    if code.startswith("30"):
        return "创业板"
    if code.startswith(("60", "00")):
        return "主板"
    return None


# ---------------------------------------------------------------------------
# 求值（纯函数）
# ---------------------------------------------------------------------------

SnapshotSource = Mapping[str, dict[str, Any]] | Callable[[], Mapping[str, dict[str, Any]]]
"""快照来源：现成的 {code: row} 映射，或惰性 loader（零参函数，联网取数）。

传 callable 的意义：显式列表查询不需要数据，loader 不会被调用 —— 不会白白打一次全市场请求。
"""


def resolve(query: UniverseQuery, *, snapshot: SnapshotSource | None = None) -> list[str]:
    """按当前数据把条件求值成代码列表（确定性；同快照必得同结果）。

    - 显式列表 → 原样返回（不需要快照）。
    - 条件型 → 要求 snapshot（映射或 loader）；loader 抛 `DataUnavailable` 时原样穿透。
    - 空条件 → UniverseConditionError（见模块 docstring「空条件」一节）。
    - 命中的代码按代码升序排列后再截 limit —— 保证「同一天重复求值结果一致」。

    匹配语义：
      * 区间一律闭区间（含等号），None 表示该侧不限；
      * 多条件是 AND；
      * 条件涉及的字段在快照里缺值（None，如亏损股 PE）→ 该标的不入选（无法验证即不选）；
      * exclude_st 排除 name 含 "ST"/*ST 的（name 缺值时不判 ST，保留——快照正常都带 name）。

    返回：命中代码列表（可能为空 —— 这与「数据源不可用」是两种不同的结果）。
    """
    if query.is_empty():
        raise UniverseConditionError(
            "空条件没有池语义：要么给显式列表（from_codes），要么至少一个过滤条件。"
            "拒绝默认展开成全市场，是为了让「忘填条件」与「真的匹配 0 只」可分辨")

    if query.codes:
        codes = list(query.codes)
        return codes[:query.limit] if query.limit is not None else codes

    snap = snapshot() if callable(snapshot) else snapshot
    if snap is None:
        raise UniverseConditionError(
            "条件型查询必须注入快照（resolve(query, snapshot=...)）："
            "None 不是「空结果」而是「没给数据」")

    matched: list[str] = []
    for code in sorted(snap):
        if _match(code, snap[code], query):
            matched.append(code)
    return matched[:query.limit] if query.limit is not None else matched


def _match(code: str, row: Mapping[str, Any], q: UniverseQuery) -> bool:
    """单标的是否满足全部条件（AND）。行缺字段时依赖该字段的条件判 False。"""
    if q.board is not None and board_of(code) != q.board:
        return False
    if q.exclude_st:
        name = row.get("name")
        if isinstance(name, str) and "ST" in name.upper():
            return False
    for key, lo, hi in (("pe", q.pe_min, q.pe_max),
                        ("pb", q.pb_min, q.pb_max),
                        ("mcap", q.mcap_min, q.mcap_max),
                        ("turnover", q.turnover_min, q.turnover_max)):
        if lo is None and hi is None:
            continue  # 该维度不筛
        v = row.get(key)
        if v is None:          # 缺值无法验证 → 不入选（宁缺勿滥，见模块 docstring）
            return False
        if lo is not None and v < lo:
            return False
        if hi is not None and v > hi:
            return False
    return True


# ---------------------------------------------------------------------------
# 联网适配器（API 层用；纯函数求值器不直接调用它 —— 数据一律参数注入）
# ---------------------------------------------------------------------------

_CLIST_PARAMS = {
    "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f12",
    "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
    "fields": "f12,f14,f115,f23,f20,f8",
}
# 字段：f12 代码，f14 名称，f115 PE(TTM)，f23 PB，f20 总市值(元)，f8 换手率(%)。
# fltt=2 时数值直接是浮点（不 ×1e2 编码）；缺值为 "-"。2026-10-21 实测。
_FS_LABEL = "沪深主板+创业板+科创板+北交所"


def load_snapshot() -> dict[str, dict[str, Any]]:
    """联网取全 A 股当日快照（resolve 的默认数据源）。

    单次 pz=50000 全量取；push2 失败降级 push2delay（延迟行情，日频场景足够）——
    与 research.astock.market_turnover_rank 同一容灾纪律。
    两个入口都失败时抛 DataUnavailable（绝不返回空 dict 与「真的 0 只」混淆）。
    """
    params = dict(_CLIST_PARAMS, pn=1, pz=50000)
    diff: list[dict] = []
    last_err: Exception | None = None
    for host in ("push2.eastmoney.com", "push2delay.eastmoney.com"):
        try:
            r = em_get(f"https://{host}/api/qt/clist/get", params=params,
                       headers={"User-Agent": UA}, timeout=20)
            data = r.json().get("data") or {}
            diff = data.get("diff") or []
            if diff:
                break
        except Exception as e:  # noqa: BLE001  换下一个入口
            last_err = e
            continue
    if not diff:
        raise DataUnavailable(
            f"全市场快照（东财 clist，{_FS_LABEL}）两个入口均不可用"
            + (f"：{type(last_err).__name__}: {last_err}" if last_err else ""))

    snap: dict[str, dict[str, Any]] = {}
    for d in diff:
        code = str(d.get("f12", "")).strip()
        if not (len(code) == 6 and code.isdigit()):
            continue  # 板块 BK 指数等非个股行
        name = str(d.get("f14", "") or "")
        pe, pb = _num(d.get("f115")), _num(d.get("f23"))
        mcap, turnover = _num(d.get("f20")), _num(d.get("f8"))
        if mcap is not None:
            mcap = mcap / 1e8  # f20 单位元 → 约定单位亿
        snap[code] = {"name": name, "pe": pe, "pb": pb, "mcap": mcap, "turnover": turnover}
    if not snap:
        raise DataUnavailable("全市场快照响应里没有任何个股行（上游协议可能已变更）")
    return snap


def _num(v: Any) -> float | None:
    if v in (None, "", "-"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 字段元信息（给前端渲染条件表单；与 UniverseQuery 的字段一一对应）
# ---------------------------------------------------------------------------

QUERY_FIELDS: list[dict[str, Any]] = [
    {"field": "board", "label": "板块", "type": "enum",
     "options": list(BOARDS), "unit": None,
     "note": "60/00=主板，30=创业板，688=科创板；不选=不限（含北交所）"},
    {"field": "pe_min", "label": "PE(TTM) 下限", "type": "number", "unit": "倍"},
    {"field": "pe_max", "label": "PE(TTM) 上限", "type": "number", "unit": "倍",
     "note": "与 pe_min 组成闭区间；亏损股 PE 缺值不入选"},
    {"field": "pb_min", "label": "PB 下限", "type": "number", "unit": "倍"},
    {"field": "pb_max", "label": "PB 上限", "type": "number", "unit": "倍"},
    {"field": "mcap_min", "label": "总市值 下限", "type": "number", "unit": "亿元"},
    {"field": "mcap_max", "label": "总市值 上限", "type": "number", "unit": "亿元"},
    {"field": "turnover_min", "label": "换手率 下限", "type": "number", "unit": "%"},
    {"field": "turnover_max", "label": "换手率 上限", "type": "number", "unit": "%"},
    {"field": "exclude_st", "label": "剔除 ST/*ST", "type": "boolean", "unit": None},
    {"field": "limit", "label": "最多返回", "type": "integer", "unit": "只",
     "note": "代码升序取前 N，保证同一天重复求值结果一致"},
    {"field": "codes", "label": "显式代码列表", "type": "code_list", "unit": None,
     "note": "与其他条件互斥：给了它池就是这几只，其余条件 ignored/禁止"},
]
