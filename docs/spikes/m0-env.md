# M0 环境实况核查

**日期**：2026-08-29

## 工具链（齐备）

| 工具 | 版本 | 路径 |
|------|------|------|
| Python | 3.13.13 | `/Users/a19150/miniconda3/bin/python3` |
| uv | 0.11.16 | `/Users/a19150/.local/bin/uv` |
| Node | v24.16.0 | 满足 dsh node carrier 要求（≥22.19） |
| sandbox-exec | 系统自带 | `/usr/bin/sandbox-exec` |

## 阻塞项

| 阻塞 | 影响 | 状态 |
|------|------|------|
| **无 runtime carrier** | `python/sdk-runtime/.../runtime/` 下无 exe 也无 node closure（`packaged-bin.js` 不存在，`dist-exe/` 不存在）。SDK 无法起子进程 | 攻坚中：构建 node carrier |
| **无 DEEPSEEK_API_KEY** | env 未设、无 `.env`、dsh 仓库 `.env` 也无 key。G1/G2/G4 需真实模型推理才能验证「agent 调通工具」 | 待用户提供；可先用 keyless/mock 验证机制面 |

## 现有资产实况

- **数据层可用**：`backend/research/astock.py` 的 `tencent_quote` 可导入、腾讯 gtimg 接口可达（茅台实测 price=1297.4）。
- **MCP server 有 pre-existing 缺陷**：`packages/dsh-alphacopilot-research/src/alphacopilot_research/server.py` 第 16 行 import 了尚未落地的 `events` 工具（T11 未完成），`python -m ...server` 会 `ImportError`。spike 用最小 server 绕开，不修产品代码。
- **MCP 框架**：标准 `mcp>=1.9,<2`（FastMCP，stdio transport）。

## SDK 运行时闭包（已核实 `python/sdk-runtime/package.json`，115 包）

- 含：`dsh-mcp-client`（可挂外部 MCP server）、skill/skill-filesystem/tool-skill、
  system-prompt/persona、subagent、session-persistence-jsonl|sqlite、compaction、
  fs-sandbox/sandbox-local(含 macOS Seatbelt)/sandbox-policy/permission-presets、
  tool-web/web-search、code-runtime(JS)。
- **不含**：任何 client/web UI 包；`dsh-bash-sandbox`（只有不隔离的 `bash-local`）；
  `code-runtime-python`（Python 代码执行后端不在闭包内 → 印证 T33 用我们自己的 run_python）。

## 门禁执行顺序调整

原计划 T21→T22→T24 串行卡在 carrier。实际按依赖重排：
1. ✅ G3 沙箱（零依赖）
2. ✅ MCP 独立连通（keyless，不经 dsh）
3. ⏳ 构建 node carrier（解阻塞）
4. ⏳ G1 完整版 / G4（需 carrier；真实调用需 key）
5. ⏳ G2（需 carrier）
