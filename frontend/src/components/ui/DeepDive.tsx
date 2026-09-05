// 「AI 深入分析」占位（S5 上线）。保留 useDeepDive / DeepDivePanel / RunAllButton / DiveItem
// 的导出与签名，让每日复盘连板表能编译；toggle 打开只显示"即将上线"，不调 llm、不做流式。
import { useState } from "react";
import { Sparkles } from "lucide-react";

// ---------- hook ----------
export interface DiveItem {
  key: string;
  prompt: string;
  context: string;
}

export interface DeepDiveState {
  open: string | null;
  analysis: Record<string, string>;
  tools: Record<string, string[]>;
  running: string | null;
  aiErr: string | null;
  needConfig: boolean;
  batch: { done: number; total: number; current: string } | null;
  toggle: (item: DiveItem) => void;
  rerun: (item: DiveItem) => void;
  runAll: (items: DiveItem[]) => void;
  stopAll: () => void;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function useDeepDive(_ns: string, _date: string): DeepDiveState {
  const [open, setOpen] = useState<string | null>(null);

  const toggle = (item: DiveItem) => {
    setOpen((cur) => (cur === item.key ? null : item.key));
  };

  return {
    open,
    analysis: {},
    tools: {},
    running: null,
    aiErr: null,
    needConfig: false,
    batch: null,
    toggle,
    rerun: () => {},
    runAll: () => {},
    stopAll: () => {},
  };
}

// ---------- 表格内展开行 ----------
interface PanelProps {
  dd: DeepDiveState;
  stockKey: string;
  colSpan: number;
  noteTitle: string;
  onRerun: () => void;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function DeepDivePanel({ dd: _dd, stockKey: _stockKey, colSpan, noteTitle: _noteTitle, onRerun: _onRerun }: PanelProps) {
  return (
    <tr className="border-b border-border/30 bg-primary/[0.03]">
      <td colSpan={colSpan} className="px-3 py-3">
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          AI 深入分析即将上线(S5)
        </div>
      </td>
    </tr>
  );
}

// ---------- 一键全部分析按钮（占位） ----------
interface RunAllProps {
  dd: DeepDiveState;
  items: DiveItem[];
  nameOf?: (key: string) => string;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function RunAllButton({ dd: _dd, items: _items, nameOf: _nameOf }: RunAllProps) {
  return (
    <button
      disabled
      title="AI 深入分析即将上线(S5)"
      className="inline-flex items-center gap-1 rounded-lg border border-primary/50 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary opacity-40"
    >
      <Sparkles className="h-3 w-3" />
      一键全部分析
    </button>
  );
}
