/**
 * 🔵 原型 v3（throwaway）—— 完整一页，用 antd 组件搭建。
 *
 * 为什么重做第三版：用户对 v1（旧外壳里塞新表格）和 v2（手写 div 全屏）
 * 都不满意，明确说「风格都不喜欢，但我心中也没有对标」+「用 react、ant 这些
 * 好看的库，而不是纯原生手写」。
 *
 * 所以这版：
 *   1. 用 **antd v6** 组件（Layout/Menu/Table/Tabs/Statistic/Segmented/Card...）
 *   2. 主题走 theme/tokens.ts 的单一真源，改 token 而不是逐组件覆盖 CSS
 *   3. **完整一页**：左导航 + 顶栏 + 主画布（K线/成交量）+ 右侧 Agent 栏 + 底栏
 *   4. 字体按调研：UI 用 Inter Variable，**所有数字用 JetBrains Mono**
 *
 * 访问：/proto/app
 * 决策依据见 docs/research/ui-design-2026-10.md。
 */
import { useEffect, useRef, useState } from "react";
import {
  Layout, Menu, Table, Tabs, Segmented, Tag, Space,
  Typography, Badge, Input, Button, Tooltip, theme as antdTheme, ConfigProvider,
} from "antd";
import {
  LineChartOutlined, FundOutlined, ThunderboltOutlined, StarOutlined,
  FileTextOutlined, ApartmentOutlined, PieChartOutlined,
  BookOutlined, SettingOutlined, MoonOutlined, SunOutlined, SearchOutlined,
  RobotOutlined, ArrowUpOutlined, ArrowDownOutlined, ReloadOutlined,
} from "@ant-design/icons";
import {
  createChart, CandlestickSeries, HistogramSeries,
  type IChartApi, type ISeriesApi, type UTCTimestamp,
} from "lightweight-charts";
import { DARK, LIGHT, FONT, SIZE, antdTheme as buildTheme, type Palette } from "@/theme/tokens";
// 字体自托管：不从 CDN 拉（离线可用、无第三方请求）
import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";

const { Sider, Header, Content, Footer } = Layout;
const { Text } = Typography;

// ---------------------------------------------------------------- 数据
type Bar = { datetime: string; open: number; close: number; high: number; low: number; vol: number };
type Quote = { name: string; price: number; change_pct: number; pe_ttm: number; pb: number; turnover_pct: number; mcap_yi: number };

function useKline(code: string) {
  const [bars, setBars] = useState<Bar[]>([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    setErr("");
    fetch(`/api/kline?code=${code}&offset=180`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => setBars(d?.data?.bars ?? []))
      .catch(() => setErr("K 线取不到"));
  }, [code]);
  return { bars, err };
}

function useQuotes() {
  const [q, setQ] = useState<Record<string, Quote>>({});
  useEffect(() => {
    fetch("/api/quote?codes=600519,000858,600036,601318,000001,300750")
      .then((r) => r.json()).then((d) => setQ(d?.data ?? {})).catch(() => {});
  }, []);
  return q;
}

// ---------------------------------------------------------------- K 线图
// 颜色从 token 读，不硬编码 —— 与 antd 主题同源（硬规则 7）
function KLineChart({ bars, height = 340, palette }: { bars: Bar[]; height?: number; palette: Palette }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  // ⚠️ 建 chart 的 effect **不能依赖 palette**。
  // 依赖了的话，切主题会销毁并重建 chart；而 series 的 cleanup 随后执行
  // `chart.removeSeries(s)`，此时 chart 已销毁 → 内部 ensureDefined 抛
  // 「Value is undefined」，整个页面白屏（实测踩过）。
  // 主题变化只该 applyOptions 换色，不该重建实例。
  useEffect(() => {
    if (!ref.current) return;
    const c = createChart(ref.current, {
      height,
      layout: { background: { color: "transparent" }, textColor: "#6B7385", fontSize: 10, attributionLogo: true },
      autoSize: true,
    });
    chartRef.current = c;
    const ro = new ResizeObserver(() => ref.current && c.applyOptions({ width: ref.current.clientWidth }));
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      seriesRef.current = null;
      chartRef.current = null;
      c.remove();
    };
  }, [height]);

  // 主题色：只改样式，不碰实例
  useEffect(() => {
    const c = chartRef.current;
    if (!c) return;
    c.applyOptions({
      layout: { textColor: palette.textTertiary, background: { color: "transparent" } },
      grid: { vertLines: { color: palette.border }, horzLines: { color: palette.border } },
      rightPriceScale: { borderColor: palette.border, scaleMargins: { top: 0.08, bottom: 0.08 } },
      timeScale: { borderColor: palette.border, timeVisible: false },
      crosshair: {
        mode: 1,
        vertLine: { color: palette.textTertiary, style: 3, labelBackgroundColor: palette.raised },
        horzLine: { color: palette.textTertiary, style: 3, labelBackgroundColor: palette.raised },
      },
    });
    if (seriesRef.current) {
      seriesRef.current.applyOptions({
        upColor: palette.up, downColor: palette.down,
        wickUpColor: palette.up, wickDownColor: palette.down,
      });
    }
  }, [palette]);

  useEffect(() => {
    const c = chartRef.current;
    if (!c || !bars.length) return;
    // 数据变了就换数据，不重建 series —— 重建会丢掉缩放位置与十字光标状态
    let s = seriesRef.current;
    if (!s) {
      s = c.addSeries(CandlestickSeries, {
        upColor: palette.up, downColor: palette.down, borderVisible: false,
        wickUpColor: palette.up, wickDownColor: palette.down,
      });
      seriesRef.current = s;
    }
    s.setData(bars.map((b) => ({
      time: (Date.parse(b.datetime + "T00:00:00Z") / 1000) as UTCTimestamp,
      open: b.open, high: b.high, low: b.low, close: b.close,
    })));
    c.timeScale().fitContent();
  }, [bars, palette]);

  return <div ref={ref} style={{ width: "100%" }} />;
}

function VolumeChart({ bars, height = 90, palette }: { bars: Bar[]; height?: number; palette: Palette }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  // 同 KLineChart：建实例的 effect 不依赖 palette（否则切主题时
  // series cleanup 会打到已销毁的 chart 上）
  useEffect(() => {
    if (!ref.current) return;
    const c = createChart(ref.current, {
      height,
      layout: { background: { color: "transparent" }, textColor: "#6B7385", fontSize: 10, attributionLogo: false },
      autoSize: true,
    });
    chartRef.current = c;
    const ro = new ResizeObserver(() => ref.current && c.applyOptions({ width: ref.current.clientWidth }));
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      seriesRef.current = null;
      chartRef.current = null;
      c.remove();
    };
  }, [height]);

  useEffect(() => {
    const c = chartRef.current;
    if (!c) return;
    c.applyOptions({
      layout: { textColor: palette.textTertiary },
      grid: { vertLines: { color: palette.border }, horzLines: { color: palette.border } },
      rightPriceScale: { borderColor: palette.border, scaleMargins: { top: 0.1, bottom: 0 } },
      timeScale: { borderColor: palette.border, visible: false },
    });
  }, [palette]);

  useEffect(() => {
    const c = chartRef.current;
    if (!c || !bars.length) return;
    let s = seriesRef.current;
    if (!s) {
      s = c.addSeries(HistogramSeries, { priceFormat: { type: "volume" } });
      seriesRef.current = s;
    }
    s.setData(bars.map((b, i) => ({
      time: (Date.parse(b.datetime + "T00:00:00Z") / 1000) as UTCTimestamp,
      value: b.vol,
      color: i > 0 && b.close >= bars[i - 1].close ? `${palette.up}55` : `${palette.down}55`,
    })));
    c.timeScale().fitContent();
  }, [bars, palette]);

  return <div ref={ref} style={{ width: "100%" }} />;
}

// ---------------------------------------------------------------- 数字组件
// 强制等宽 + 涨跌色。所有要显示钱/百分比的地方都走它，不直接写字。
function Num({ v, digits = 2, pct = false, palette }: { v: number | null | undefined; digits?: number; pct?: boolean; palette: Palette }) {
  if (v == null || Number.isNaN(v)) return <span style={{ fontFamily: FONT.mono, color: palette.textTertiary }}>—</span>;
  const color = pct ? (v > 0 ? palette.up : v < 0 ? palette.down : palette.textSecondary) : palette.text;
  return (
    <span style={{ fontFamily: FONT.mono, fontVariantNumeric: "tabular-nums", color }}>
      {v > 0 && pct ? "+" : ""}{v.toFixed(digits)}{pct ? "%" : ""}
    </span>
  );
}

// ---------------------------------------------------------------- 左侧自选表
function WatchTable({ quotes, palette, onPick, active }: {
  quotes: Record<string, Quote>; palette: Palette; onPick: (c: string) => void; active: string;
}) {
  const rows = Object.entries(quotes).map(([code, q]) => ({ key: code, code, ...q }));

  const cols = [
    {
      title: "代码", dataIndex: "code", width: 72,
      render: (c: string) => <span style={{ fontFamily: FONT.mono, color: palette.textTertiary, fontSize: SIZE.xs }}>{c}</span>,
    },
    {
      title: "名称", dataIndex: "name", width: 76,
      render: (n: string, r: { code: string }) => (
        <a onClick={() => onPick(r.code)} style={{ color: r.code === active ? palette.accent : palette.text }}>{n}</a>
      ),
    },
    {
      title: "现价", dataIndex: "price", align: "right" as const, width: 76,
      render: (v: number) => <Num v={v} palette={palette} />,
    },
    {
      title: "涨跌", dataIndex: "change_pct", align: "right" as const, width: 76,
      render: (v: number) => <Num v={v} pct palette={palette} />,
    },
  ];

  return (
    <Table
      dataSource={rows}
      columns={cols}
      size="small"
      pagination={false}
      showHeader
      scroll={{ y: 300 }}
      style={{ fontSize: SIZE.sm }}
    />
  );
}

// ---------------------------------------------------------------- 主画布
function MainCanvas({ palette, code }: { palette: Palette; code: string }) {
  const { bars, err } = useKline(code);
  const quotes = useQuotes();
  const last = bars[bars.length - 1];
  const prev = bars[bars.length - 2];
  const pct = last && prev ? ((last.close - prev.close) / prev.close) * 100 : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, height: "100%" }}>
      {/* 头部：标的 + 大数字。这是视觉焦点，不塞别的 */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 16, paddingBottom: 12, borderBottom: `1px solid ${palette.border}` }}>
        <div>
          <Space size={8} align="baseline">
            <span style={{ fontSize: SIZE.lg, fontWeight: 600, color: palette.text }}>
              {quotes[code]?.name ?? "—"}
            </span>
            <span style={{ fontFamily: FONT.mono, fontSize: SIZE.xs, color: palette.textTertiary }}>{code}</span>
            <Tag style={{ marginLeft: 4, fontFamily: FONT.mono, fontSize: 10 }}>日线</Tag>
          </Space>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginTop: 4 }}>
            <span style={{ fontFamily: FONT.mono, fontSize: 28, fontWeight: 500, color: pct >= 0 ? palette.up : palette.down, fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>
              {last ? last.close.toFixed(2) : "—"}
            </span>
            <span style={{ fontFamily: FONT.mono, fontSize: SIZE.md, color: pct >= 0 ? palette.up : palette.down }}>
              {pct >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />} {Math.abs(pct).toFixed(2)}%
            </span>
          </div>
        </div>

        <div style={{ marginLeft: "auto", display: "flex", gap: 28 }}>
          {([["开", last?.open], ["高", last?.high], ["低", last?.low], ["量(万)", last ? last.vol / 1e4 : null]] as const).map(([k, v]) => (
            <div key={k}>
              <div style={{ fontSize: SIZE.xs, color: palette.textTertiary }}>{k}</div>
              <div style={{ fontFamily: FONT.mono, fontSize: SIZE.sm, color: palette.text, fontVariantNumeric: "tabular-nums" }}>
                {v == null ? "—" : v.toFixed(k === "量(万)" ? 1 : 2)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {err && <Text type="danger" style={{ fontSize: SIZE.xs }}>{err}</Text>}

      <Tabs
        size="small"
        defaultActiveKey="k"
        items={[
          {
            key: "k", label: "K 线",
            children: (
              <div>
                <KLineChart bars={bars} palette={palette} height={340} />
                <div style={{ borderTop: `1px solid ${palette.border}`, marginTop: 2 }}>
                  <VolumeChart bars={bars} palette={palette} height={80} />
                </div>
              </div>
            ),
          },
          {
            key: "corr", label: "相关性",
            children: <div style={{ padding: 40, textAlign: "center", color: palette.textTertiary, fontSize: SIZE.sm }}>此处挂 ECharts 热力图（M2-5）</div>,
          },
          {
            key: "bt", label: "回测",
            children: <div style={{ padding: 40, textAlign: "center", color: palette.textTertiary, fontSize: SIZE.sm }}>净值 + 回撤（LWC 双 pane）</div>,
          },
        ]}
      />
    </div>
  );
}

// ---------------------------------------------------------------- 右 Agent 栏
// ADR-0013 §4 的核心主张：对话常驻，不做右下角浮标
function AgentPanel({ palette }: { palette: Palette }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", borderLeft: `1px solid ${palette.border}` }}>
      <div style={{ padding: "10px 12px", borderBottom: `1px solid ${palette.border}`, display: "flex", alignItems: "center", gap: 8 }}>
        <RobotOutlined style={{ color: palette.accent, fontSize: 14 }} />
        <span style={{ fontSize: SIZE.sm, fontWeight: 500, color: palette.text }}>Agent</span>
        <Badge status="processing" style={{ marginLeft: "auto" }} />
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ fontSize: 10, color: palette.textTertiary, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          当前页面：复盘看板
        </div>
        <div style={{ fontSize: SIZE.xs, color: palette.textSecondary, lineHeight: 1.6 }}>
          600519 贵州茅台 日线 180 根 · 现价 1309.69 · 涨跌 -1.67%<br />
          上涨 1941 / 下跌 3055 · 涨停 50 · 最高 4 板
        </div>

        <div style={{ background: palette.raised, borderRadius: 4, padding: "8px 10px", fontSize: SIZE.sm, color: palette.text }}>
          这波下跌是普跌还是结构性的？
        </div>
        <div style={{ fontSize: SIZE.sm, color: palette.textSecondary, lineHeight: 1.7 }}>
          上涨 1941 家、下跌 3055 家，属普跌结构；涨停 50 家说明仍有局部热点，但赚钱效应集中在少数连板股。
          <div style={{ marginTop: 6, fontSize: 10, color: palette.textTertiary }}>
            数据 as-of 2026-10-21 · run 7f3a2c
          </div>
        </div>
      </div>

      <div style={{ borderTop: `1px solid ${palette.border}`, padding: 10 }}>
        <Input.TextArea
          autoSize={{ minRows: 2, maxRows: 4 }}
          placeholder="问点什么… (⌘K)"
          variant="filled"
          style={{ fontSize: SIZE.sm }}
        />
        <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
          <Button size="small" icon={<ReloadOutlined />} style={{ fontSize: SIZE.xs }}>重算</Button>
          <Button size="small" type="primary" style={{ marginLeft: "auto", fontSize: SIZE.xs }}>发送</Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- 外壳
const NAV = [
  { key: "/macro", icon: <FundOutlined />, label: "宏观看板" },
  { key: "/daily-review", icon: <LineChartOutlined />, label: "复盘看板" },
  { type: "divider" as const },
  { key: "/watchlist", icon: <StarOutlined />, label: "股票池" },
  { key: "/reports", icon: <FileTextOutlined />, label: "我的研报" },
  { type: "divider" as const },
  { key: "/bt", icon: <ThunderboltOutlined />, label: "回测" },
  { key: "/corr", icon: <ApartmentOutlined />, label: "相关性分析" },
  { key: "/pf", icon: <PieChartOutlined />, label: "模拟组合" },
  { type: "divider" as const },
  { key: "/journal", icon: <BookOutlined />, label: "交易日志" },
  { key: "/settings", icon: <SettingOutlined />, label: "接入 AI" },
];

export function ProtoApp() {
  const [dark, setDark] = useState(true);
  const [code, setCode] = useState("600519");
  const palette = dark ? DARK : LIGHT;
  const quotes = useQuotes();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <ConfigProvider theme={{ ...buildTheme(palette), algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm }}>
      <div style={{ position: "fixed", inset: 0, background: palette.bg, fontFamily: FONT.ui }}>
        <Layout style={{ height: "100%", background: palette.bg }}>
          {/* 左导航 */}
          <Sider
            width={180}
            collapsedWidth={52}
            collapsible
            onCollapse={(v) => setCollapsed(v)}
            trigger={null}
            theme="light"
            style={{ background: palette.panel, borderRight: `1px solid ${palette.border}` }}
          >
            <div
              onClick={() => setCollapsed((c) => !c)}
              style={{
                height: 48, display: "flex", alignItems: "center", gap: 8, padding: "0 14px",
                borderBottom: `1px solid ${palette.border}`, cursor: "pointer",
              }}>
              <div style={{
                width: 20, height: 20, borderRadius: 3, background: palette.accent,
                display: "flex", alignItems: "center", justifyContent: "center",
                color: "#fff", fontSize: 11, fontWeight: 700,
              }}>A</div>
              {!collapsed && <span style={{ fontSize: SIZE.md, fontWeight: 600, color: palette.text }}>AlphaCopilot</span>}
            </div>
            <Menu
              mode="inline"
              selectedKeys={["/daily-review"]}
              items={NAV}
              style={{ background: "transparent", borderInlineEnd: "none", fontSize: SIZE.sm, paddingTop: 4 }}
            />
          </Sider>

          <Layout style={{ background: palette.bg }}>
            {/* 顶栏 */}
            <Header style={{
              height: 48, lineHeight: "48px", padding: "0 16px", background: palette.panel,
              borderBottom: `1px solid ${palette.border}`, display: "flex", alignItems: "center", gap: 12,
            }}>
              <Segmented
                size="small"
                options={[{ label: "自选", value: "watch" }, { label: "盘面", value: "market" }, { label: "研究", value: "research" }]}
                defaultValue="market"
              />
              <Input
                size="small"
                prefix={<SearchOutlined style={{ color: palette.textTertiary }} />}
                placeholder="搜代码/名称，或 ⌘K 命令"
                style={{ width: 260, fontSize: SIZE.xs }}
                variant="filled"
              />
              <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: 10, color: palette.textTertiary, fontFamily: FONT.mono }}>
                  as-of 2026-10-21 15:00
                </span>
                <Tooltip title={dark ? "切浅色" : "切深色"}>
                  <Button
                    size="small" type="text"
                    icon={dark ? <SunOutlined /> : <MoonOutlined />}
                    onClick={() => setDark((d) => !d)}
                  />
                </Tooltip>
              </div>
            </Header>

            {/* 主区：主画布 + Agent 栏 */}
            <Content style={{ display: "grid", gridTemplateColumns: "300px 1fr 340px", overflow: "hidden" }}>
              {/* 左二：自选列表 —— 终端里这一栏是给人扫的，不是装饰 */}
              <div style={{ borderRight: `1px solid ${palette.border}`, overflow: "auto", background: palette.panel }}>
                <div style={{ padding: "10px 12px 6px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: SIZE.xs, color: palette.textTertiary, textTransform: "uppercase", letterSpacing: "0.06em" }}>自选</span>
                  <span style={{ fontSize: 10, fontFamily: FONT.mono, color: palette.textTertiary }}>{Object.keys(quotes).length}</span>
                </div>
                <WatchTable quotes={quotes} palette={palette} onPick={setCode} active={code} />
              </div>
              <div style={{ padding: 16, overflow: "auto" }}>
                <MainCanvas palette={palette} code={code} />
              </div>
              <AgentPanel palette={palette} />
            </Content>

            {/* 底栏：数据来源与口径。ADR-0013 §4 */}
            <Footer style={{
              height: 28, lineHeight: "28px", padding: "0 16px", background: palette.panel,
              borderTop: `1px solid ${palette.border}`,
              display: "flex", alignItems: "center", gap: 16,
              fontSize: 10, color: palette.textTertiary, fontFamily: FONT.mono,
            }}>
              <span>数据 腾讯行情 / akshare</span>
              <span style={{ color: palette.borderStrong }}>|</span>
              <span>口径 A股红涨绿跌</span>
              <span style={{ color: palette.borderStrong }}>|</span>
              <span>as-of 2026-10-21</span>
              <span style={{ marginLeft: "auto" }}>ADR-0014 原型 · 看完即删</span>
            </Footer>
          </Layout>
        </Layout>
      </div>
    </ConfigProvider>
  );
}
