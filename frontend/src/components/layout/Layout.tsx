import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import {
  Moon, Sun, ChevronsLeft, ChevronsRight, CandlestickChart, Cog,
  Activity, Globe, Star, FileText, TrendingDown, GitCompare, Briefcase,
  NotebookPen, Sparkles, PanelRightClose, ArrowUpDown, Clock3, History, GitBranch, Hammer,
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
  { to: "/research", icon: GitBranch, label: "研究线" },
  { to: "/reports", icon: FileText, label: "我的研报" },
];
const QUANT_NAV = [
  { to: "/quant-backtest", icon: TrendingDown, label: "回测" },
  { to: "/runs", icon: History, label: "Run 记录" },
  { to: "/correlation", icon: GitCompare, label: "相关性分析" },
  { to: "/portfolios", icon: Briefcase, label: "模拟组合" },
];
const SYSTEM_NAV = [
  { to: "/journal", icon: NotebookPen, label: "交易日志" },
  { to: "/build", icon: Hammer, label: "Build" },
  { to: "/settings", icon: Cog, label: "接入 AI" },
];

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
const AGENT_W = { open: 360, closed: 44 };
const TOPBAR_H = 48;

export function Layout() {
  const { pathname } = useLocation();
  const { dark, toggle } = useDarkMode();

  const [navClosed, setNavClosed] = useState(() => localStorage.getItem("ac-nav") === "closed");
  const [agentClosed, setAgentClosed] = useState(() => localStorage.getItem("ac-agent") === "closed");
  const [caliber, setCaliberState] = useState(currentCaliber);

  useEffect(() => { localStorage.setItem("ac-nav", navClosed ? "closed" : "open"); }, [navClosed]);
  useEffect(() => { localStorage.setItem("ac-agent", agentClosed ? "closed" : "open"); }, [agentClosed]);

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
      <div className="mb-1 mt-3 px-2.5 text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground/70 first:mt-0">
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
          <span className="text-[14px] font-semibold tracking-tight">
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
          <kbd className="rounded-[2px] border border-border px-1 text-[10px]">⌘K</kbd>
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

          {/* Agent 栏 */}
          <aside
            data-region="agent"
            className="flex shrink-0 flex-col border-l border-border bg-[hsl(var(--card))]"
            style={{ width: agentClosed ? AGENT_W.closed : AGENT_W.open, transition: "width 160ms ease" }}
          >
            <div
              className="flex shrink-0 items-center border-b border-border px-3"
              style={{ height: TOPBAR_H }}
            >
              {agentClosed ? (
                <button
                  onClick={() => setAgentClosed(false)}
                  title="展开助手"
                  className="mx-auto rounded-[4px] p-1.5 text-muted-foreground transition-colors hover:bg-[hsl(var(--muted))] hover:text-foreground"
                >
                  <Sparkles className="h-4 w-4" />
                </button>
              ) : (
                <>
                  <Sparkles className="h-4 w-4 text-primary" />
                  <span className="ml-2 text-[13px] font-medium">助手</span>
                  <button
                    onClick={() => setAgentClosed(true)}
                    title="收起助手"
                    className="ml-auto rounded-[4px] p-1.5 text-muted-foreground transition-colors hover:bg-[hsl(var(--muted))] hover:text-foreground"
                  >
                    <PanelRightClose className="h-4 w-4" />
                  </button>
                </>
              )}
            </div>
            {!agentClosed && (
              <div className="min-h-0 flex-1" style={{ minHeight: 0 }}>
                <AiConsole embedded />
              </div>
            )}
          </aside>
        </AiPageProvider>
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

      {/* ⌘K 命令栏（M5-1）：全局入口，与右侧助手共用同一个对话 */}
      <CommandBar />
    </div>
    </DataAsOfProvider>
  );
}

/** 供别处引用的一致尺寸常量（避免各页面各写一个数）。 */
export const LAYOUT_SIZE = { NAV_W, AGENT_W, TOPBAR_H };
