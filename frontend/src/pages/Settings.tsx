// 「接入 AI」页（S5 + ROUND3 A3）—— AI 助手的运行说明 + 模型选择器 + 连通状态自检。
//
// 定位：AlphaCopilot 的 AI 助手由**后端**统一接入（Pi 运行时子进程 RPC），
// 前端不配置、不持有模型 key。本页因此不是"填 key"的表单，而是：
// 选一个真的会生效的 model、说明它怎么工作、做一次连通自检、讲清合规边界。
//
// **为什么本页没有 baseURL / apiKey 输入框**（不要"补全"）：
// PiProvider 不消费这两个字段（backend/agent/provider.py:81）——端点与凭据
// 由 Pi 自己从 ~/.pi/agent/models.json 与 auth.json 读。给它们做输入框
// = 让人填完无效还以为改成功了，是「UI 撒谎」，比不做更糟。
// 唯一真的生效的设置是 model（pi.py 把它拼成 --provider/--model），
// 所以后端 PUT /api/settings/ai 也只收 model。

import { useEffect, useMemo, useState } from "react";
import {
  Sparkles, CheckCircle2, XCircle, Loader2, ShieldCheck, MessageSquare, AlertTriangle,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { apiUrl } from "@/lib/base";
import { authHeaders, settingsApi } from "@/lib/api";
import type { ModelOption } from "@/lib/api";

type Probe = { state: "idle" | "checking" | "ok" | "fail"; detail?: string };

// GET 的响应里还带 `known`（api.ts 契约写早于该字段，类型少列了它）。
// 说它什么：保存过的模型可能已被下方注册表移除，后端仍然回显 current 并
// 如实标 known=false——前端拿这个字段判断要不要给「不在注册表里」的提示。
// 这里在包内做一次窄化（ROUND3 规则：不动 api.ts）。
type AiSettings = {
  current: string;
  known: boolean;
  options: ModelOption[];
};

const inputCls =
  "h-7 rounded-[4px] border border-border bg-[hsl(var(--card))] px-2.5 text-[13px] " +
  "outline-none placeholder:text-muted-foreground/60 focus:border-[hsl(var(--primary))]";

export function Settings() {
  const [probe, setProbe] = useState<Probe>({ state: "idle" });

  // 模型设置：清单后端现读注册表（来自 pi --list-models），本页只消费。
  const [ai, setAi] = useState<AiSettings | null>(null);
  const [loadFail, setLoadFail] = useState<string | null>(null);
  const [selected, setSelected] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    settingsApi
      .ai()
      .then((data) => {
        if (!alive) return;
        const d = data as AiSettings;
        setAi(d);
        setSelected(d.current || "");
      })
      .catch((e: unknown) => {
        if (alive) setLoadFail(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, []);

  // 按 provider 分组（接口 34 个选项天然按 provider 排好）。
  const groups = useMemo(() => {
    const map = new Map<string, ModelOption[]>();
    for (const o of ai?.options ?? []) {
      const list = map.get(o.provider) ?? [];
      list.push(o);
      map.set(o.provider, list);
    }
    return [...map.entries()];
  }, [ai]);

  const save = async () => {
    if (!selected) return;
    setSaving(true);
    setSaveMsg(null);
    setSaveErr(null);
    try {
      await settingsApi.setModel(selected);
      // 后端在**下一次建会话**时才读 setting（见后端 resolve_model 注释），
      // 不是立即换掉进行中的对话——所以措辞是「下一条消息生效」，别写成「已应用」。
      setSaveMsg("已切换，下一条消息生效");
    } catch (e) {
      setSaveErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

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

  const unknownCurrent = ai && ai.current !== "" && !ai.known;

  return (
    <div>
      <PageHeader
        title="接入 AI"
        subtitle="AI 助手的运行方式、连通自检与合规边界"
      />

      {/* 运行配置 */}
      <Panel className="mb-4">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="h-4 w-4 text-primary" /> 运行配置
        </h3>
        <Row k="接入方式" v="Pi 运行时（本地子进程 · RPC）" />
        <Row
          k="可用工具"
          v="bash · read · write · edit · MCP(vendor 取数) · skills 白名单"
        />

        {/* 模型选择（A3）：后端现读注册表（pi --list-models），选完保存即可，
            不用重启；baseURL/apiKey 故意不做，见文件头注释。 */}
        {loadFail ? (
          <div className="mt-3 flex items-center gap-2 text-sm text-[hsl(var(--danger))]">
            <XCircle className="h-4 w-4 shrink-0" /> 读不到模型清单：{loadFail}（确认后端已启动）
          </div>
        ) : ai === null ? (
          <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> 正在读取模型清单 …
          </div>
        ) : (
          <div className="mt-3">
            <label className="block min-w-0">
              <span className="mb-1 block text-[11px] text-muted-foreground">模型</span>
              <select
                aria-label="模型"
                className={`${inputCls} w-full cursor-pointer max-w-xl`}
                value={selected}
                onChange={(e) => {
                  setSelected(e.target.value);
                  setSaveMsg(null);
                  setSaveErr(null);
                }}
              >
                {/* 保存过的模型已不在注册表里 → 原样回显在单独分组，
                    不静默换成第一个：用户必须看到现状并主动重选。 */}
                {unknownCurrent && (
                  <optgroup label="当前保存的模型（不在注册表里）">
                    <option value={ai.current}>{ai.current}</option>
                  </optgroup>
                )}
                {groups.map(([provider, opts]) => (
                  <optgroup key={provider} label={provider}>
                    {opts.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>

            {unknownCurrent && (
              <div className="mt-2 flex items-center gap-2 text-sm text-[hsl(var(--warning))]">
                <AlertTriangle className="h-4 w-4 shrink-0" /> 当前模型不在注册表里，请重新选择后保存
              </div>
            )}

            <div className="mt-2 flex flex-wrap items-center gap-3">
              <button
                onClick={save}
                disabled={saving || !selected}
                className="inline-flex h-7 items-center gap-1.5 rounded-[4px] bg-[hsl(var(--primary))] px-3 text-[13px] font-medium text-[hsl(var(--primary-foreground))] transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                保存
              </button>
              {saveMsg && (
                <span role="status" className="inline-flex items-center gap-1.5 text-sm text-[hsl(var(--success))]">
                  <CheckCircle2 className="h-4 w-4" /> {saveMsg}
                </span>
              )}
              {saveErr && (
                <span role="status" className="inline-flex items-center gap-1.5 text-sm text-[hsl(var(--danger))]">
                  <XCircle className="h-4 w-4" /> 保存失败：{saveErr}
                </span>
              )}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              模型清单来自本机 Pi 注册表现读；key 与端点由 Pi 配置持有，不在浏览器保存、不经前端传输 — 因此本页不需要填写任何密钥。
            </p>
          </div>
        )}
      </Panel>

      {/* 连通自检 */}
      <Panel className="mb-4">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <CheckCircle2 className="h-4 w-4 text-primary" /> 连通自检
        </h3>
        <div className="flex items-center gap-3">
          <button
            onClick={check}
            disabled={probe.state === "checking"}
            className="inline-flex h-7 items-center gap-1.5 rounded-[4px] bg-[hsl(var(--primary))] px-3 text-[13px] font-medium text-[hsl(var(--primary-foreground))] transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {probe.state === "checking" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
            检查后端连通
          </button>
          {probe.state === "ok" && (
            <span className="inline-flex items-center gap-1.5 text-sm text-[hsl(var(--success))]">
              <CheckCircle2 className="h-4 w-4" /> {probe.detail}
            </span>
          )}
          {probe.state === "fail" && (
            <span className="inline-flex items-center gap-1.5 text-sm text-[hsl(var(--danger))]">
              <XCircle className="h-4 w-4" /> 不可达：{probe.detail}（确认后端已启动）
            </span>
          )}
        </div>
      </Panel>

      {/* 怎么用 */}
      <Panel className="mb-4">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <MessageSquare className="h-4 w-4 text-primary" /> 怎么用
        </h3>
        <ul className="space-y-2 text-sm text-muted-foreground">
          <li>· 点右下角 <span className="text-primary">✦</span> 浮标打开对话面板，面板可拖左上角调整大小。</li>
          <li>· 每页会把本页的确定性数据快照作为上下文，AI 就着当前页面的数据为你解释。</li>
          <li>· AI 拥有完整工具集（bash / 读写文件 / MCP 取数），以你的 OS 用户权限运行 —— 这是 ADR-0010 显式接受的风险，不是疏忽。</li>
          <li>· 换模型后**下一条消息**即生效，不需要重启后端。</li>
        </ul>
      </Panel>

      {/* 合规边界 */}
      <Panel>
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <ShieldCheck className="h-4 w-4 text-primary" /> 合规边界
        </h3>
        <p className="text-sm text-muted-foreground">
          AI 助手只做信息整理与多视角分析：不推荐具体买卖、不预测涨跌与价位、不给买卖时机、
          不承诺收益、不打分排名。这条底线固化在后端 persona，模型对话始终受其约束。
        </p>
      </Panel>

      <div className="mt-4">
      </div>
    </div>
  );
}
