import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import {
  Moon, Sun, ChevronsLeft, ChevronsRight, CandlestickChart, Cog,
  Activity, Globe, Star, FileText, TrendingDown, GitCompare, Briefcase,
  NotebookPen } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDarkMode } from "@/hooks/useDarkMode";
import { AiPageProvider } from "@/lib/ai-page";
import { AiDockFab } from "@/components/ui/AiDockFab";

// AlphaCopilot 导航（见 CONTEXT.md「导航分组（第一版）」）。
// 定位：确定性计算为主、AI 只解释。全局 Agent 浮标独立于分组，覆盖在所有页面之上。

// 市场复盘：以人工阅读判断为主，数据确定性产出。
// 复盘看板 = 盘面数据（指数/外围/情绪/连板梯队/成交额/板块资金一屏看全）。
const REVIEW_NAV = [
  { to: "/macro", icon: Globe, label: "宏观看板" },
  { to: "/daily-review", icon: Activity, label: "复盘看板" },
];

// 研究管理：本机状态型业务页。
const RESEARCH_NAV = [
  { to: "/watchlist", icon: Star, label: "股票池" },
  { to: "/reports", icon: FileText, label: "我的研报" },
];

// 量化研究：程序化确定性 Python 计算。
const QUANT_NAV = [
  { to: "/quant-backtest", icon: TrendingDown, label: "回测" },
  { to: "/correlation", icon: GitCompare, label: "相关性分析" },
  { to: "/portfolios", icon: Briefcase, label: "模拟组合" },
];

// 个人与系统。⛔ 交易日志的数据只在本机流动。
const SYSTEM_NAV = [
  { to: "/journal", icon: NotebookPen, label: "交易日志" },
  { to: "/settings", icon: Cog, label: "接入 AI" },
];

export function Layout() {
  const { pathname } = useLocation();
  const { dark, toggle } = useDarkMode();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("ac-sidebar") === "collapsed");

  useEffect(() => {
    localStorage.setItem("ac-sidebar", collapsed ? "collapsed" : "expanded");
  }, [collapsed]);

  const item = ({ to, icon: Icon, label }: { to: string; icon: LucideIcon; label: string }) => {
    const active = pathname === to;
    return (
      <Link
        key={to}
        to={to}
        title={collapsed ? label : undefined}
        className={cn(
          "flex items-center rounded-lg text-sm transition-colors",
          collapsed ? "justify-center p-2.5" : "gap-2.5 px-3 py-2.5",
          active
            ? "bg-primary/15 font-medium text-primary shadow-glow"
            : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
        )}
      >
        <Icon className="h-4 w-4 shrink-0" />
        {!collapsed && label}
      </Link>
    );
  };

  const groupLabel = (text: string) =>
    !collapsed && (
      <div className="mb-1 mt-3 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/60 first:mt-0">{text}</div>
    );

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className={cn(
        "glass z-10 m-2 flex shrink-0 flex-col rounded-2xl transition-all duration-200",
        collapsed ? "w-14" : "w-60",
      )}>
        {/* Brand */}
        <div className={cn("border-b border-border/50", collapsed ? "flex justify-center p-3" : "p-4")}>
          <Link to="/daily-review" className={cn("flex items-center", collapsed ? "justify-center" : "gap-2")}>
            <CandlestickChart className="h-6 w-6 shrink-0 text-primary text-glow" />
            {!collapsed && <span className="text-lg font-extrabold tracking-tight">Alpha<span className="text-primary">Copilot</span></span>}
          </Link>
          {!collapsed && <p className="mt-1 text-[11px] text-muted-foreground">个人量化投研工作台</p>}
        </div>

        {/* Nav */}
        <nav className={cn("flex-1 space-y-0.5 overflow-auto", collapsed ? "p-1.5" : "p-2.5")}>
          {groupLabel("市场复盘")}
          {REVIEW_NAV.map((n) => item(n))}

          {!collapsed && <div className="my-2 border-t border-border/40" />}
          {groupLabel("研究管理")}
          {RESEARCH_NAV.map((n) => item(n))}

          {!collapsed && <div className="my-2 border-t border-border/40" />}
          {groupLabel("量化研究")}
          {QUANT_NAV.map((n) => item(n))}

          {!collapsed && <div className="my-2 border-t border-border/40" />}
          {groupLabel("个人与系统")}
          {SYSTEM_NAV.map((n) => item(n))}
        </nav>

        {/* Footer */}
        <div className={cn("border-t border-border/50", collapsed ? "flex flex-col items-center gap-2 p-2" : "space-y-2 p-3")}>
          {collapsed ? (
            <>
              <button onClick={toggle} className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title={dark ? "亮色" : "暗色"}>
                {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
              <button onClick={() => setCollapsed(false)} className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title="展开">
                <ChevronsRight className="h-4 w-4" />
              </button>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <button onClick={toggle} className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground">
                  {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
                  {dark ? "亮色" : "暗色"}
                </button>
                <button onClick={() => setCollapsed(true)} className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground" title="收起">
                  <ChevronsLeft className="h-3.5 w-3.5" />
                </button>
              </div>
            </>
          )}
        </div>
      </aside>

      {/* Main */}
      <AiPageProvider>
        <main className="flex-1 overflow-auto">
          <div className="mx-auto max-w-6xl px-6 py-6">
            <Outlet />
          </div>
        </main>
        {/* 全局 AI 浮标：覆盖所有页面，页面感知见 lib/ai-page */}
        <AiDockFab />
      </AiPageProvider>
    </div>
  );
}
