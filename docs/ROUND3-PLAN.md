# ROUND3 — 收尾批次（2026-10-22）

> 所有并行开发共用这一份约定。**先读完你的包对应的章节，再动手。**
> 共享内核（schema / store 方法 / 路由注册 / `api.ts` 契约）**已经由主控写好**，
> 你只填自己那一包，**不要改动别人负责的文件**。

## 全局硬规则（违反即返工）

1. **TDD**：先写会失败的测试，再实现。测试要能红——提交前自己变异验证一次。
2. **不要碰** `frontend/src/lib/api.ts`（契约已定好，直接用）。若确实缺函数，
   在你的包内用 `fetch` + `apiUrl()` 自己解决，并在报告里说明。
3. **不要碰** `backend/api/store.py`（方法已写好）、`backend/api/app.py`（路由已注册）。
4. **颜色只有一个真源**：`frontend/src/theme/tokens.ts`。组件里出现 `#` 开头的
   颜色字面量即违规（测试会查）。数字一律走 `<Num>` 组件。
5. **图表优先**：孤立数字必须配序列。ECharts option 里**不要传 legend**
   （窄容器会压绘图区），用 `<ChartLegend>` / `<ToneLegend>` 在 HTML 层自绘。
6. **取不到就如实说**：`available: false` + `reason`，**不编造、不插值、不补 0**。
   补 0 会在曲线上造出假断崖，比没数据危险得多。
7. **破坏性操作必须可撤销**（硬规则 14）。
8. 跑完整验证再报告：
   ```
   cd backend  && python3 -m pytest -q && ruff check .
   cd frontend && npx tsc --noEmit && npx vitest --run
   ```
   基线是 backend 472 passed / frontend 239 passed，**不许减少**。

## 已就绪的共享内核

### 后端 store（`backend/api/store.py`，直接用）

```python
# Run 软删（B3）
store.runs.soft_delete(rid) -> bool          # 列表默认已排除软删
store.runs.restore(rid) -> bool
store.runs.set_note(rid, note) -> bool
store.runs.list_recent(kind=..., limit=...)  # 已自动 WHERE deleted_at IS NULL

# 研报归档（B4）
store.docs.add_doc(title, source_path, text="", *, kind="note", tags="",
                   file_path="", bytes_=0, mime="") -> str
store.docs.list_docs()            # 已排除软删，不回 text
store.docs.get_doc(did)           # 含 text
store.docs.soft_delete_doc(did) / restore_doc(did) / update_doc_meta(did, title=..., tags=...)

# 会话（C4）
store.list_sessions()             # 已带 message_count
store.delete_session(sid)         # 硬删（会话不是产品真源）

# 设置（A3）
store.settings.get(key, "") / set(key, value)
```

`doc` 新列：`deleted_at` `kind` `tags` `file_path` `bytes` `mime`
`run` 新列：`deleted_at` `note`
新表：`setting(key, value, updated_at)`

### 后端路由（已注册，你填实现）

- `backend/api/macro.py` → `build_macro_router(store)`，挂在 `/api`
- `backend/api/settings_ai.py` → **已完成**，不要改

### 前端 api.ts 契约（已写好，直接 import 用）

```ts
// B3
runsApi.deleteRun(rid) / restoreRun(rid) / setRunNote(rid, note)

// B4
type DocKind = "note" | "pdf" | "markdown" | "image";
interface DocRow { id; title; source_path; kind; tags; file_path; bytes; mime; created_at }
reportsApi.list() / detail(did) / upload(file, {title?, tags?}) /
           createNote({title, text, tags?}) / remove(did) / restore(did) /
           setMeta(did, {title?, tags?}) / fileUrl(did)

// A3
interface ModelOption { id; provider; model; label; vision }
settingsApi.ai() -> {current, known, options: ModelOption[]}
settingsApi.setModel(model)

// C4
interface SessionSummary { id; title; runtime_session_id; created_at; message_count }
interface SessionMessage { id; role: "user"|"assistant"; content; meta?; created_at }
agentApi.sessions() / messages(sid) / deleteSession(sid)

// D4
interface MacroSeries { available; reason; unit; points: {period, value|null}[] }
interface MacroCurve  { available; reason; unit; date; points: {tenor, value}[] }
macroApi.socialFinancing() / pmi() / cnYields() / lpr() / repo() / northbound() / margin()
```

---

## 包划分（文件所有权，**严格不要越界**）

| 包 | 你拥有 | 你**不得**修改 |
|---|---|---|
| **B3** | `backend/api/runs.py`、`backend/tests/test_run_soft_delete.py`、`frontend/src/pages/Runs.tsx`、`frontend/src/pages/__tests__/Runs*.test.tsx` | store.py, app.py, api.ts, 其他页面 |
| **B4** | `backend/api/business.py`、`backend/tests/test_docs_archive.py`、`frontend/src/pages/MyReports.tsx`、`frontend/src/pages/__tests__/MyReports*.test.tsx` | 同上 |
| **D4** | `backend/api/macro.py`、`backend/tests/test_macro.py`、`frontend/src/pages/MacroDashboard.tsx`、`frontend/src/lib/macro-charts.ts`、对应 `__tests__` | 同上 |
| **D5** | `backend/alpha/factor.py`（只改 renderer/注册相关）、`backend/tests/test_correlation_lwc.py`、`frontend/src/components/charts/MultiLineChart.tsx`、`frontend/src/components/page/BlockRenderer.tsx`、对应 `__tests__` | store.py, app.py, api.ts, PageCanvas.tsx |
| **A3** | `frontend/src/pages/Settings.tsx`、`frontend/src/pages/__tests__/Settings*.test.tsx` | 后端全部（已写完） |
| **C-shell** | 新建 `frontend/src/components/agent/AgentWindow.tsx`、`AgentSessionList.tsx` + 各自 `__tests__` | Layout.tsx, ChatMessage.tsx, api.ts |
| **C-render** | 新建 `frontend/src/components/agent/ChatMessage.tsx`、`frontend/src/lib/agent-markdown.ts` + 各自 `__tests__` | Layout.tsx, AgentWindow.tsx, AgentSessionList.tsx, api.ts |

---

## B3 — Run 软删 + 备注

### 后端 `backend/api/runs.py`

```
DELETE /api/runs/{rid}          -> {"ok": true, "id": rid, "soft": true}
POST   /api/runs/{rid}/restore  -> {"ok": true, "id": rid}     404 = 不存在
POST   /api/runs/{rid}/note     -> {"ok": true}   body {"note": "..."}
GET    /api/runs                -> 已排除软删（store 已做，无需改）
```

要点：
- 404 判断用 `store.runs.get(rid) is None`（`get` 能取到软删的，所以 restore 也能找到）
- 内置/受保护的 Run **不存在**这个概念，不加 400 保护
- `note` 长度上限 500，超了 400

### 前端 `frontend/src/pages/Runs.tsx`

- 每条 Run 行加删除按钮（悬停显示，`Trash2`）
- 删除后弹**带「撤销」的提示条**（`role="status"`），与 `pages/` 页删除完全同一套交互
  （参考 `frontend/src/pages/PageView.tsx` 或导航栏里已有的 undo toast 实现）
- **不要**用 `window.confirm`：确认弹窗防手滑，防不了「确认完才想错」
- 行内可编辑备注：点一下变输入框，失焦保存（调 `setRunNote`）
- 列表要能显示备注列

### 测试
- 后端：软删后不出现在 `GET /runs`、`GET /runs/{rid}` 仍 200、restore 后回来、
  restore 不存在 → 404、note 写入与超长 400
- 前端：点删除 → 行消失 + 出现撤销条；点撤销 → 行回来

---

## B4 — 研报归档库

### 后端 `backend/api/business.py`

```
GET    /api/docs                 -> [DocRow]        软删已排除
GET    /api/docs/{did}           -> DocRow + text   404
POST   /api/docs                 -> multipart 上传，回 DocRow
POST   /api/docs/note            -> {"title","text","tags"} 纯文本，回 DocRow
GET    /api/docs/{did}/file      -> FileResponse（原文件，用于 <img>/<iframe> 预览）
PATCH  /api/docs/{did}           -> {"title"?,"tags"?} 回 {"ok": true}
DELETE /api/docs/{did}           -> {"ok": true, "soft": true}
POST   /api/docs/{did}/restore   -> {"ok": true}
```

**落盘位置**：`workspace/reports/<did><ext>`。`doc.file_path` 存**文件名**（相对），
不存绝对路径（备份/搬家后绝对路径全失效）。

**kind 判定**（按 MIME + 扩展名，别只看后缀名）：
- `image/png|jpeg|webp|gif` → `image`
- `application/pdf` → `pdf`
- `text/markdown` 或 `.md` → `markdown`
- 其他 → 拒绝，400 说明「只接受 PDF / Markdown / 图片」

**大小上限 20MB**，超了 413。
**mime 白名单**必须校验（不能只信前端给的 Content-Type）。

`workspace_root` 从 `Store` 拿不到——用 `backend/api/app.py` 里已有的
`ws_root` 约定：`Path(db_path).parent`（DB 就在 `backend/workspace/` 下）。
自己算清楚并写注释说明为什么。

### 前端 `frontend/src/pages/MyReports.tsx`

- 从「手动粘贴文本」改成**归档库**：列表 + 上传 + 标签筛选 + 搜索
- 上传：拖拽 + 点击选择，接受 PDF/MD/图片
- 预览按 `kind` 分派：`image` → `<img src={reportsApi.fileUrl(id)}>`；
  `pdf` → `<iframe>`；`markdown`/`note` → 正文
- 删除 → 带撤销的提示条

### 测试
- 后端：上传 PDF 落盘 + kind=pdf、上传 .txt → 400、超 20MB → 413、
  列表不含软删、restore 回来、`/file` 返回正确 Content-Type
- 前端：上传调 `reportsApi.upload`、按 kind 渲染不同预览、删除 + 撤销

---

## D4 — 宏观看板补内容（**内容不足，不是密度不够**）

用户原话：748 字、5 panel，是**内容太少**。目标是让「现在处于历史什么位置」
肉眼可见，所以**必须出时间序列**。

### 后端 `backend/api/macro.py`

数据源**只能**经 vendor：`backend/api/vendor.py` 已有 `POST /api/v1/invoke`
的能力，看它怎么调 `data-service/src/worker.py`，在你的 router 里复用同一个
调用路径（**不要**另写 HTTP 请求）。

要实现的端点与对应 vendor 能力（见 `data-service/vendor/a-stock-data/SKILL.md`）：

| 端点 | vendor 章节 | 说明 |
|---|---|---|
| `GET /api/macro/social-financing` | §11.1 人民银行 社融增量 | 月度序列，近 36 个月 |
| `GET /api/macro/pmi` | §11.2 统计局 PMI | 月度，制造业 + 荣枯线 50 |
| `GET /api/macro/cn-yields` | §11.3 中债收益率曲线 | **曲线**（1Y/3Y/5Y/7Y/10Y/30Y） |
| `GET /api/macro/lpr` | §11.5 LPR 全历史 | 1Y/5Y 两条，月度 |
| `GET /api/macro/repo` | §11.4 回购定盘利率 FR/FDR | 近 60 个交易日 |
| `GET /api/macro/northbound` | §3.2 同花顺北向资金 | 近 60 个交易日净流入 |
| `GET /api/macro/margin` | §4.1 融资融券 | 沪深两融余额，近 60 个交易日 |

**取不到就 `available: false` + `reason`**。vendor 不通时**不要**返回空数组
冒充成功——空数组在前面会被画成「一条平线」，比不画更误导。

先跑一次确认 vendor 真的能拿到（`data-service/.venv/bin/python`），
把实测结果（拿到几条、字段名长什么样）写进你的报告。拿不到的端点就
`available: false`，并在报告里说明，**不要伪造**。

### 前端

- `frontend/src/lib/macro-charts.ts`：ECharts option 构建器
  （PMI 折线 + 50 荣枯线 markLine；社融柱；国债收益率曲线折线；北向净流入正负柱；
  两融余额折线）。**不要传 legend**，用 `<ChartLegend>` 自绘。
- `MacroDashboard.tsx` 新增这些 panel，每块都是「图 + 一句当前读数」。
- span 用 2（宏观看板不在 page spec 体系里，直接栅格布局即可）。

### 测试
- 后端：mock vendor 返回 → 整形正确；vendor 抛错 → `available:false` + reason 非空
- 前端：option 构建器（标记线在 50、正负柱有正负色）；MacroDashboard 渲染出 panel

---

## D5 — 相关性走势图换 Lightweight Charts

用户要求 TradingView 式交互（十字光标、拖拽缩放），ECharts 做不到。

### 后端
`backend/api/page_spec.py` 有 `RENDERER_BY_FN` 映射。把
`correlation.overlay` 与 `correlation.rolling` 改成 `"lwc"`。
`alpha/lwc.py: option_to_series` 已经能把 ECharts line option 转成 LWC 载荷，
**不需要改它**（它就是干这个的）。

注意 `correlation.overlay` 是**多条** series（每个标的一条），
`correlation.rolling` 是 1 条。DRAWDOWN_FNS 里**不要**加它们（相关性没有"回撤"）。

### 前端
新建 `frontend/src/components/charts/MultiLineChart.tsx`：
- 一个 `createChart` 实例，N 条 `LineSeries` 叠在**同一个 pane**
  （多 pane 是给「净值 vs 回撤」那种量纲不同的场景，相关性叠图量纲相同）
- 颜色从 `usePalette()` 取，循环使用；调色板色不够时按序回绕
- 生命周期纪律与 `PriceChart.tsx` 完全一致（建实例 effect 依赖 `[]`、
  主题变化只 applyOptions、数据变化只 setData）——**照它的注释抄**
- 0 基线画一条水平参考线（相关性为负时能看出来）

`BlockRenderer.tsx` 的 lwc 分支：series 条数 > 1 且**没有** drawdown 时走
`MultiLineChart`。**注意**现有注释解释了为什么"按 series 条数分派"曾经是错的：
那次错的根源是把「净值+基准」当成「净值+回撤」。真正的判别符是
`payload.drawdown` 有没有值 —— 保持这个判定，只在**没有 drawdown** 的分支里
区分单条/多条。

### 测试
- 后端：`correlation.overlay` 的 renderer 是 lwc、载荷 series 条数 == 标的数、
  `drawdown` 为空
- 前端：MultiLineChart 渲染 N 条 series（mock lightweight-charts）；
  BlockRenderer 在无 drawdown + 2 series 时选 MultiLineChart

---

## A3 — 设置页（只做 model 选择）

后端**已全部完成**（`backend/api/settings_ai.py`）：
- `GET /api/settings/ai` → `{current, known, options:[34 个]}`（`pi --list-models` 现读）
- `PUT /api/settings/ai` → 写 `setting` 表；**下一次建会话即生效**，不用重启

### 前端 `frontend/src/pages/Settings.tsx`
- 「运行配置」那块把「模型端点：由本机 Pi 配置决定」换成一个**真能改的**选择器
- 按 provider 分组（`<optgroup>`），显示 `label`
- `known === false` 时给醒目提示：「当前模型不在注册表里」（别静默换掉）
- 保存后显示「已切换，下一条消息生效」
- **不要**加 baseURL / apiKey 输入框（`agent/provider.py:81` 明确说 PiProvider
  不消费它们，做了等于让人填无效 → UI 撒谎）

### 测试
- 渲染出 34 个选项中的 provider 分组
- 选择后调 `settingsApi.setModel`
- `known:false` 时出现提示文案

---

## C2–C5 — Agent 栏（最大的一包）

现状：Agent 栏可以折叠成右下角浮标（`data-region="agent-fab"`），但浮标点开后
是一个固定的右侧 `<aside>`，没有拖动、没有思考过程、没有会话列表、
对话是纯文本。

### C2 浮动窗
- 打开后是**浮层**（`position: fixed`），可拖动标题栏移动、右下角可 resize、
  松手吸附到屏幕边缘（16px 内吸附）
- 位置/尺寸记到 `localStorage`，刷新后还在
- 有最大/最小尺寸约束；窄屏（< 768px）退化为全屏抽屉，**不要**让浮窗跑到屏幕外

### C3 思考过程
- assistant 消息的 `meta.thinking`（可选）折叠展示，默认收起，
  标题「思考过程（N 字）」
- 流式过程中如果有 `thinking_delta` 事件也接上（看现有 SSE 消费代码有没有）

### C4 会话列表
- 浮窗顶部加「历史」入口，列出 `agentApi.sessions()`
- 每项显示标题 + `message_count` + 时间；点一下切换到那个会话
- 可删除（带撤销）
- 切会话 = 重新拉 `agentApi.messages(sid)`

### C5 对话渲染
- markdown 渲染（标题/列表/表格/代码块/行内代码/链接）
- 代码块带「复制」按钮
- 工具调用可见：`meta.tool_calls` 折叠展示，显示工具名 + 参数 + 结果摘要
- **不要**引入重型 markdown 库之外的东西；先看 `package.json` 有没有
  `react-markdown` / `marked`，没有就手写一个最小渲染器（够用即可，
  别为此加依赖 —— 加了要在报告里说明理由）

### 测试（必写）
- 拖动改变 `style.left/top`；resize 改变宽高
- localStorage 往返
- 思考过程默认收起、点开显示
- 会话列表渲染 + 切换调用 `agentApi.messages`
- markdown：标题/列表/代码块渲染出正确标签；代码块复制按钮写剪贴板

---

## 报告格式（每个包都要给）

```
### 包名
- 改动文件（逐个列，含行数增减）
- 测试：新增 N 个，全量 backend XXX passed / frontend XXX passed
- 实测结果（真跑过的命令 + 输出关键行）
- 变异验证（把哪个改动改坏 → 哪个测试红了）
- 没做到 / 有疑问的地方（**必须诚实**，不要写"已完成"掩盖）
```


---

## C 包拆分说明（重要：Layout 集成由主控做，你不要碰 Layout.tsx）

原来 C2–C5 是一个包，太大。拆成两个**只写新文件**的包，
最后由主控把三者拼进 `Layout.tsx`。这样两个包之间没有文件冲突。

### C-shell 的交付契约（C-render 不会改你的文件）

```tsx
// frontend/src/components/agent/AgentWindow.tsx
export interface AgentWindowProps {
  title?: string;
  onClose: () => void;
  children: React.ReactNode;         // 主控往里塞对话内容
  /** 头部右侧额外按钮（主控用来塞「历史」开关） */
  headerExtra?: React.ReactNode;
  /** 本地存储键前缀，测试时传不同值以免互相污染 */
  storageKey?: string;
}
export function AgentWindow(props: AgentWindowProps): JSX.Element;
```

行为要求：
- `position: fixed`，标题栏可拖动、右下角可 resize、松手 16px 内吸附屏幕边缘
- 位置/尺寸写 `localStorage`（键 `${storageKey}.rect`），刷新后恢复
- 最小 320×360、最大不超过视口 − 32
- 视口 < 768px 时退化为全屏抽屉，且**不写** localStorage
- 键盘可达：标题栏可聚焦，方向键移动 8px（无障碍 + 可测试）

```tsx
// frontend/src/components/agent/AgentSessionList.tsx
export interface AgentSessionListProps {
  sessions: SessionSummary[];
  activeId: string | null;
  onPick: (sid: string) => void;
  onDelete: (sid: string) => void;
  onNew: () => void;
}
export function AgentSessionList(props: AgentSessionListProps): JSX.Element;
```
- 每项：标题（空标题显示「未命名会话」）+ `message_count` 条 + 相对时间
- 当前会话高亮；悬停显示删除按钮
- 顶部「新对话」按钮
- 空列表给一句话，不要白屏

### C-render 的交付契约（C-shell 不会改你的文件）

```tsx
// frontend/src/components/agent/ChatMessage.tsx
import type { SessionMessage } from "@/lib/api";
export interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  meta?: SessionMessage["meta"];
  /** 流式中（显示光标/未完成态） */
  streaming?: boolean;
}
export function ChatMessage(props: ChatMessageProps): JSX.Element;
```
- `role=user` / `assistant` 视觉区分（不求花哨，左右或底色区分都行）
- markdown 渲染（**不要新增依赖**：手写最小渲染器，见下）
- `meta.thinking` 折叠块，默认收起，标题「思考过程（N 字）」
- `meta.tool_calls` 折叠块，每条显示工具名 + 参数 + 结果摘要
- 代码块右上角「复制」按钮（`navigator.clipboard`，失败静默）

```ts
// frontend/src/lib/agent-markdown.ts
export type MdBlock =
  | { type: "heading"; level: 1 | 2 | 3; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "code"; lang: string; code: string }
  | { type: "table"; head: string[]; rows: string[][] }
  | { type: "hr" };
export function parseMarkdown(src: string): MdBlock[];
```
- **纯函数 + 有测试**，不要在组件里内联正则
- 行内元素（`**粗体**` / `` `代码` `` / `[链接](url)`）单独导出：
  `export function parseInline(text: string): InlineSpan[]`
  `type InlineSpan = {type:"text"|"bold"|"code"|"link"; text:string; href?:string}`
- XSS 面：**不要**用 `dangerouslySetInnerHTML`。链接 href 里出现
  `javascript:` 一律降级成纯文本（写测试钉住）

---

# 执行结果（2026-10-23）

## 各包落地情况

| 包 | 结果 | 备注 |
|---|---|---|
| **B3** Run 软删 + 备注 | ✅ | `DELETE /runs/{id}` 软删、`/restore`、`/note`；前端行内备注 + 撤销条 |
| **B4** 研报归档 | ✅ | multipart 上传落 `workspace/reports/`、MIME 白名单、按 kind 预览、20MB 上限 |
| **D4** 宏观看板 | ✅ | 4 个端点真拿到数据（社融/中债曲线/回购/LPR），3 个如实降级（PMI/北向/两融）|
| **D5** 相关性换 LWC | ✅ | `MultiLineChart`（单 pane 多线）+ `correlation.overlay/rolling` → lwc |
| **A3** 模型选择 | ✅ | `pi --list-models` 现读 34 个；`setting` 表持久化；**下一条消息生效** |
| **C-shell** 浮窗 + 会话列表 | ✅ | 拖动/resize/16px 吸附/localStorage/窄屏抽屉 |
| **C-render** 对话渲染 | ✅（改造过）| 见下「与计划的偏离」 |

## 与计划的偏离（诚实记录）

### 1. C-render 手写的 markdown 解析器被删掉了

子代理写了一版 `lib/agent-markdown.ts`（220 行）+ 27 个测试。但仓库里**本来就有**
`react-markdown` + `remark-gfm`（`MyReports.tsx` 在用）。两套引擎并存必然导致
「同一个回答在研报页和对话页长得不一样」，而手写版还不支持嵌套列表/引用/斜体。

**处理**：保留 `ChatMessage` 的外壳（角色对齐 / 思考过程 / 工具调用 / 复制按钮），
正文换成 `react-markdown`；删掉 `agent-markdown.ts` 及其测试。
理由写在 `ChatMessage.tsx` 头注释里。

### 2. Layout 的 Agent 栏从「常驻右栏」变成「浮窗」

ROUND2-C1 与 ROUND3-C2 的诉求不相容（常驻栏要么占宽度，要么不是浮窗）。
按时间顺序，C2 更新，所以取浮窗。同时主画布永远拿满宽度。
`layout.test.tsx` 里 5 个「常驻栏」时代的契约用例被改写成浮窗契约。

### 3. D4 少了一半端点，是子代理跑完预算了

`pmi/social-financing/cn-yields` 实现完，`lpr/repo/northbound/margin` 没写。
主控补齐；其中 `repo` 与 `lpr` 的测试 fixture 本身自相矛盾（断言 12.2 但按数据
应得 13.2），已修正并加强为「乱序输入也能取到最新一条 + 只留 60 条」。

## 顺手修掉的三个真 bug

### ① `str(None)` 被当成有效月份
社融未发布月份的 `month` 是 `None`，`str(None)` = `"None"` 是**真值** →
凭空造出一个 `"None"` 数据点。图上表现为多一个尖峰。已改为先判 `None` 再 `str()`。

### ② `build_macro_router(store)` 不传 bridge → 生产路径全崩
`b = bridge`（None），每个端点都报 `'NoneType' object has no attribute 'invoke'`。
**测试全绿**（测试都显式注入 FakeBridge），只有真启动才暴露。
已改为 `b = bridge if bridge is not None else VendorBridge()` 并加日志。

### ③ loader 把模块级常量当示例调用剥掉（最严重）
旧规则「右值含任何 Call 就丢」把这三个一起埋了：
```
_TICKER_RE = re.compile(...)     → Ticker 归一化 NameError
EM_SESSION = requests.Session()  → 所有东财函数 NameError
_CN_TZ     = timezone(...)       → 时间戳解析 NameError
```
后果不是导入失败，而是能力「存在」但一调就崩 —— LPR 端点因此长期返回
`NameError: EM_SESSION`，而 loader 自己的 14 个测试全绿。

**新判据**看被调者是谁（裸名字 vs 属性调用、是否来自 import/内建/块内 def）。
第一次放宽时把「跨块取数函数」也放过了，加载从 0.36s 涨到 **99.6s**
（9 个块在 import 阶段真联网）。修好后 0.30s 且常量全部就位。

判据抽成 `strip_examples()` 纯函数暴露给测试 —— 早先测试直接调
`_is_example_fetch`，把**调用点**改坏（退回旧规则）测试依然全绿，
等于测了一个没人用的函数。

## 追加修掉的第四个 bug（验收时发现）

**`agentApi` 打错路由 → 界面谎报「还没有会话」。**

`agentApi.sessions()` 写的是 `/api/agent/sessions`，后端路由在 `/api/sessions`。
404 被调用方 `catch(() => setSessions([]))` 吞成空数组，界面于是理直气壮地
显示「还没有会话。发一句话就会自动开一个」，而库里躺着 **17 条**。

这是本批次里最危险的一类 bug：**不报错、不崩，只是把一个事实换成了相反的事实**。
之前的验收脚本还给了假绿 —— 它只检查「新对话按钮在不在」，而那个按钮与数据无关。

两处修改：
1. 路径改对（`/sessions`）
2. **「查不到」与「确实没有」分开**：`AgentSessionList` 新增 `error` prop，
   有错时显示错误原因，绝不显示「还没有会话」

回归测试：`lib/__tests__/agent-api.test.ts`（断言真实 URL）+ `AgentSessionList.test.tsx`
（有 error 时不能出现「还没有会话」）。两个方向的变异都能抓到。

## 遗留问题（未做 / 建议下一轮）

| # | 问题 | 说明 |
|---|---|---|
| 1 | **会话标题全是空串** | 库里 17 条会话 `title=''`，列表里全显示「未命名会话」，仍然挑不出来。需要「用第一条消息前 20 字自动命名」或允许用户改名。 |
| 2 | **Runs 的 diff 没有「变化显著」高亮** | 参数表只列差异项（够用），指标表给了 delta 但没有视觉强调，看不出「哪一个指标变化大」。 |
| 3 | **研报只有标题/标签过滤，没有全文检索** | `doc.text` 存了正文但没建索引；SQLite FTS5 可以做，属于新功能。 |
| 4 | **PMI / 北向 / 两融三个宏观项取不到** | 分别是：统计局页面改版、上游 2024-08 起停披露日频净买入、逐日逐所拉全市场成本不合理。都如实标注了原因，没有编数字。 |
| 5 | **A3 只验到「保存成功」** | 没有真跑一轮对话去证明「换模型后确实是新模型在答」（要消耗真实额度）。后端逻辑是建会话时 `resolve_model()` 现读，代码路径确定，但没有端到端证据。 |
| 6 | **MultiLineChart 的 0 基线对归一化叠加图无意义** | 那条 priceLine 在 0~110 的图上恒不可见，属无害噪音；要干净应当做成 prop。 |
| 7 | **`correlation.matrix` 仍是 ECharts** | 这是对的（热力图不是时间序列），但如果用户要「矩阵与走势联动十字光标」做不到。 |
