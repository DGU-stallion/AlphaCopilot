# 调研：a-stock-data V3.10.2（数据层供体项目）

**日期**：2026-10-20
**结论**：**大幅更新了，而且正好命中我们三个已知问题。建议全量 vendor 当前版本（保留全部 15 层能力），替换我们 4 个月前的旧移植。**

---

## 1. 项目现状

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/simonlin1212/a-stock-data |
| 版本 | **V3.10.2（2026-10-11）** · commit `29b07d2e3700` |
| 许可 | **Apache 2.0**（注明出处即可） |
| 规模 | 15 层 / 87 个端点 / 34 个数据源 |
| 形态 | **单文件 `SKILL.md`**（Markdown + 内嵌 Python），面向 AI 编程助手 |
| 测试 | **179 条离线测试**（从 SKILL.md 抽代码跑，不联网）+ 联网测试（显式开关） |
| 定位 | 「只负责取数，不带回测引擎」——**与我们的 `alpha/` 计算层正好互补** |

**我们的现状**：`backend/research/astock.py` 头部写着「移植自 a-stock-data 工具包（五层数据源）」，
代码注释里有「移植自 a-stock-data v3.3」。也就是说我们落后 **7 个小版本**。

---

## 2. 三个直接命中我们问题的更新

### 2.1 腾讯分钟 K 线可用（我们误判了）

我们在 ADR-0011 写「60 分钟线不可用，mac 无解」。**这是错的。**

本项目 V3.9 起把 K 线主源改成腾讯，支持 **1/5/15/30/60 分钟**。我实测确认：

```bash
curl "https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh600519,m60,,5"
# {"code":0,...,"m60":[["202610191500","1333.50","1324.97","1334.13","1322.91","8741.06",{},...]]}
#                             时间        开        收        高        低        量
```

**关键细节（他们 V3.10.1 踩过的坑）**：

- 端点必须用 `ifzq.gtimg.cn`，`web.ifzq.gtimg.cn` 的 `mkline` 会 301
- **科创板（688/689）成交量单位是「股」，其余是「手」**（差 100 倍）。我实测确认：
  `600519 vol=34136`（手）vs `688017 vol=10632800`（股）
- 分钟线最近一个交易日的量是取整到手的，下一交易日才回填成精确股数
- 单次最多 320 根

→ **ADR-0011 与 REFACTOR-PLAN 里「60 分钟线不可用」的结论需要更正。**

### 2.2 mootdx 的 K 线/盘口/逐笔 2026-09 全挂了（他们 issue #52）

与我们实测一致。他们的处置：

| 原能力 | 新来源 |
|---|---|
| 日/周/月 K 线（前复权） | 腾讯 K 线 |
| 1–60 分钟 K 线 | 腾讯 K 线（三入口轮换防限流） |
| 某交易日全市场日线（含成交额） | 通达信官网盘后包（HTTP zip） |
| 当日逐笔 | 腾讯逐笔 |
| 财务快照 / F10 | mootdx 保留 |

**但我们本机实测：mootdx 连财务也拿不到。**

```
Quotes.factory(market="std")                      → ValueError（BESTIP bug）
Quotes.factory(server=("119.147.212.81",7709))    → 73.6s 连上，finance 返回 0 行
```

→ **对我们来说 mootdx 应该整体放弃**，财务走 akshare 同花顺摘要（实测 0.66s / 103 行）
或新浪财报三表。

### 2.3 V3.0 起彻底移除 akshare，理由正好是我们踩的坑

他们的原话：

> akshare 本质是对东财/同花顺/新浪等公开 API 的封装，中间层增加了故障点
> （版本兼容 bug、pandas 3.0 ArrowInvalid 等）。V3.0 直连底层 HTTP API。

我们的 `astock.stock_news()` 就是 `ArrowInvalid: invalid escape sequence` —— **同一个 bug**。

→ 这削弱了 ADR-0011「必须留 Python 因为 akshare」的论据：
真正不可替代的是 `pandas`（数据处理）+ `baostock`（估值历史/上市退市/ST，TCP 客户端），
akshare 本身可以去掉。

---

## 3. 他们新增的、我们缺的能力（按对我们的价值排序）

| 能力 | 为什么重要 | 对应我们的里程碑 |
|---|---|---|
| **申万行业变迁史** | 消除**前视偏差**（回测里用「今天的行业」筛历史 = 作弊） | M4 因子/回测 |
| **估值历史** PE/PB/PS/PCF + 换手 + 停牌 + ST（2016+） | 估值分位、因子、`valuation_percentile` 的正确实现 | M4 |
| **上市/退市日** | 消除**幸存者偏差**（退市股不在今天的列表里） | M4 回测 |
| **ST 名单**（沪深京当日） | Universe 过滤必需 | M3 Universe |
| **复权因子** qfq/hfq | 回测正确性 | M4 回测 |
| **全市场某日线**（盘后包） | 横截面回测不用逐票请求 | M4 |
| **筹码分布 CYQ**（本地计算） | 散户最常问的指标之一 | M5 可选 |
| **事件驱动**：业绩预告/机构调研/增减持/回购/质押/新股 | 研究线索 + 未来「命题核验」的证据源 | M5 / FinBuddy 方向 |
| **互动易 / 上证e互动** | **公司对传闻的官方回应**——命题核验的一手证据 | FinBuddy 方向 |
| **宏观**：社融/PMI/中债收益率/LPR/回购利率 | 宏观看板从「行情」升级到「流动性」 | M4 |
| **指数成分/权重/估值 + 官方交易日历** | 基准、行业中性、Universe | M4 |
| 期货/期权/可转债 | 暂不需要 | 不做 |
| 逐笔成交 | 25 秒一次，对低频投研过重 | 不做 |

---

## 4. 他们值得抄的工程实践

| 实践 | 说明 |
|---|---|
| **`norm_ticker()` + 抛错而非返回空** | 代码写错时抛 `ValueError`，避免「查不到」被误读为「没数据」 |
| **`is_stale` / `stale_reason`** | 北交所老码会返回**僵尸报价**（定格在迁移日、成交量 0），必须显式标记 |
| **统一限流 `em_get()` + `EM_MIN_INTERVAL`** | 东财系共用风控，限流防封（我们已有） |
| **备用源按「风控面」分离** | 主源被封时换的是**不同域名**的源，不是同域换路径 |
| **成交量单位按品种写死** | 主板/科创/可转债/指数各不同，文档里逐条列 |
| **179 条离线测试从 SKILL.md 抽代码跑** | 保证「文档里的代码」和「能跑的代码」是同一份 |
| **CHANGELOG 记录数据口径变化** | 每次改单位/改字段都留痕 |

---

## 5. 建议：全量 vendor，两层暴露

**不做的事**：
- ❌ 不装它的 `SKILL.md` 给 agent 当 skill 用。会让 agent 绕过我们的数据门面
  `alpha.data`（没有 as-of、没有缓存、限流翻倍），出现两条取数路径。
  > 2026-10-21 注：`MarketDataPort` 已随「后端保 Python」取消（ADR-0011 §0），
  > 但这条约束的实质不变——门面是 `alpha.data`，不是 Pi 里再挂一份。
- ❌ 不按需裁剪端点。**保留全部 15 层 / 87 个端点**——期货、期权、可转债、事件驱动
  现在用不上，但扩展时会用；裁掉再长回来成本更高。

**做的事**：

1. **原样 vendor** `SKILL.md`（425KB / 7585 行 / 91 个 python 代码块）到
   `data-service/vendor/a-stock-data/`，附 `LICENSE`（Apache 2.0）与 `NOTICE`（出处 + commit）。
2. **写一个 loader**：按顺序抽出 91 个代码块 → 用 AST 去掉「模块级示例调用」
   （只保留 import / 常量 / def / class）→ 在同一个 namespace 里 exec → 导出公共函数。
   实测：**182 个函数定义，181 个唯一名**（仅 `_macro_get` 重复一次，后者覆盖前者）。
   上游自己的测试就是这么做的（`tests/test_v39_sources.py` 的 `_defs_only` + `_exec_with_stubs`）。
3. **复用他们的 179 条离线测试**作为 data-service 的测试基线（从 SKILL.md 抽代码跑，不联网）。
4. **两层暴露**：

   | 层 | 用途 | 形态 |
   |---|---|---|
   | **Curated REST** | 页面用的确定性数据（约 15 个） | `/v1/quote`、`/v1/kline`… 带缓存 + `asOf` |
   | **Generic invoke** | agent 的 ad-hoc 研究，覆盖全部 87 个 | `GET /v1/capabilities` + `POST /v1/invoke {name, kwargs}` |

   Agent 也可以直接 `import a_stock_data`（模块在 `PYTHONPATH` 上）——**这是「完整能力」
   的一部分，允许**，但产出的 artifact 必须标 `provenance.kind = agent`。

5. **上游同步脚本**：`scripts/vendor-a-stock-data.sh` 重新下载 `SKILL.md` → 跑 179 条
   离线测试 → 绿则更新 `NOTICE` 里的 commit。上游更新频率约每周一次，同步成本应接近零。

6. **我们的 `alpha/` 计算层保留**（回测、因子、相关性、涨停样本），它明确「不带回测引擎」。

7. **财务数据不用 mootdx**：走 akshare `stock_financial_abstract_ths`（实测可用）
   或它的新浪财报三表。

**依赖实测**（他们建议 `pip install mootdx requests pandas stockstats numpy baostock xlrd openpyxl`）：

| 包 | 本机 | 代码里实际用途 |
|---|---|---|
| pandas / numpy / requests | ✅ 已装 | 数据处理 / 筹码网格 / 全部 HTTP |
| **baostock** | ❌ **未装** | 估值历史、换手、停牌、ST、退市日（53 处引用） |
| xlrd / openpyxl | ❌ 未装 | `pd.read_excel` 引擎（申万行业、社融、国证、两融） |
| mootdx | ✅ 0.11.7（但不可用） | 财务快照 / F10；K 线/盘口/逐笔 2026-09 起失效 |
| stockstats | ❌ 未装 | **代码里没有 import**，只出现在文档依赖表——可不装 |

注意 `mootdx` 锁 `httpx<0.26`，与 MCP 等要求 `httpx>=0.27` 冲突；
**本项目不装 mootdx**（连财务都取不到），所以这个冲突不应该发生。
若将来真需要，放在 data-service 独立 venv，并且不要 `pip install --no-deps` 手改——
那是不可复现的钉。

**收益**：一次性解决 60 分钟线、数据口径 bug、7 个版本的能力差距、
以及「87 个端点自己维护」的问题。**成本约 2–3 天**（vendor + loader + 接 HTTP + 测试）。

## 6. 需要更正的两份文档

| 文档 | 原文 | 更正 |
|---|---|---|
| ADR-0011 §事实 1 | 「60 分钟线不可用，不是降级是没能力」 | 腾讯 `mkline` 可用；注意科创板单位、320 根上限、当日回填 |
| ADR-0011 §3 | 「mootdx 依赖删掉；kline 的 60 分钟分支保留但返回空」 | mootdx 整体放弃；分钟线接腾讯；财务走 akshare/新浪 |
| ADR-0011 §2 论据 | 「必须留 Python 因为 akshare」 | 改为「因为 pandas + baostock + 回测引擎」；akshare 可去掉 |
| REFACTOR-PLAN §6 | 60 分钟线 ❌ 不可用 | ✅ 腾讯 mkline（带口径说明） |
| REFACTOR-PLAN M0-5 | 「删 20 个死函数」 | 改为「全量 vendor V3.10.2 + loader + 复用 179 条离线测试」（**2026-10-21：实现从 M0-5b 移到 M3-V1～M3-V6**） |

---

## 7. vendor 操作手册（M3-V1～M3-V6 执行时照此进行）
>
> **2026-10-21 变更**：本节原标为 M0-5b。现移到 M3（与 monorepo 搬迁一起），
> 且**前置 M3-V1：data-service 独立 venv**（下方的 `mootdx` / `httpx` 冲突已实测，
> 不隔离则主环境必炸）。`mootdx` 本阶段**不装**——本机连财务都取不到。

> 版本已钉死：**V3.10.2 / commit `29b07d2e3700`**。上游约每周发一版，
> 执行前**不要**直接取 `main`，先比对下面这个 commit；若已漂移，
> 记录新 commit 并重跑第 3 步的全部测试，绿了再升级。

### 7.1 取文件

**前置（M3-V1）：先建独立 venv，否则装不上。**

```bash
cd data-service
python3.13 -m venv .venv
.venv/bin/pip install pandas numpy requests baostock xlrd openpyxl pytest
# 不装 mootdx（锁 httpx<0.26，与主环境 mcp>=1.9 冲突，且本机取不到数据）
```

```bash
mkdir -p data-service/vendor/a-stock-data
cd data-service/vendor/a-stock-data

# 钉死到具体 commit，不用 main
curl -L -o SKILL.md \
  https://raw.githubusercontent.com/simonlin1212/a-stock-data/29b07d2e3700/SKILL.md
curl -L -o LICENSE \
  https://raw.githubusercontent.com/simonlin1212/a-stock-data/29b07d2e3700/LICENSE
curl -L -o CHANGELOG.md \
  https://raw.githubusercontent.com/simonlin1212/a-stock-data/29b07d2e3700/CHANGELOG.md

# 上游测试（179 条离线 + 4 条联网，联网默认跳过）
mkdir -p tests && cd tests
for f in test_valuation.py test_official_data.py test_v39_sources.py test_v310_sources.py; do
  curl -L -O https://raw.githubusercontent.com/simonlin1212/a-stock-data/29b07d2e3700/tests/$f
done
```

### 7.2 校验（不校验就等于把一个黑盒放进了仓库）

```bash
wc -l SKILL.md          # 期望 7585
grep -c '^```python' SKILL.md   # 期望 91
shasum -a 256 SKILL.md  # 记进 NOTICE
```

### 7.3 写 NOTICE

```
a-stock-data — A 股全栈数据工具包
Upstream : https://github.com/simonlin1212/a-stock-data
Version  : V3.10.2 (2026-10-11)
Commit   : 29b07d2e3700
License  : Apache License 2.0 (见同目录 LICENSE)
SHA256   : <上一步的 shasum>
Synced   : 2026-10-20 by scripts/vendor-a-stock-data.sh

本目录内容为上游原样拷贝，未作修改。
本地适配（loader / 缓存 / HTTP 暴露）在 data-service/src/ 内，
不改动本目录任何文件——保证同步脚本可以无冲突覆盖。
```

**关键约束**：**`vendor/` 目录只读**。所有本地适配写在外面。
否则下次同步会冲突，然后有人手工 merge，然后就变成「自己维护的分支」——上次
v3.3 → 现在这条线就是这么烂掉的。

### 7.4 loader 骨架（参考实现，实际写在 `data-service/src/loader.py`）

上游测试里的 `_defs_only` + `_marker_code` 可以直接抄思路：

```python
import ast, re, types
from pathlib import Path

SKILL = Path(__file__).parents[2] / "vendor/a-stock-data/SKILL.md"
#        parents[2] 相对 data-service/src/loader.py 指到 data-service/
#        搬运到 monorepo 后要重新核对；加一条「loader 能跑」的测试就够。

def _blocks() -> list[str]:
    return re.findall(r"```python\n(.*?)\n```", SKILL.read_text(encoding="utf-8"), re.S)

def _defs_only(src: str) -> types.CodeType:
    """保留 import / 常量 / def / class，丢掉模块级示例调用。

    上游 tests/test_v39_sources.py 的 _defs_only 是权威实现，行为要对齐：
    遇到 Expr/For/While/With 直接丢；赋值语句若调用了本块定义的函数也丢。
    """
    tree = ast.parse(src)
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    keep = []
    for node in tree.body:
        if isinstance(node, (ast.Expr, ast.For, ast.While, ast.With)):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            calls = {c.func.id for c in ast.walk(node)
                     if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
            if calls & names:
                continue
        keep.append(node)
    tree.body = keep
    return compile(tree, "SKILL.md", "exec")

def load() -> dict:
    """91 个块依次 exec 进同一 namespace；后定义覆盖先定义（_macro_get 会重复）。"""
    ns: dict = {}
    for block in _blocks():
        try:
            exec(_defs_only(block), ns)
        except SyntaxError:
            continue          # 有些块是 shell / 非 python 片段，跳过
    return ns
```

**验收口径**：`len([k for k,v in ns.items() if callable(v) and not k.startswith('_')])`
应接近 87（上游的能力入口计数口径与「函数个数」不同，见其 README 的 88−1−1+1 说明）。

### 7.5 跑上游测试

```bash
cd data-service/vendor/a-stock-data
../.venv/bin/python -m unittest discover -s tests -v   # 期望 179 条离线全绿
```

测试是从 `SKILL.md` 里**抽代码执行**的，所以它们绿 = 「仓库里那份文件和能跑的代码是同一份」。
这是 vendor 这个形态唯一的质量保证，别跳过。

需要先补的依赖：`baostock xlrd openpyxl`（本机未装，见第 5 节依赖表）。

### 7.6 同步脚本（`scripts/vendor-a-stock-data.sh`）

```bash
#!/usr/bin/env bash
# 拉上游最新 → 跑 179 条离线测试 → 绿则更新 NOTICE，红则回滚
set -euo pipefail
COMMIT="${1:?用法: vendor-a-stock-data.sh <commit>}"
# 1) 备份 → 2) 按 7.1 下载 → 3) 跑 7.5 的测试
# 4) 绿：写 NOTICE + 输出 diff 摘要；红：git checkout -- . 并退出非零
```

### 7.7 与旧移植的关系

M3-V1～M3-V6 完成后，`backend/research/astock.py`（我们的 v3.3 移植）在 M3-7 删除。
在此之前它继续服务现有端点，**冻结不改**（M0-5 已约定）。
