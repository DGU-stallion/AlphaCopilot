import { useCallback, useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import {
  Moon, Sun, ChevronsLeft, ChevronsRight, CandlestickChart, Cog,
  Activity, Globe, Star, FileText, TrendingDown, GitCompare, Briefcase,
  NotebookPen, ArrowUpDown, Clock3, History, X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDarkMode } from "@/hooks/useDarkMode";
import { AiPageProvider } from "@/lib/ai-page";
import { DataAsOfProvider, useDataAsOfValue, formatAsOf } from "@/lib/data-asof";
import { AiConsole } from "@/components/ai/AiConsole";
import { CommandBar } from "@/components/ai/CommandBar";
import { currentCaliber, setCaliber } from "@/theme/usePalette";
import { ROW } from "@/theme/tokens";
import { api } from "@/lib/api";

/**
 * 三区布局（M2-5 / ADR-0014 §8）。
 *
 *   ┌──────────────────────────────────────────────────┐
 *   │ 顶栏 48                                           │
 *   ├────────┬──────────────────────┬──────────────────┤
 *   │ 左导航 │  主画布              │  Agent 栏        │
 *   │176 / 52│  flex:1, minHeight:0 │  360 / 44        │
 *   ├────────┴──────────────────────┴──────────────────┤
 *   │ 底栏 28                                           │
 *   └──────────────────────────────────────────────────┘
 *
 * 为什么改成这样（而不是原来的「侧栏 + 浮层」）：
 * 原布局的 AI 是右下角浮起来的一个框，压住内容、要手动拖开、还会挡住表格最后一行。
 * 改成常驻可折叠的右侧栏，位置固定、宽度可预期，折叠后主画布自动变宽。
 *
 * 尺寸用**内联 style** 而不是 Tailwind 类：折叠动画要过渡 width，
 * 类名切换会丢掉过渡的起止值。同时 data-region 供测试定位结构。
 *
 * ⚠️ 主画布必须 minHeight:0 —— 否则 flex 子项不会真正压缩，
 * 图表会把父容器撑破（ADR-0014 §8 点名的坑）。
 */

// 导航分组。定位：确定性计算为主、AI 只解释。
const REVIEW_NAV = [
  { to: "/macro", icon: Globe, label: "宏观看板" },
  { to: "/daily-review", icon: Activity, label: "复盘看板" },
];
const RESEARCH_NAV = [
  { to: "/watchlist", icon: Star, label: "股票池" },
  { to: "/reports", icon: FileText, label: "我的研报" },
];
const QUANT_NAV = [
  // ADR-0016：回测/相关已迁到 spec 渲染（/p/:slug）。
  // 仍然指回同一个 slug，所以导航看起来没变，但底层不再是手写 TSX。
  { to: "/p/backtest", icon: TrendingDown, label: "回测" },
  { to: "/runs", icon: History, label: "Run 记录" },
  { to: "/p/correlation", icon: GitCompare, label: "相关性分析" },
  { to: "/portfolios", icon: Briefcase, label: "模拟组合" },
];
const SYSTEM_NAV = [
  { to: "/journal", icon: NotebookPen, label: "交易日志" },
  { to: "/settings", icon: Cog, label: "接入 AI" },
];

/**
 * 自定义页导航（ADR-0016）：库里 kind=user 的页面自动出现在这里。
 *
 * 为什么导航要动态而不是写死：页面现在是**数据**，agent 新建一个页面后
 * 用户应该立刻能看到入口，而不是「已经存在但你没地方点」。
 * 内置页（backtest/correlation）已直接写在 QUANT_NAV 里，不在此列。
 *
 * 带删除能力（`del`）：建页面的成本极低（agent 一条 POST），没有删除就
 * 只增不减，实验页会永久占着导航栏。
 */
function useUserPages() {
  const [pages, setPages] = useState<
    { id: string; slug: string; title: string }[]
  >([]);

  const load = useCallback(() => {
    api
      .pages()
      .then((rows) =>
        setPages(
          rows
            .filter((r) => r.kind === "user")
            .map((r) => ({ id: r.id, slug: r.slug, title: r.title })),
        ),
      )
      // 后端未起时不阻塞导航渲染 —— 自定义页看不到而已，不该把整个 UI 拖垮。
      .catch(() => { /* 静默降级 */ });
  }, []);

  useEffect(() => { load(); }, [load]);

  /**
   * 删除（软删）+ 撤销入口。
   *
   * 为什么不是「点一下就删完」：这条链路曾经是硬删除且无确认，我当时写的理由是
   * 「页面内容是 spec，可再生」——**那个理由是错的**，用户手写的页面不是可再生
   * 资源，实际造成一个自定义页被删后无法恢复。
   *
   * 现在两层保护：
   *   1. 后端软删（数据还在，可 restore）
   *   2. 前端给一个带「撤销」的提示条
   */
  const [undo, setUndo] = useState<{ id: string; title: string } | null>(null);

  const del = useCallback(
    async (id: string, title: string) => {
      await api.deletePage(id);
      setUndo({ id, title });
      load();
    },
    [load],
  );

  const undoDelete = useCallback(async () => {
    if (!undo) return;
    try {
      await api.restorePage(undo.id);
      setUndo(null);
      load();
    } catch {
      // 409 = slug 已被占用。保留提示条，让人看到「恢复不了」而不是静默失败。
    }
  }, [undo, load]);

  const dismissUndo = useCallback(() => setUndo(null), []);

  return { pages, del, undo, undoDelete, dismissUndo };
}

/** 底栏的数据时点（M5-4）：页面报告什么，这里就显示什么。 */
function AsOfBadge() {
  const info = useDataAsOfValue();
  const { text, stale } = formatAsOf(info);
  if (!info) return <span className="text-muted-foreground/60">as-of —</span>;
  return (
    <span
      className={cn("flex items-center gap-1", stale ? "text-[hsl(var(--warning))]" : "text-muted-foreground")}
      title={stale ? "这不是今天取到的数据，注意时效" : "数据时点"}
    >
      <Clock3 className="h-3 w-3" />
      {/* 数字必须等宽：时间戳跳动会让它旁边的按钮跟着位移 */}
      <span style={{ fontFamily: "var(--font-mono, monospace)" }}>as-of {text}</span>
    </span>
  );
}

const NAV_W = { open: 176, closed: 52 };
const TOPBAR_H = 48;

export function Layout() {
  const { pathname } = useLocation();
  const { dark, toggle } = useDarkMode();

  const [navClosed, setNavClosed] = useState(() => localStorage.getItem("ac-nav") === "closed");
  const [caliber, setCaliberState] = useState(currentCaliber);
  const userPages = useUserPages();

  useEffect(() => { localStorage.setItem("ac-nav", navClosed ? "closed" : "open"); }, [navClosed]);

  const flipCaliber = () => {
    const next = caliber === "cn" ? "intl" : "cn";
    setCaliber(next);
    setCaliberState(next);
  };

  const item = ({ to, icon: Icon, label }: { to: string; icon: LucideIcon; label: string }) => {
    const active = pathname === to;
    return (
      <Link
        key={to}
        to={to}
        title={navClosed ? label : undefined}
        className={cn(
          "flex items-center rounded-[4px] text-[13px] transition-colors",
          navClosed ? "justify-center py-2" : "gap-2 px-2.5 py-1.5",
          active
            ? "bg-[hsl(var(--muted))] font-medium text-foreground"
            : "text-muted-foreground hover:bg-[hsl(var(--muted))] hover:text-foreground",
        )}
      >
        <Icon className="h-[15px] w-[15px] shrink-0" />
        {!navClosed && label}
      </Link>
    );
  };

  const groupLabel = (text: string) =>
    !navClosed && (
      <div className="mb-1 mt-3 px-2.5 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground/70 first:mt-0">
        {text}
      </div>
    );

  return (
    <DataAsOfProvider>
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      {/* ---------------- 顶栏 48 ---------------- */}
      <header
        className="flex shrink-0 items-center gap-3 border-b border-border px-4"
        style={{ height: TOPBAR_H }}
      >
        <Link to="/daily-review" className="flex items-center gap-2">
          <CandlestickChart className="h-[18px] w-[18px] text-primary" />
          <span className="text-[16px] font-semibold tracking-tight">
            Alpha<span className="text-primary">Copilot</span>
          </span>
        </Link>
        <div className="h-4 w-px bg-border" />
        <span className="text-[11px] text-muted-foreground">个人量化投研工作台</span>

        <button
          onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))}
          className="ml-auto flex items-center gap-1.5 rounded-[4px] border border-border px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:border-[hsl(var(--primary))] hover:text-foreground"
          title="打开命令栏（⌘K）"
        >
          <span>问 AI</span>
          <kbd className="rounded-[2px] border border-border px-1 text-[11px]">⌘K</kbd>
        </button>
        <div className="flex items-center gap-1">
          <button
            onClick={toggle}
            title={dark ? "切到亮色" : "切到暗色"}
            className="rounded-[4px] p-1.5 text-muted-foreground transition-colors hover:bg-[hsl(var(--muted))] hover:text-foreground"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
      </header>

      {/* ---------------- 三区 ---------------- */}
      <div className="flex min-h-0 flex-1">
        {/* 左导航 */}
        <aside
          data-region="nav"
          className="flex shrink-0 flex-col border-r border-border bg-[hsl(var(--card))]"
          style={{ width: navClosed ? NAV_W.closed : NAV_W.open, transition: "width 160ms ease" }}
        >
          <nav className={cn("flex-1 overflow-auto", navClosed ? "p-1.5" : "p-2.5")}>
            {groupLabel("市场复盘")}
            {REVIEW_NAV.map((n) => item(n))}

            {!navClosed && <div className="my-2 border-t border-border" />}
            {groupLabel("研究管理")}
            {RESEARCH_NAV.map((n) => item(n))}

            {!navClosed && <div className="my-2 border-t border-border" />}
            {groupLabel("量化研究")}
            {QUANT_NAV.map((n) => item(n))}

            {!navClosed && <div className="my-2 border-t border-border" />}
            {groupLabel("个人与系统")}
            {SYSTEM_NAV.map((n) => item(n))}

            {/* 自定义页（ADR-0016）：库里 kind=user 的页面自动出现。
                空时不显示分组标题，避免一条空行占位。
                悬停显删除按钮：建页成本极低（agent 一条 POST），没有删除就只增不减。 */}
            {userPages.pages.length > 0 && (
              <>
                {!navClosed && <div className="my-2 border-t border-border" />}
                {groupLabel("自定义页")}
                {userPages.pages.map((u) => {
                  const active = pathname === `/p/${u.slug}`;
                  return (
                    <div key={u.id} className="group/u relative flex items-center">
                      <Link
                        to={`/p/${u.slug}`}
                        title={navClosed ? u.title : undefined}
                        className={cn(
                          "flex flex-1 items-center rounded-[4px] text-[13px] transition-colors",
                          navClosed ? "justify-center py-2" : "gap-2 px-2.5 py-1.5 pr-7",
                          active
                            ? "bg-[hsl(var(--muted))] font-medium text-foreground"
                            : "text-muted-foreground hover:bg-[hsl(var(--muted))] hover:text-foreground",
                        )}
                      >
                        <FileText className="h-[15px] w-[15px] shrink-0" />
                        {!navClosed && <span className="truncate">{u.title}</span>}
                      </Link>
                      {/* 折叠态没有空间放删除按钮，所以只在展开时出现。 */}
                      {!navClosed && (
                        <button
                          onClick={() => {
                            // 不弹 modal 确认，但**不是**无保护：
                            // 后端是软删（可 restore），前端给带「撤销」的提示条。
                            // 比 modal 少一次点击，又留了后悔的余地。
                            void userPages.del(u.id, u.title).catch(() => { /* 失败时列表不刷 */ });
                          }}
                          title={`删除「${u.title}」`}
                          aria-label={`删除 ${u.title}`}
                          className="absolute right-1 rounded-[2px] p-1 text-muted-foreground/0 transition-colors group-hover/u:text-muted-foreground/70 hover:!text-danger"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  );
                })}
              </>
            )}
          </nav>

          <div className={cn("border-t border-border", navClosed ? "flex flex-col items-center gap-1 p-1.5" : "p-2")}>
            <button
              onClick={() => setNavClosed((c) => !c)}
              title={navClosed ? "展开导航" : "收起导航"}
              className={cn(
                "flex items-center gap-1.5 rounded-[4px] text-[11px] text-muted-foreground transition-colors hover:bg-[hsl(var(--muted))] hover:text-foreground",
                navClosed ? "p-1.5" : "w-full px-2 py-1",
              )}
            >
              {navClosed ? <ChevronsRight className="h-[15px] w-[15px]" /> : <><ChevronsLeft className="h-[15px] w-[15px]" /> 收起</>}
            </button>
          </div>
        </aside>

        {/* 主画布 */}
        <AiPageProvider>
          <main
            data-region="canvas"
            className="min-w-0 flex-1 overflow-auto"
            style={{ minHeight: 0, minWidth: 0 }}
          >
            {/* 内边距放在这里而不是每个页面各写一份：10 个页面统一呼吸感，
                也避免某个页面忘了加导致内容贴边。数据密集页不用 max-w 限宽
                （表格列多时限宽反而更难读）。 */}
            <div className="px-5 py-4">
              <Outlet />
            </div>
          </main>

          {/* Agent 栏已改为**浮窗**（ROUND3 C2），不再占布局宽度。

              ROUND2 时它是右侧常驻 aside，折叠后收成 44px 竖条；用户反馈
              「折叠后仍占右侧空间」，于是 C1 改成「折叠即完全退出布局」。
              ROUND3 又要求「浮窗可拖动/resize/吸附」，这两条与常驻栏不相容：
              常驻栏要么占宽度，要么就不是浮窗。所以整块从布局里移出去，
              由 AiConsole 自己渲染 fixed 浮层（位置/尺寸记在 localStorage）。
              附带好处：主画布永远拿满宽度，宽表格不再出横向滚动。 */}
        </AiPageProvider>

        {/* 助手浮层（ROUND3 C2/C3/C4/C5）。
            放在 Provider 内部才拿得到「当前页确定性数据快照」作对话上下文。 */}
        <AiConsole />
      </div>

      {/* ---------------- 底栏 28 ---------------- */}
      <footer
        data-region="bottom"
        className="flex shrink-0 items-center gap-3 border-t border-border bg-[hsl(var(--card))] px-4 text-[11px] text-muted-foreground"
        style={{ height: ROW.compact }}
      >
        <span>本地 · data-service</span>
        <AsOfBadge />
        <button
          onClick={flipCaliber}
          className="flex items-center gap-1 rounded-[2px] px-1 py-0.5 transition-colors hover:bg-[hsl(var(--muted))] hover:text-foreground"
          title="切换涨跌配色口径"
        >
          <ArrowUpDown className="h-3 w-3" />
          口径：{caliber === "cn" ? "涨红跌绿" : "涨绿跌红"}
        </button>
        <span className="ml-auto">v2 · M2</span>
      </footer>

      {/* 删除后的撤销提示（ROUND2 §9）。软删 + 撤销，替代确认弹窗：
          确认弹窗能防「手滑」，但防不了「确认了才发现想错了」。
          撤销能防后者，且不打断操作流。 */}
      {userPages.undo && (
        <div
          role="status"
          className="fixed bottom-10 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-[4px] border border-border bg-[hsl(var(--card))] px-3 py-2 text-[12px]"
        >
          <span className="text-muted-foreground">
            已删除「{userPages.undo.title}」
          </span>
          <button
            onClick={() => void userPages.undoDelete()}
            className="font-medium text-primary hover:underline"
          >
            撤销
          </button>
          <button
            onClick={() => userPages.dismissUndo()}
            aria-label="关闭提示"
            className="text-muted-foreground/60 hover:text-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      {/* ⌘K 命令栏（M5-1）：全局入口，与右侧助手共用同一个对话 */}
      <CommandBar />
    </div>
    </DataAsOfProvider>
  );
}

/** 供别处引用的一致尺寸常量（避免各页面各写一个数）。 */
export const LAYOUT_SIZE = { NAV_W, TOPBAR_H };
