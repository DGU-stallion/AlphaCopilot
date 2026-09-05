# ADR-0007 — 页面驱动形态 + Agent Provider 解耦 + 参数化 Page Spec

**状态**：已决定
**日期**：2026-09-02
**补充**：ADR-0006（不取代；本 ADR 调整产品形态与 dsh 耦合面，四层划分不变）

## 背景

M1–M3 完成后（T25–T40，均以 keyless mock 模型验收），复盘暴露三个方向性问题：

1. **形态偏差**：PLAN 第一节把「Chat 时间线」定为主入口（ADR-0002），但实际使用中
   每天要重复看的内容（复盘、相关性）不应每天重新对话生成。用户要的是
   **页面驱动 + 对话辅助**，与现锚冲突。
2. **provider 锁定**：ADR-0006 声明 dsh 耦合面收敛到「3 wire 方法 + cordis.yml」，
   但实现层把 dsh 的类型（`HarnessSettings`）、wire 事件形状（`text-delta`）、
   模型参数（`thinking`/`reasoningEffort`）泄漏到了业务层与前端 3 个文件。
   用户要求 dsh 可替换（如本地 Claude Code / 其它 CLI），需真正的防腐层。
3. **能力未沉淀**：相关性计算留在 mock 脚本字符串里，`alpha.factor` 不存在；
   承诺 A 的实质（真实模型靠 docstring 自己取数算图）从未跑过。

## 决定

### 1. 产品形态：页面驱动，对话辅助

- 左侧可收展 tab 栏选择展示页；「每日复盘」「相关性分析」为 `builtin` 固定页。
- 全局右下角浮标按钮唤出 **右侧滑出的 chat panel**；对话不再是主入口。
- 会话状态与 SSE 连接生命周期提升到 `AppShell` 层（context/store），
  panel 开关不影响流与消息留存。

ADR-0002「单一对话时间线为主入口」的**主入口地位**被本条取代；对话时间线本身保留，
降级为 panel 内的组件。

### 2. Agent Provider 防腐层（真正解耦）

引入中立契约，dsh 成为其一个实现，可替换：

- `backend/agent/provider.py`：`AgentEvent`（中立事件）+ `AgentProvider`（Protocol）
  + `ProviderSpec`（中立配置，不含 cordis/session_root 等 dsh 词汇）。
- `backend/agent/providers/dsh.py`：现 `harness.py` 下沉于此，负责 cordis.yml 生成、
  `text-delta` 解析、id-collision 规避、**模型参数归一化**（thinking 等 dsh 私有参数
  不外泄，provider 内部按目标端点能力决定是否传）。
- 业务层（`api/*`）与前端只认中立事件 kind：`text_delta` / `tool_started` /
  `tool_result` / `turn_end` / `error`；不再出现 `assistant/chunk`、`text-delta`、
  `cordis` 等字样。

**准入约束**：provider 契约要求「能禁用 shell / 只经 MCP 执行代码」。不满足此约束的
provider 不予接入（AGENTS 硬规则 9 的结构保证在最小公分母下降级为配置保证，接受）。

本 ADR 只落 dsh 一个实现；第二个 provider 出现时按两个实测样本再校准契约字段
（遵循「出现真实重复再抽象」）。

### 3. 参数化 Page Spec 契约（承诺 B 的交互式扩展）

Page spec 增加 `params` 段与 `kind` 字段，使交互式分析页也能「插一条记录即新增」，
不为单页写组件（守住 AGENTS 硬规则 6）：

```jsonc
{
  "id": "p-corr", "slug": "correlation", "title": "相关性分析",
  "kind": "builtin",              // builtin: 固定左侧 tab，不可删；user: 可删
  "status": "published",
  "layout": "grid|stack",
  "params": [
    { "name": "symbols", "type": "symbol_list", "label": "标的",
      "default": ["600519","000858"], "max": 8 },
    { "name": "window", "type": "int", "label": "滚动窗口", "default": 60,
      "min": 5, "max": 250 },
    { "name": "range", "type": "date_range", "label": "区间", "default": "1y" }
  ],
  "blocks": [
    { "kind": "chart", "span": 2, "analysis_ref": { "fn": "correlation.overlay" } },
    { "kind": "chart", "span": 1, "analysis_ref": { "fn": "correlation.matrix" } }
  ],
  "refresh": { "mode": "manual|on_open|cron", "cron": "0 9 * * 1-5" }
}
```

**安全决策（不可协商）**：`analysis_ref.fn` 是字符串键，经 `alpha/registry.py`
**白名单注册表**解析。**禁止** `importlib`/`eval` 动态解析——AI 能建 draft spec，
动态解析等于把任意代码执行权交给幻觉。`fn` 不在注册表内的 spec 一律拒收
（独立负向测试守护）。参数值经注册函数声明的规格校验（类型/取值域），越界拒收。

渲染端点：`POST /api/pages/{slug}/render`，body 为参数值 → 返回各 block 的 option JSON。

## 权衡

- **备选：相关性页写成独立组件（方案 A）** → 否决。直接但破硬规则 6，每个交互式
  分析页都要写组件。用户已确认后续会有多个交互式分析页，方案 B 的抽象有真实需求支撑，
  非预防性抽象。
- **备选：只划 provider seam 不改模型参数处理** → 否决。真实 agnes 端点
  （openai-completions）很可能不认 `thinking`/`reasoningEffort`，参数归一化是接通
  真实模型的前置，必须进 provider 层。

## 影响

- `docs/PLAN.md` 第一节「北极星」的「典型工作日」与架构图「主入口」措辞更新（本轮同步改）。
- 真实模型（agnes）接入：`ProviderSpec` 增 `base_url`/`api_key`/`model`；凭据从
  `~/.dsh/.credentials.yaml`（`AGNES_API_KEY`）或环境变量读，**不进仓库、不进 workspace**。
- `store.py` 按聚合拆仓储（DDD 边界）；`page` 表 `spec` 内含新字段，走 migration。
- 任务号从 **T41** 续编（T41–T50）。
- 测试分层：纯函数单元 / 契约 / mock 集成（现 T36/T40 作管道回归）/ `@pytest.mark.live`
  真实 agnes（默认跳过，断言仅结构性）。
