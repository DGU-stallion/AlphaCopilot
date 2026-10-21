import { type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes, forwardRef } from "react";
import { RADIUS, SIZE } from "@/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * 表单控件（ADR-0014 §5）。
 *
 * 为什么要有这三个组件：改造前 7 个页面各写各的 input 类名，
 * 出现 `rounded-lg` / `bg-black/20` / 各种 px-3 py-2 混用 ——
 * 同一个应用里的输入框圆角、高度、底色都不一样，用户会觉得"没做完"。
 *
 * 统一到：高 28（CONTROL_MD）、圆角 4、实色 panel 底、聚焦时边框变 accent。
 * 高度走 token 而不是类名，因为 antd 的 controlHeight 也是 28，两边要对齐。
 */

const base =
  "w-full border bg-[hsl(var(--card))] text-foreground outline-none transition-colors " +
  "placeholder:text-muted-foreground/60 " +
  "focus:border-[hsl(var(--primary))] disabled:opacity-50";

const sizing = "px-2.5 text-[13px]";
const shape = { borderRadius: RADIUS.md, borderColor: "hsl(var(--border))" };

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, style, ...rest }, ref) => (
    <input
      ref={ref}
      className={cn(base, sizing, "h-7", className)}
      style={{ ...shape, ...style }}
      {...rest}
    />
  ),
);
TextInput.displayName = "TextInput";

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, style, ...rest }, ref) => (
    <textarea
      ref={ref}
      className={cn(base, sizing, "py-1.5 resize-y", className)}
      style={{ ...shape, minHeight: 56, ...style }}
      {...rest}
    />
  ),
);
TextArea.displayName = "TextArea";

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, style, children, ...rest }, ref) => (
    <select
      ref={ref}
      className={cn(base, sizing, "h-7 cursor-pointer", className)}
      style={{ ...shape, ...style }}
      {...rest}
    >
      {children}
    </select>
  ),
);
Select.displayName = "Select";

/** 表单项：标签在上、控件在下，标签固定 11px（与表头同字号）。 */
export function Field({
  label, hint, children, className,
}: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn("block min-w-0", className)}>
      <span className="mb-1 block text-muted-foreground" style={{ fontSize: SIZE.xs }}>{label}</span>
      {children}
      {hint && <span className="mt-0.5 block text-muted-foreground/60" style={{ fontSize: SIZE.xs }}>{hint}</span>}
    </label>
  );
}

/** 主按钮 / 次级按钮。高度与控制件对齐（28）。 */
export function Button({
  variant = "primary", className, children, ...rest
}: InputHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" }) {
  return (
    <button
      className={cn(
        "inline-flex h-7 shrink-0 items-center justify-center gap-1.5 px-3 text-[13px] transition-colors",
        variant === "primary"
          ? "bg-[hsl(var(--primary))] font-medium text-[hsl(var(--primary-foreground))] hover:opacity-90"
          : "border border-border text-muted-foreground hover:bg-[hsl(var(--muted))] hover:text-foreground",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      style={{ borderRadius: RADIUS.md }}
      {...(rest as Record<string, unknown>)}
    >
      {children}
    </button>
  );
}
