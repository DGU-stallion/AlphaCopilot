// 「接入 AI」页（S5）—— AI 助手的运行说明 + 连通状态自检。
//
// 定位：AlphaCopilot 的 AI 助手由**后端**统一接入（dsh SDK + agnes 端点 + 项目专属
// profile alphacopilot-prod），前端不配置、不持有模型 key。本页因此不是"填 key"的表单，
// 而是：说明它怎么工作、做一次连通自检、讲清合规边界。

import { useState } from "react";
import { Sparkles, CheckCircle2, XCircle, Loader2, ShieldCheck, MessageSquare } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { apiUrl } from "@/lib/base";
import { authHeaders } from "@/lib/api";

type Probe = { state: "idle" | "checking" | "ok" | "fail"; detail?: string };

export function Settings() {
  const [probe, setProbe] = useState<Probe>({ state: "idle" });

  // 连通自检：建一个会话即证明后端会话运行时可达（不消耗模型额度）。
  const check = async () => {
    setProbe({ state: "checking" });
    try {
      const resp = await fetch(apiUrl("/api/sessions"), { method: "POST", headers: { ...authHeaders() } });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setProbe({ state: "ok", detail: `会话运行时可达（session ${data.session_id}）` });
    } catch (e) {
      setProbe({ state: "fail", detail: e instanceof Error ? e.message : String(e) });
    }
  };

  const Row = ({ k, v }: { k: string; v: string }) => (
    <div className="flex items-baseline justify-between gap-4 border-b border-border/40 py-2 last:border-0">
      <span className="text-sm text-muted-foreground">{k}</span>
      <span className="text-right font-mono text-sm text-foreground">{v}</span>
    </div>
  );

  return (
    <div>
      <PageHeader
        title="接入 AI"
        subtitle="AI 助手的运行方式、连通自检与合规边界"
      />

      {/* 运行状态 */}
      <GlassCard className="mb-4 p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="h-4 w-4 text-primary" /> 运行配置
        </h3>
        <Row k="接入方式" v="dsh SDK（本地运行时）" />
        <Row k="模型端点" v="agnes（apihub.agnes-ai.com）" />
        <Row k="模型" v="agnes-2.5-flash" />
        <Row k="Profile" v="alphacopilot-prod" />
        <Row k="可用工具" v="run_python · get_quote · submit_backtest" />
        <p className="mt-3 text-xs text-muted-foreground">
          模型密钥由后端统一持有（不在浏览器保存、不经前端传输），因此本页无需填写任何 key。
        </p>
      </GlassCard>

      {/* 连通自检 */}
      <GlassCard className="mb-4 p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <CheckCircle2 className="h-4 w-4 text-primary" /> 连通自检
        </h3>
        <div className="flex items-center gap-3">
          <button
            onClick={check}
            disabled={probe.state === "checking"}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-3.5 py-2 text-sm text-primary transition-colors hover:bg-primary/25 disabled:opacity-50"
          >
            {probe.state === "checking" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
            检查后端连通
          </button>
          {probe.state === "ok" && (
            <span className="inline-flex items-center gap-1.5 text-sm text-success">
              <CheckCircle2 className="h-4 w-4" /> {probe.detail}
            </span>
          )}
          {probe.state === "fail" && (
            <span className="inline-flex items-center gap-1.5 text-sm text-destructive">
              <XCircle className="h-4 w-4" /> 不可达：{probe.detail}（确认后端已启动）
            </span>
          )}
        </div>
      </GlassCard>

      {/* 怎么用 */}
      <GlassCard className="mb-4 p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <MessageSquare className="h-4 w-4 text-primary" /> 怎么用
        </h3>
        <ul className="space-y-2 text-sm text-muted-foreground">
          <li>· 点右下角 <span className="text-primary">✦</span> 浮标打开对话面板，面板可拖左上角调整大小。</li>
          <li>· 每页会把本页的确定性数据快照作为上下文，AI 就着当前页面的数据为你解释。</li>
          <li>· AI 可自主调用 run_python 在沙箱里做计算/画图、查行情、提交回测任务。</li>
        </ul>
      </GlassCard>

      {/* 合规边界 */}
      <GlassCard className="p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <ShieldCheck className="h-4 w-4 text-primary" /> 合规边界
        </h3>
        <p className="text-sm text-muted-foreground">
          AI 助手只做信息整理与多视角分析：不推荐具体买卖、不预测涨跌与价位、不给买卖时机、
          不承诺收益、不打分排名。这条底线固化在后端 persona，模型对话始终受其约束。
        </p>
      </GlassCard>

      <div className="mt-4">
        <Disclaimer />
      </div>
    </div>
  );
}
