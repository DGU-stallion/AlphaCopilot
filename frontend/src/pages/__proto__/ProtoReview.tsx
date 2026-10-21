/**
 * 🔵 原型（throwaway）—— 回答「ADR-0013 的终端风长什么样、布局怎么排」。
 *
 * 访问：/daily-review?proto=A|B|C
 * 三个变体**结构不同**（不是换配色）：
 *   A 密集终端：单栏、全表格、行高 26px，一屏看尽 —— 交易终端最字面的读法
 *   B 分栏工作台：左摘要 + 中主画布 + 右 Agent 常驻栏 —— ADR-0013 §4 的布局
 *   C 卡片流：每块自成一卡、自带标题与口径 —— 慢读、可追溯，一屏看得少
 *
 * 样式走 proto.css 里的 --p-* token（ADR-0013 §2 的值），刻意不复用生产的
 * 玻璃拟态 token —— 否则看不出风格切换到底差在哪。
 *
 * 数据来自真实 /api 接口。原型不写库、不改后端、不持久化。
 * 看完即删，或搬到 throwaway 分支。
 */
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type MarketOverview, type Quote, type ShortTermEmotion } from "@/lib/api";
import "./proto.css";

// ---------------------------------------------------------------- 共享取数
// 原型不追求缓存/重试，只把真数据拿到手。失败就明说，因为原型要暴露的
// 恰恰是「数据为空时版式还成不成立」。
function useProtoData() {
  const [ov, setOv] = useState<MarketOverview | null>(null);
  const [emo, setEmo] = useState<ShortTermEmotion | null>(null);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    let alive = true;
    api.marketOverview().then((d) => alive && setOv(d)).catch(() => alive && setErr("盘面数据取不到"));
    api.emotion().then((d) => alive && setEmo(d)).catch(() => alive && setErr("情绪数据取不到"));
    api.quote("600519,000858,600036,601318,000001,300750")
      .then((d) => alive && setQuotes(d))
      .catch(() => alive && setErr("行情取不到"));
    return () => { alive = false; };
  }, []);

  return { ov, emo, quotes, err };
}

const fmt = (v: number | null | undefined, d = 2) =>
  v == null || Number.isNaN(v) ? "—" : v.toLocaleString("zh-CN", { minimumFractionDigits: d, maximumFractionDigits: d });

// 涨跌色走 token（--p-up/--p-down 会随口径切换），不写死 hex
const ud = (v: number | null | undefined): React.CSSProperties =>
  v == null || v === 0
    ? { color: "var(--p-muted)" }
    : { color: v > 0 ? "var(--p-up)" : "var(--p-down)" };

// 原型内部的一组原子类，避免到处写 style
const S = {
  bg: { background: "var(--p-bg)" } as React.CSSProperties,
  panel: { background: "var(--p-panel)" } as React.CSSProperties,
  surface: { background: "var(--p-surface)" } as React.CSSProperties,
  borderB: { borderBottom: "1px solid var(--p-border)" } as React.CSSProperties,
  borderR: { borderRight: "1px solid var(--p-border)" } as React.CSSProperties,
  muted: { color: "var(--p-muted)" } as React.CSSProperties,
  faint: { color: "var(--p-faint)" } as React.CSSProperties,
  accent: { color: "var(--p-accent)" } as React.CSSProperties,
};

const Label = ({ children }: { children: React.ReactNode }) => (
  <div style={{ ...S.muted, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em" }}>
    {children}
  </div>
);

// ---------------------------------------------------------------- 变体 A：密集终端
// 结构：没有卡片，只有贴边的表格行。目标是一屏塞进最多确定性数字，
// 眼睛顺着列往下扫。行高压到 26px 是刻意的。
function VariantA() {
  const { ov, emo, quotes, err } = useProtoData();
  const s = ov?.sentiment;
  const rows = Object.entries(quotes);

  const metrics: [string, string | number | undefined, React.CSSProperties][] = [
    ["上涨", s?.up, ud(s?.up)], ["下跌", s?.down, s?.down != null ? { color: "var(--p-down)" } : S.muted],
    ["平", s?.flat, S.muted], ["涨停", s?.zt, { color: "var(--p-up)" }],
    ["跌停", s?.dt, { color: "var(--p-down)" }], ["活跃", s?.active, {}],
    ["广度", s?.breadth, {}], ["投机", s?.speculation, {}],
  ];

  return (
    <div style={{ fontFamily: "JetBrains Mono, ui-monospace, monospace", fontSize: 12 }}>
      {err && (
        <div style={{ ...S.borderB, background: "color-mix(in srgb, var(--p-down) 12%, transparent)", color: "var(--p-down)", padding: "4px 12px" }}>
          {err}
        </div>
      )}

      {/* 指标条：一整行，竖线分隔，不占垂直空间 */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--p-border)" }}>
        {metrics.map(([k, v, st], i) => (
          <div key={k} style={{ ...(i < metrics.length - 1 ? S.borderR : {}), flex: 1, padding: "8px 12px" }}>
            <Label>{k}</Label>
            <div style={{ ...st, fontVariantNumeric: "tabular-nums" }}>
              {typeof v === "number" ? fmt(v, 0) : (v ?? "—")}
            </div>
          </div>
        ))}
      </div>

      {/* 主表：数字右对齐，等宽 */}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ ...S.borderB, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", ...S.muted }}>
            {["代码", "名称", "现价", "涨跌%", "换手%", "PE", "PB", "市值亿"].map((h, i) => (
              <th key={h} style={{ padding: "6px 12px", fontWeight: 400, textAlign: i < 2 ? "left" : "right" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([code, q]) => (
            <tr key={code} style={{ height: 26, borderBottom: "1px solid color-mix(in srgb, var(--p-border) 55%, transparent)" }}>
              <td style={{ padding: "0 12px", ...S.muted, fontVariantNumeric: "tabular-nums" }}>{code}</td>
              <td style={{ padding: "0 12px" }}>{q.name}</td>
              <td style={{ padding: "0 12px", textAlign: "right", ...ud(q.change_pct) }}>{fmt(q.price)}</td>
              <td style={{ padding: "0 12px", textAlign: "right", ...ud(q.change_pct) }}>
                {q.change_pct > 0 ? "+" : ""}{fmt(q.change_pct)}%
              </td>
              <td style={{ padding: "0 12px", textAlign: "right" }}>{fmt(q.turnover_pct)}</td>
              <td style={{ padding: "0 12px", textAlign: "right", ...S.muted }}>{fmt(q.pe_ttm, 1)}</td>
              <td style={{ padding: "0 12px", textAlign: "right", ...S.muted }}>{fmt(q.pb, 1)}</td>
              <td style={{ padding: "0 12px", textAlign: "right" }}>{fmt(q.mcap_yi, 0)}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={8} style={{ padding: "24px 12px", textAlign: "center", ...S.muted }}>行情未加载</td></tr>
          )}
        </tbody>
      </table>

      {/* 连板梯队：同一套网格，不另开卡片 */}
      <div style={{ borderTop: "1px solid var(--p-border)" }}>
        <div style={{ padding: "6px 12px" }}>
          <Label>连板梯队 · {emo?.date ?? "—"} · 最高 {emo?.max_boards ?? "—"} 板</Label>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 1, background: "var(--p-border)", padding: 1 }}>
          {(emo?.ladder ?? []).map((l) => (
            <div key={l.boards} style={{ ...S.panel, display: "flex", flex: 1, minWidth: 90, alignItems: "baseline", justifyContent: "space-between", padding: "8px 12px" }}>
              <span style={{ ...S.muted, fontSize: 11 }}>{l.boards} 板</span>
              <span style={{ fontVariantNumeric: "tabular-nums" }}>{l.count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- 变体 B：分栏工作台
// 结构：左（市场摘要）+ 中（主画布）+ 右（Agent 常驻栏）。
// 用来判断「对话常驻」是否比右下角浮标更贴合 AI native。
function VariantB() {
  const { ov, emo, quotes, err } = useProtoData();
  const s = ov?.sentiment;
  const rows = Object.entries(quotes);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "180px 1fr 320px", gap: 1, background: "var(--p-border)", height: "100%", fontSize: 12 }}>
      {/* 左：市场摘要 */}
      <div style={{ ...S.panel, padding: 12 }}>
        <Label>盘面</Label>
        <div style={{ marginTop: 6 }}>
          {([["上涨", s?.up, { color: "var(--p-up)" }], ["下跌", s?.down, { color: "var(--p-down)" }],
             ["涨停", s?.zt, { color: "var(--p-up)" }], ["跌停", s?.dt, { color: "var(--p-down)" }]] as const).map(([k, v, st]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
              <span style={S.muted}>{k}</span>
              <span style={{ ...st, fontVariantNumeric: "tabular-nums" }}>{fmt(Number(v), 0)}</span>
            </div>
          ))}
        </div>
        <div style={{ height: 16 }} />
        <Label>情绪</Label>
        <div style={{ marginTop: 6 }}>
          {[["活跃度", s?.active], ["广度", s?.breadth], ["投机", s?.speculation]].map(([k, v]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
              <span style={S.muted}>{k}</span>
              <span>{v ?? "—"}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 中：主画布 */}
      <div style={{ ...S.bg, padding: 12, overflow: "auto" }}>
        {err && (
          <div style={{ border: "1px solid var(--p-down)", color: "var(--p-down)", padding: "4px 8px", marginBottom: 8 }}>{err}</div>
        )}
        <Label>自选行情</Label>
        <div style={{ border: "1px solid var(--p-border)", marginTop: 6 }}>
          {rows.map(([code, q], i) => (
            <div key={code} style={{ ...(i % 2 ? S.panel : S.bg), display: "grid", gridTemplateColumns: "80px 1fr 90px 80px", alignItems: "center", height: 30, padding: "0 12px" }}>
              <span style={{ ...S.muted, fontVariantNumeric: "tabular-nums" }}>{code}</span>
              <span>{q.name}</span>
              <span style={{ textAlign: "right", ...ud(q.change_pct) }}>{fmt(q.price)}</span>
              <span style={{ textAlign: "right", ...ud(q.change_pct) }}>
                {q.change_pct > 0 ? "+" : ""}{fmt(q.change_pct)}%
              </span>
            </div>
          ))}
          {rows.length === 0 && <div style={{ padding: "24px 12px", textAlign: "center", ...S.muted }}>行情未加载</div>}
        </div>

        <div style={{ height: 16 }} />
        <Label>连板梯队</Label>
        <div style={{ marginTop: 6 }}>
          {(emo?.ladder ?? []).map((l) => (
            <div key={l.boards} style={{ display: "flex", alignItems: "center", gap: 8, padding: "2px 0" }}>
              <span style={{ width: 48, fontSize: 11, ...S.muted }}>{l.boards} 板</span>
              <div style={{ height: 12, background: "var(--p-up)", opacity: 0.75, width: Math.min(l.count * 6, 240) }} />
              <span style={{ fontVariantNumeric: "tabular-nums" }}>{l.count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 右：Agent 常驻栏 */}
      <div style={{ ...S.panel, display: "flex", flexDirection: "column" }}>
        <div style={{ ...S.borderB, padding: "8px 12px" }}>
          <Label>Agent</Label>
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={S.muted}>【当前页面：复盘看板】</div>
          <div style={S.muted}>
            涨 {s?.up ?? "—"} / 跌 {s?.down ?? "—"}，涨停 {s?.zt ?? "—"}，最高 {emo?.max_boards ?? "—"} 板
          </div>
          <div style={{ ...S.surface, border: "1px solid var(--p-border)", padding: 8 }}>今天这盘面怎么解读？</div>
          <div style={S.muted}>
            上涨 {s?.up ?? "—"} 家、下跌 {s?.down ?? "—"} 家，广度{s?.breadth ?? "—"}；涨停 {s?.zt ?? "—"} 家说明还有局部热点，但整体是普跌结构。
          </div>
        </div>
        <div style={{ borderTop: "1px solid var(--p-border)", padding: 8 }}>
          <div style={{ ...S.bg, border: "1px solid var(--p-border)", padding: "6px 8px", ...S.faint }}>问点什么…</div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- 变体 C：卡片流
// 结构：每块自成一卡、自带标题与口径。与 A 相反的取向：慢读、可追溯，一屏看得少。
function VariantC() {
  const { ov, emo, quotes, err } = useProtoData();
  const s = ov?.sentiment;
  const rows = Object.entries(quotes);

  const Card = ({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) => (
    <div style={{ ...S.panel, border: "1px solid var(--p-border)", borderRadius: 4 }}>
      <div style={{ ...S.borderB, display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "8px 12px" }}>
        <span style={{ fontSize: 13 }}>{title}</span>
        {note && <span style={{ fontSize: 10, ...S.faint }}>{note}</span>}
      </div>
      <div style={{ padding: 12 }}>{children}</div>
    </div>
  );

  return (
    <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8, fontSize: 12 }}>
      {err && <div style={{ border: "1px solid var(--p-down)", color: "var(--p-down)", padding: "4px 8px" }}>{err}</div>}

      <Card title="盘面情绪" note={`as-of ${s?.date ?? "—"}`}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
          {([["上涨", s?.up, { color: "var(--p-up)" }], ["下跌", s?.down, { color: "var(--p-down)" }],
             ["涨停", s?.zt, { color: "var(--p-up)" }], ["跌停", s?.dt, { color: "var(--p-down)" }]] as const).map(([k, v, st]) => (
            <div key={k}>
              <Label>{k}</Label>
              <div style={{ ...st, fontSize: 16, fontVariantNumeric: "tabular-nums" }}>{fmt(Number(v), 0)}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 8, fontSize: 11, ...S.muted }}>
          广度 {s?.breadth ?? "—"} · 投机 {s?.speculation ?? "—"} · 活跃 {s?.active ?? "—"}
        </div>
      </Card>

      <Card title="自选行情" note="现价 · 涨跌 · 换手">
        <div>
          {rows.map(([code, q]) => (
            <div key={code} style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", borderBottom: "1px solid color-mix(in srgb, var(--p-border) 50%, transparent)", paddingBottom: 4, marginBottom: 4 }}>
              <div>
                <span style={S.muted}>{code}</span>
                <span style={{ marginLeft: 8 }}>{q.name}</span>
              </div>
              <div style={{ display: "flex", gap: 12, fontVariantNumeric: "tabular-nums" }}>
                <span style={ud(q.change_pct)}>{fmt(q.price)}</span>
                <span style={{ width: 64, textAlign: "right", ...ud(q.change_pct) }}>
                  {q.change_pct > 0 ? "+" : ""}{fmt(q.change_pct)}%
                </span>
              </div>
            </div>
          ))}
          {rows.length === 0 && <div style={{ padding: "16px 0", textAlign: "center", ...S.muted }}>行情未加载</div>}
        </div>
      </Card>

      <Card title="连板梯队" note="按板数分层">
        <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
          {(emo?.ladder ?? []).map((l) => (
            <div key={l.boards} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
              <div style={{ width: 24, background: "var(--p-up)", opacity: 0.75, height: Math.min(l.count * 8, 80) }} />
              <span style={{ fontSize: 10, ...S.faint }}>{l.boards}板</span>
              <span style={{ fontVariantNumeric: "tabular-nums" }}>{l.count}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- 切换条
const VARIANTS = [
  { key: "A", name: "密集终端", C: VariantA },
  { key: "B", name: "分栏工作台", C: VariantB },
  { key: "C", name: "卡片流", C: VariantC },
] as const;

// 切换条刻意做得和页面不一样（黑底圆角胶囊），让人一眼知道它不是被评审的设计
function Switcher({ cur, set }: { cur: string; set: (k: string) => void }) {
  const i = Math.max(0, VARIANTS.findIndex((v) => v.key === cur));
  const go = (d: number) => set(VARIANTS[(i + d + VARIANTS.length) % VARIANTS.length].key);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (/^(INPUT|TEXTAREA)$/.test(t.tagName) || t.isContentEditable) return;
      if (e.key === "ArrowLeft") go(-1);
      if (e.key === "ArrowRight") go(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div style={{
      position: "fixed", bottom: 16, left: "50%", transform: "translateX(-50%)", zIndex: 50,
      display: "flex", alignItems: "center", gap: 8, borderRadius: 999,
      background: "rgba(0,0,0,0.88)", color: "#fff", padding: "6px 8px",
      boxShadow: "0 8px 24px rgba(0,0,0,.4)", fontFamily: "system-ui, sans-serif",
    }}>
      <button onClick={() => go(-1)} style={{ padding: "0 8px", fontSize: 18, lineHeight: 1 }}>←</button>
      <span style={{ minWidth: 132, textAlign: "center", fontSize: 12 }}>
        <b>{cur}</b> · {VARIANTS[i].name}
      </span>
      <button onClick={() => go(1)} style={{ padding: "0 8px", fontSize: 18, lineHeight: 1 }}>→</button>
      <span style={{ marginLeft: 4, borderLeft: "1px solid rgba(255,255,255,.2)", paddingLeft: 8, fontSize: 10, opacity: 0.5 }}>
        原型 · 看完即删
      </span>
    </div>
  );
}

// ---------------------------------------------------------------- 外壳（主题/口径切换）
// 把「双主题 + 涨跌双口径」也放进原型：切换时的观感正是要评审的东西之一。
function Controls({ theme, setTheme, conv, setConv }: {
  theme: string; setTheme: (v: string) => void; conv: string; setConv: (v: string) => void;
}) {
  const btn = (active: boolean): React.CSSProperties => ({
    border: `1px solid ${active ? "var(--p-accent)" : "var(--p-border)"}`,
    color: active ? "var(--p-accent)" : "var(--p-muted)",
    background: "transparent", padding: "2px 8px", fontSize: 11, cursor: "pointer", borderRadius: 2,
  });
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, borderBottom: "1px solid var(--p-border)", padding: "6px 12px" }}>
      <span style={{ fontSize: 11, ...S.muted }}>主题</span>
      <button style={btn(theme === "dark")} onClick={() => setTheme("dark")}>深色</button>
      <button style={btn(theme === "light")} onClick={() => setTheme("light")}>浅色</button>
      <span style={{ marginLeft: 12, fontSize: 11, ...S.muted }}>涨跌口径</span>
      <button style={btn(conv === "cn")} onClick={() => setConv("cn")}>A股 红涨绿跌</button>
      <button style={btn(conv === "intl")} onClick={() => setConv("intl")}>国际 绿涨红跌</button>
      <span style={{ marginLeft: "auto", fontSize: 10, ...S.faint }}>ADR-0013 原型</span>
    </div>
  );
}

export function ProtoReview() {
  const [sp, setSp] = useSearchParams();
  const variant = (sp.get("proto") ?? "A").toUpperCase();
  const cur = useMemo(() => VARIANTS.find((v) => v.key === variant) ?? VARIANTS[0], [variant]);
  const [theme, setTheme] = useState("dark");
  const [conv, setConv] = useState("cn");

  return (
    <div className="proto-shell" data-theme={theme} data-convention={conv} style={{ height: "100%" }}>
      <Controls theme={theme} setTheme={setTheme} conv={conv} setConv={setConv} />
      <cur.C />
      <Switcher cur={cur.key} set={(k) => setSp({ proto: k }, { replace: true })} />
    </div>
  );
}
