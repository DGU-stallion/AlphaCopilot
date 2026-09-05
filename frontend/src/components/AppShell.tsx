/**
 * AppShell — 页面驱动骨架（ADR-0007 决策 1）：
 * 左侧可收展 tab 栏 + 主区 Outlet + 右下浮标唤出的右侧 slide-in chat panel。
 *
 * 会话状态与 SSE 生命周期由 SessionProvider 持有并包在 AppShell 外层，
 * 浮标开/关 panel 不销毁会话（panel 卸载，context 仍在）。
 */

import { useState } from "react";
import { MessageCircle, Moon, Sun } from "lucide-react";
import { Outlet } from "react-router-dom";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { Sidebar } from "@/components/Sidebar";
import { SessionProvider } from "@/session-context";
import { useTheme } from "@/theme";

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="切换主题"
      className="glass flex h-9 w-9 items-center justify-center rounded-md text-foreground/80 transition-colors hover:text-primary"
    >
      {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}

export function AppShell() {
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <SessionProvider>
      <div className="flex h-screen w-screen overflow-hidden">
        <Sidebar />
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden p-2">
          <div className="flex justify-end p-1">
            <ThemeToggle />
          </div>
          <div className="min-h-0 flex-1">
            <Outlet />
          </div>
        </main>

        {/* 右下浮标：唤出右侧 chat panel */}
        <button
          type="button"
          onClick={() => setChatOpen((o) => !o)}
          aria-label="对话"
          className="glass fixed bottom-6 right-6 z-20 flex h-12 w-12 items-center justify-center rounded-full text-primary transition-colors hover:text-accent"
        >
          <MessageCircle size={22} />
        </button>

        {/* panel 只在开时挂载；会话状态在 SessionProvider，卸载不丢 */}
        {chatOpen && <ChatPanel onClose={() => setChatOpen(false)} />}
      </div>
    </SessionProvider>
  );
}
