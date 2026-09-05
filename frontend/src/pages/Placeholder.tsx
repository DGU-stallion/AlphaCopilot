import { Construction } from "lucide-react";

// 尚未搬运的页面占位：避免侧边栏点击 404。逐页从 vibe-astock 缝合过来后替换。
export function Placeholder({ title }: { title: string }) {
  return (
    <div className="glass mt-6 flex flex-col items-center justify-center rounded-2xl py-24 text-center text-muted-foreground">
      <Construction className="mb-3 h-8 w-8 text-primary/70" />
      <div className="text-lg font-semibold text-foreground">{title}</div>
      <div className="mt-1 text-sm">该页面即将上线</div>
    </div>
  );
}
