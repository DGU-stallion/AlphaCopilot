import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface Props {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}

// 面板：设计系统 v2（ADR-0014）的基础容器 —— 实色底 + 发丝边框 + 6px 圆角。
// 前身是 GlassCard（玻璃拟态）；ADR-0013 §5 清理后层次只靠同色相灰阶与边框，
// 不再使用半透明填充 / 内高光 / 柔投影。视觉真源在 theme/tokens.ts，
// 颜色经 index.css 的语义变量（--card / --border）接入双主题。
export function Panel({ children, className, onClick }: Props) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "rounded-[6px] border border-border bg-card p-5",
        onClick && "cursor-pointer transition-transform hover:-translate-y-0.5",
        className,
      )}
    >
      {children}
    </div>
  );
}
