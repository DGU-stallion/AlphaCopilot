# data-service

独立的 A 股数据服务。vendor `simonlin1212/a-stock-data`（V3.10.2）作为取数唯一实现，
按 REFACTOR-PLAN M3 接入；本阶段（M3-V1/V2）只做 venv 与 vendor 文件，
loader（M3-V3）/ 测试（M3-V4）/ REST（M3-V5）/ 同步脚本（M3-V6）为后续任务。

```
data-service/
  requirements.txt    # 独立依赖清单（不装 mootdx，见下）
  README.md           # 本文件
  .venv/              # 独立虚拟环境（gitignore，不入库）
  src/                # 本地适配代码（loader 等，M3-V3 起）——不碰 vendor/
  vendor/
    README.md         # 只读约定与 CI 校验说明
    a-stock-data/     # 上游原样拷贝：SKILL.md / LICENSE / CHANGELOG.md / NOTICE / tests/
```

## 为什么必须独立 venv（M3-V1）

vendor 依赖与主环境（`backend/`）不可调和，两条证据都来自公开元数据，可复现：

1. **mootdx 与主环境 httpx 版本冲突**（PyPI 元数据，2026-10-21 抓取）：
   - `mootdx 0.11.7` requires：`httpx<0.26.0,>=0.25.0`（另有 `py-mini-racer<0.7.0` 等旧约束）
   - `mcp>=1.9`（`backend/pyproject.toml` 钉了 `mcp>=1.9,<2`）requires：`httpx>=0.27`
   - 买方（`<0.26`）与卖方（`>=0.27`）区间不相交，pip 解析必然失败。
     同装一个环境里根本装不上，不是「能用但不舒服」。
2. **`backend/pyproject.toml` 自己也钉了 mootdx**（`mootdx>=0.10` + `httpx>=0.27`），
   这个组合在当前后端环境里本身就是未求解的冲突；data-service 不再把 mootdx 写进
   任何 requirements，等于新代码不再依赖它，而不是把冲突搬到新目录。

**主环境（backend venv）不该装的东西**：`mootdx`。它锁 `httpx<0.26`，会和
`mcp` `httpx-sse` 等全链冲突；且本项目实测 mootdx 连财务都取不到
（`Quotes.factory` 抛 ValueError；指定 server 后 finance 返回 0 行，
上游 issue #52 同证）。vendor SKILL.md 的 K 线已换腾讯源，不依赖 mootdx。

`data-service/.venv` 与 backend 的 venv 互不感知：
- 一个进程只用其中一个；不存在混装
- 唯一交互边界是后续 M3-V5 的 HTTP REST（同机不同端口），语言/进程级隔离

## 环境复现

```bash
cd data-service
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

实测（2026-10-21，Python 3.13.13）可一次性装成，版本见 `requirements.txt`
上方注释与本 README 底部验收记录。

## vendor/ 只读约定

`vendor/` 是上游原样拷贝（sha256 记录在 `vendor/a-stock-data/NOTICE`）：

- **任何人不许手工编辑 vendor 下的文件**，包括 SKILL.md 的注释、换行、tail 空行
- 本地适配全部写在 `src/`（loader 在运行时抽 python 块 exec，不改源文件）
- CI 用 `git diff --exit-code data-service/vendor/` 校验无本地改动（todo：CI job，
  建议 job 定义见本报告，尚未写入 ci.yml）
- 更新只能通过同步脚本（M3-V6，`scripts/vendor-a-stock-data.sh`）整目录覆盖

## 如需 mootdx 的未来选项

放在 `data-service/.venv` 内单独装（本 venv，装了不影响主环境）；
但鉴于本机实测取不到任何数据，大概率永远不需要。
不要 `pip install --no-deps` 手改依赖树——那是不可复现的钉。

---

## 验收记录（2026-10-21, M3-V1/V2）

```
$ data-service/.venv/bin/python -c "import sys; print(sys.version)"
3.13.13 | packaged by Anaconda, Inc. | ...

$ .venv/bin/pip install -r requirements.txt   # 一次成功
Successfully installed baostock-0.9.4 certifi-2026.10.19 charset_normalizer-3.5.2
et-xmlfile-2.0.0 idna-3.20 iniconfig-2.3.1 numpy-2.5.4 openpyxl-3.1.5 packaging-26.3
pandas-3.0.6 pluggy-1.7.0 pygments-2.21.0 pytest-9.1.1 python-dateutil-2.9.0.post0
requests-2.34.2 six-1.17.0 urllib3-2.8.0 xlrd-2.0.2

$ wc -l vendor/a-stock-data/SKILL.md → 7585
$ grep -c '```python' vendor/a-stock-data/SKILL.md → 91
$ shasum -a 256 vendor/a-stock-data/SKILL.md
d30aa90edb881a45168c397a6ca1ccfebc440a8d4c93b3d94d3123d27b260a1d
```
