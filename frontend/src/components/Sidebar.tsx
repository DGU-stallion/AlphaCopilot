/**
 * Sidebar — 左侧可收展 tab 栏（ADR-0007 决策 1）。
 *
 * 收展状态持久化到 localStorage。tab 项默认用静态占位（每日复盘、相关性分析），
 * 但通过 `pages` prop 注入，为后续 usePages 数据驱动留出接口位——不写死组件级页面。
 */

import { useCallback, useEffect, useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/cn";
import { usePages } from "@/hooks/usePages";

export interface PageTab {
  slug: string;
  label: string;
  /** 专用业务页用绝对路径（如 /stock-pool）；page-spec 页省略，走 /pages/{slug}。 */
  path?: string;
}

/** 第一版固定 tab（ADR-0008）。分析页走 /pages/{slug}；业务页走专用 path。 */
export const DEFAULT_TABS: PageTab[] = [
  { slug: "daily-review", label: "复盘看板" },
  { slug: "market", label: "盘面数据" },
  { slug: "limit-up-stats", label: "涨停样本统计" },
  { slug: "stock-pool", label: "股票池", path: "/stock-pool" },
  { slug: "correlation", label: "相关性分析" },
  { slug: "journal", label: "交易日志", path: "/journal" },
  { slug: "reports", label: "我的研报", path: "/reports" },
];

const BUSINESS_SLUGS = new Set(["stock-pool", "journal", "reports"]);

const STORAGE_KEY = "alphacopilot-sidebar-collapsed";

export function Sidebar({ pages }: { pages?: PageTab[] }) {
  const dynamic = usePages();
  // builtin/业务页固定在前；动态页去重后追加（数据驱动，AGENTS 硬规则 6）。
  // 动态页里若与固定 tab 或业务 slug 重名则跳过（避免 market/limit-up-stats 重复出现）。
  const tabs: PageTab[] =
    pages ??
    [
      ...DEFAULT_TABS,
      ...dynamic
        .filter(
          (d) =>
            !DEFAULT_TABS.some((b) => b.slug === d.slug) && !BUSINESS_SLUGS.has(d.slug),
        )
        .map((d) => ({ slug: d.slug, label: d.title })),
    ];

  const [collapsed, setCollapsed] = useState<boolean>(
    () => localStorage.getItem(STORAGE_KEY) === "1",
  );

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  const toggle = useCallback(() => setCollapsed((c) => !c), []);

  return (
    <aside
      className={cn(
        "glass m-2 flex shrink-0 flex-col gap-1 rounded-lg p-3 transition-[width]",
        collapsed ? "w-16" : "w-56",
      )}
      data-collapsed={collapsed}
    >
      <div className="mb-4 flex items-center justify-between">
        {!collapsed && (
          <span className="px-2 text-lg font-semibold text-primary">AlphaCopilot</span>
        )}
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"}
          className="glass flex h-9 w-9 items-center justify-center rounded-md text-foreground/80 transition-colors hover:text-primary"
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>
      <nav className="flex flex-col gap-1">
        {tabs.map((p) => (
          <NavLink
            key={p.slug}
            to={p.path ?? `/pages/${p.slug}`}
            title={p.label}
            className={({ isActive }) =>
              cn(
                "rounded-md px-3 py-2 text-sm transition-colors",
                collapsed && "text-center",
                isActive
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
              )
            }
          >
            {collapsed ? p.label.slice(0, 1) : p.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
