// 「问 AI」入口 —— AI 助手占位（S5 上线）。保留 props(context/suggestions/label)，
// 点击弹出"即将上线"提示，不调 chatStream。接入 AI 时恢复原流式对话面板。
import { Sparkles } from "lucide-react";
import { toast } from "sonner";

interface Props {
  context: string;
  suggestions?: string[];
  label?: string;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function AskAiButton({ context: _context, suggestions: _suggestions = [], label = "问 AI" }: Props) {
  return (
    <button
      onClick={() => toast("AI 助手即将上线(S5)")}
      className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-3 py-1.5 text-sm font-medium text-primary shadow-glow transition-colors hover:bg-primary/25"
    >
      <Sparkles className="h-4 w-4" />
      {label}
    </button>
  );
}
