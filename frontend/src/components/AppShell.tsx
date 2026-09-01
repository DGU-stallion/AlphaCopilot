/**
 * AppShell — 全站骨架：侧边栏导航 + 主题切换 + 内容出口（Outlet）。
 * 后期换风格只需改 token 或本文件（PLAN：~6 个组件之一）。
 */

import { Moon, Sun } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { cn } from "@/lib/cn";
import { useTheme } from "@/theme";

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="切换主题"
      className="glass flex h-9 w-9 items-center justify-center rounded-md text-foreground/80 hover:text-primary transition-colors"
    >
      {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}

const NAV = [
  { to: "/", label: "对话" },
  { to: "/pages", label: "展示页" },
];

export function AppShell() {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <aside className="glass m-2 flex w-56 shrink-0 flex-col gap-1 rounded-lg p-3">
        <div className="mb-4 px-2 text-lg font-semibold text-primary">
          AlphaCopilot
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                )
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto flex items-center justify-between px-1 pt-3">
          <span className="text-xs text-muted-foreground">主题</span>
          <ThemeToggle />
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden p-2">
        <Outlet />
      </main>
    </div>
  );
}
