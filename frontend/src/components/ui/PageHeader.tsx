import { type ReactNode } from "react";
import { SIZE } from "@/theme/tokens";
import { cn } from "@/lib/utils";

interface Props {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  /**
   * 数据时点/口径说明，显示在副标题右侧的等宽小字里
   * （如「data as-of 2026-10-21 15:00」）。数字必须等宽，避免时间戳跳动。
   */
  meta?: ReactNode;
}

/**
 * 页面标题栏。
 *
 * 字号走 token（ADR-0014 §5）：页标 16，副标 12，不用 24px 特粗 ——
 * 那是营销页的表达，数据终端里标题抢眼会压住数据本身。
 *
 * 纵向留白比原来小（mb-4 而非 mb-6）：一屏内要放更多数据，
 * 每个页面顶部省下的 8px 累积起来是可观的。
 */
export function PageHeader({ title, subtitle, actions, meta }: Props) {
  return (
    <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="font-semibold tracking-tight" style={{ fontSize: SIZE.lg }}>{title}</h1>
          {meta && (
            <span
              className="text-muted-foreground"
              style={{ fontSize: SIZE.xs, fontFamily: "var(--font-mono, monospace)" }}
            >
              {meta}
            </span>
          )}
        </div>
        {subtitle && (
          <div className={cn("mt-0.5 text-muted-foreground")} style={{ fontSize: SIZE.sm }}>
            {subtitle}
          </div>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
