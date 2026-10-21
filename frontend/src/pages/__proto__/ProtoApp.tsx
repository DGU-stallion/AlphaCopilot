/**
 * 🔵 原型 v4（throwaway）—— 方向 A 打磨版。
 *
 * 相对 v3 的三处改动（都由用户反馈驱动）：
 *   1. **去掉自选表** —— 用户明确不需要。腾出的宽度全给主画布
 *   2. **Agent 栏可折叠** —— 折叠后只留 44px 竖条（图标 + 展开按钮），
 *      主画布随之变宽。这是 ADR-0013 §4「右常驻可折叠栏」的落地
 *   3. **图表自适应填满** —— v3 的 K 线用固定高度（340+90），下方留一大片
 *      空白。现在用 LWC 的 autoSize + flex 分配，K 线 : 成交量 = 3:1，永远吃满
 *
 * 另外补了一个标的切换器到顶栏：去掉自选表后总得有个换标的的入口，
 * 但它是工具按钮，不是一张占满纵向空间的表。
 *
 * 访问：/proto/app
 */
import { useEffect, useRef, useState } from "react";
import {
  Layout, Menu, Segmented, Tag, Space,
  Typography, Badge, Input, Button, Tooltip, theme as antdTheme, ConfigProvider, Select,
} from "antd";
import {
  LineChartOutlined, FundOutlined, ThunderboltOutlined, StarOutlined,
  FileTextOutlined, ApartmentOutlined, PieChartOutlined, BookOutlined,
  SettingOutlined, MoonOutlined, SunOutlined, SearchOutlined,
  RobotOutlined, ArrowUpOutlined, ArrowDownOutlined,
  LeftOutlined, RightOutlined, ReloadOutlined,
} from "@ant-design/icons";
import {
  createChart, CandlestickSeries, HistogramSeries,
  type IChartApi, type ISeriesApi, type UTCTimestamp,
} from "lightweight-charts";
import { DARK, LIGHT, FONT, SIZE, antdTheme as buildTheme, type Palette } from "@/theme/tokens";
import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";

const { Sider, Header, Content, Footer } = Layout;
const { Text } = Typography;

// ---------------------------------------------------------------- 数据
type Bar = { datetime: string; open: number; close: number; high: number; low: number; vol: number };
type Quote = { name: string; price: number; change_pct: number };

const UNIVERSE = [
  { value: "600519", label: "600519 贵州茅台" },
  { value: "000858", label: "000858 五粮液" },
  { value: "600036", label: "600036 招商银行" },
  { value: "601318", label: "601318 中国平安" },
  { value: "000001", label: "000001 平安银行" },
  { value: "300750", label: "300750 宁德时代" },
];

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

function useQuote(code: string) {
  const [q, setQ] = useState<Quote | null>(null);
  useEffect(() => {
    fetch(`/api/quote?codes=${code}`)
      .then((r) => r.json())
      .then((d) => setQ(d?.data?.[code] ?? null))
      .catch(() => {});
  }, [code]);
  return q;
}

// ---------------------------------------------------------------- 图表
// 两个绘图组件共用同一套生命周期纪律：
//   · 建实例的 effect **不依赖 palette** —— 依赖了切主题会销毁重建，
//     series 的 cleanup 随后 removeSeries 打到已销毁实例上，整页白屏（踩过）
//   · autoSize: true —— 由容器决定尺寸，图表永远填满，不留固定高度造成的空白

// 同一个 chart 里放两个 pane（K 线 + 成交量）。
//
// 为什么必须同一个实例：v4 曾用两个独立 chart 拼成上下两段，结果
//   · 左右边缘对不齐（两个实例各自计算价格轴宽度，差几像素）
//   · 缩放/十字光标不联动（各管各的 timeScale）
//   · 多一份 WebGL/canvas 开销
// pane API 天然解决这三件事：时间轴是共享的，缩放自动同步。
function PriceChart({ bars, palette }: { bars: Bar[]; palette: Palette }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const paneRO = useRef<ResizeObserver | null>(null);

  // 建实例：**不依赖 palette**。依赖了切主题会销毁重建，series 的 cleanup
  // 随后 removeSeries 打到已销毁实例上，整页白屏（v3 踩过）。
  useEffect(() => {
    if (!ref.current) return;
    const c = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: "#6B7385", fontSize: 10, attributionLogo: true },
    });
    chartRef.current = c;
    return () => {
      paneRO.current?.disconnect();
      paneRO.current = null;
      candleRef.current = null;
      volRef.current = null;
      chartRef.current = null;
      c.remove();
    };
  }, []);

  // 主题：只换色
  useEffect(() => {
    const c = chartRef.current;
    if (!c) return;
    c.applyOptions({
      layout: { textColor: palette.textTertiary, background: { color: "transparent" } },
      grid: { vertLines: { color: palette.border }, horzLines: { color: palette.border } },
      rightPriceScale: {
        borderColor: palette.border,
        scaleMargins: { top: 0.06, bottom: 0.06 },
        // 边缘刻度宁可不显示，也不要露半截数字（canvas 会裁掉）
        entireTextOnly: true,
      },
      timeScale: { borderColor: palette.border, timeVisible: false },
      crosshair: {
        mode: 1,
        vertLine: { color: palette.textTertiary, style: 3, labelBackgroundColor: palette.raised },
        horzLine: { color: palette.textTertiary, style: 3, labelBackgroundColor: palette.raised },
      },
    });
    candleRef.current?.applyOptions({
      upColor: palette.up, downColor: palette.down,
      wickUpColor: palette.up, wickDownColor: palette.down,
    });
  }, [palette]);

  // 数据：K 线在 pane 0，成交量在 pane 1
  useEffect(() => {
    const c = chartRef.current;
    if (!c || !bars.length) return;

    const toTs = (d: string) => (Date.parse(d + "T00:00:00Z") / 1000) as UTCTimestamp;

    let candle = candleRef.current;
    if (!candle) {
      candle = c.addSeries(CandlestickSeries, {
        upColor: palette.up, downColor: palette.down, borderVisible: false,
        wickUpColor: palette.up, wickDownColor: palette.down,
      }, 0);
      candleRef.current = candle;
    }
    candle.setData(bars.map((b) => ({
      time: toTs(b.datetime), open: b.open, high: b.high, low: b.low, close: b.close,
    })));

    let vol = volRef.current;
    if (!vol) {
      vol = c.addSeries(HistogramSeries, { priceFormat: { type: "volume" } }, 1);
      volRef.current = vol;
      // 成交量占整体约 1/4：图表 resize 时按比例给两个 pane 定高。
      // 不设的话两个 pane 等高，K 线会被压扁。
      const setPaneHeights = () => {
        const panes = c.panes();
        if (panes.length < 2) return;
        const total = ref.current?.clientHeight ?? 0;
        if (total < 80) return;
        panes[1].setHeight(Math.max(48, Math.round(total * 0.24)));
      };
      setPaneHeights();
      const ro = new ResizeObserver(setPaneHeights);
      if (ref.current) ro.observe(ref.current);
      paneRO.current = ro;
    }
    vol.setData(bars.map((b, i) => ({
      time: toTs(b.datetime),
      value: b.vol,
      color: i > 0 && b.close >= bars[i - 1].close ? `${palette.up}55` : `${palette.down}55`,
    })));

    c.timeScale().fitContent();
  }, [bars, palette]);

  return <div ref={ref} style={{ width: "100%", height: "100%" }} />;
}

// ---------------------------------------------------------------- 数字
// 所有钱/百分比都走它：强制等宽 + 涨跌色，不直接写字
function Num({ v, digits = 2, pct = false, palette }: {
  v: number | null | undefined; digits?: number; pct?: boolean; palette: Palette;
}) {
  if (v == null || Number.isNaN(v)) {
    return <span style={{ fontFamily: FONT.mono, color: palette.textTertiary }}>—</span>;
  }
  const color = pct ? (v > 0 ? palette.up : v < 0 ? palette.down : palette.textSecondary) : palette.text;
  return (
    <span style={{ fontFamily: FONT.mono, fontVariantNumeric: "tabular-nums", color }}>
      {v > 0 && pct ? "+" : ""}{v.toFixed(digits)}{pct ? "%" : ""}
    </span>
  );
}

// ---------------------------------------------------------------- 主画布
function MainCanvas({ palette, code }: { palette: Palette; code: string }) {
  const { bars, err } = useKline(code);
  const quote = useQuote(code);
  const [view, setView] = useState<string>("k");

  const last = bars[bars.length - 1];
  const prev = bars[bars.length - 2];
  const pct = last && prev ? ((last.close - prev.close) / prev.close) * 100 : 0;

  return (
    // 整列 flex：header 固定，图表区 flex:1 吃满剩余高度（这是 v3 留白的原因）
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {/* 头部：标的名 + 大数字。视觉焦点，不塞别的东西 */}
      <div style={{
        display: "flex", alignItems: "flex-end", gap: 24,
        paddingBottom: 10, borderBottom: `1px solid ${palette.border}`, flex: "0 0 auto",
      }}>
        <div>
          <Space size={8} align="baseline">
            <span style={{ fontSize: SIZE.lg, fontWeight: 600, color: palette.text }}>
              {quote?.name ?? UNIVERSE.find((u) => u.value === code)?.label.split(" ")[1] ?? "—"}
            </span>
            <span style={{ fontFamily: FONT.mono, fontSize: SIZE.xs, color: palette.textTertiary }}>{code}</span>
            <Tag style={{ fontFamily: FONT.mono, fontSize: 10, marginInlineEnd: 0 }}>日线 · 前复权</Tag>
          </Space>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginTop: 2 }}>
            <span style={{
              fontFamily: FONT.mono, fontSize: SIZE.xxl, fontWeight: 500,
              color: pct >= 0 ? palette.up : palette.down,
              fontVariantNumeric: "tabular-nums", lineHeight: 1.1,
            }}>
              {last ? last.close.toFixed(2) : "—"}
            </span>
            <span style={{ fontFamily: FONT.mono, fontSize: SIZE.md, color: pct >= 0 ? palette.up : palette.down }}>
              {pct >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />} {Math.abs(pct).toFixed(2)}%
            </span>
          </div>
        </div>

        {/* OHLC：右对齐，等宽，和左边的价格同一视觉节奏 */}
        <div style={{ marginLeft: "auto", display: "flex", gap: 24 }}>
          {([
            ["开", last?.open], ["高", last?.high], ["低", last?.low],
            ["量", last ? last.vol / 1e4 : null], ["换手", quote ? (quote as unknown as { turnover_pct?: number }).turnover_pct ?? null : null],
          ] as const).map(([k, v]) => (
            <div key={k} style={{ textAlign: "right" }}>
              <div style={{ fontSize: SIZE.xs, color: palette.textTertiary }}>{k}</div>
              <div style={{ fontSize: SIZE.sm }}>
                <Num v={v} digits={k === "量" || k === "换手" ? 1 : 2} palette={palette} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 视图切换：Segmented 放到工具条，不占内容高度 */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", flex: "0 0 auto" }}>
        <Segmented
          size="small"
          value={view}
          onChange={(v) => setView(String(v))}
          options={[
            { label: "K 线", value: "k" },
            { label: "相关性", value: "corr" },
            { label: "回测", value: "bt" },
          ]}
        />
        {err && <Text type="danger" style={{ fontSize: SIZE.xs }}>{err}</Text>}
        <span style={{ marginLeft: "auto", fontSize: 10, color: palette.textTertiary, fontFamily: FONT.mono }}>
          {bars.length} 根 · 截至 {last?.datetime ?? "—"}
        </span>
      </div>

      {/* 图表区：flex:1 + minHeight:0 才能真正压缩到父容器高度 */}
      <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        {view === "k" && <PriceChart bars={bars} palette={palette} />}
        {view === "corr" && <Placeholder palette={palette} text="相关性热力图（ECharts）· M2-5" />}
        {view === "bt" && <Placeholder palette={palette} text="净值 + 回撤双 pane（LWC）· M2-5" />}
      </div>
    </div>
  );
}

function Placeholder({ palette, text }: { palette: Palette; text: string }) {
  return (
    <div style={{
      flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
      border: `1px dashed ${palette.border}`, borderRadius: 4,
      color: palette.textTertiary, fontSize: SIZE.sm,
    }}>{text}</div>
  );
}

// ---------------------------------------------------------------- Agent 栏
// 可折叠：展开 360px 显示对话；折叠 44px 只留竖条。
// 折叠的意义：看图时把空间全给图表，需要问的时候再展开。
function AgentPanel({ palette, collapsed, onToggle }: {
  palette: Palette; collapsed: boolean; onToggle: () => void;
}) {
  if (collapsed) {
    return (
      <div style={{
        borderLeft: `1px solid ${palette.border}`, background: palette.panel,
        display: "flex", flexDirection: "column", alignItems: "center",
        paddingTop: 12, gap: 12,
      }}>
        <Tooltip title="展开 Agent" placement="left">
          <Button size="small" type="text" icon={<LeftOutlined />} onClick={onToggle} />
        </Tooltip>
        <RobotOutlined style={{ color: palette.accent, fontSize: 14 }} />
        <div style={{
          writingMode: "vertical-rl", fontSize: SIZE.xs, color: palette.textTertiary,
          letterSpacing: "0.1em", marginTop: 4,
        }}>AGENT</div>
      </div>
    );
  }

  return (
    <div style={{
      borderLeft: `1px solid ${palette.border}`, background: palette.panel,
      display: "flex", flexDirection: "column", height: "100%", minHeight: 0,
    }}>
      <div style={{
        padding: "0 12px", height: 40, borderBottom: `1px solid ${palette.border}`,
        display: "flex", alignItems: "center", gap: 8, flex: "0 0 auto",
      }}>
        <RobotOutlined style={{ color: palette.accent, fontSize: 14 }} />
        <span style={{ fontSize: SIZE.sm, fontWeight: 500, color: palette.text }}>Agent</span>
        <Badge status="processing" style={{ marginLeft: 4 }} />
        <Tooltip title="收起" placement="left">
          <Button
            size="small" type="text" icon={<RightOutlined />}
            onClick={onToggle} style={{ marginLeft: "auto" }}
          />
        </Tooltip>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ fontSize: 10, color: palette.textTertiary, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          当前页面：复盘看板
        </div>
        <div style={{ fontSize: SIZE.xs, color: palette.textSecondary, lineHeight: 1.7 }}>
          600519 贵州茅台 日线 180 根 · 现价 1309.69 · 涨跌 -1.67%<br />
          上涨 1941 / 下跌 3055 · 涨停 50 · 最高 4 板
        </div>

        <div style={{ background: palette.raised, borderRadius: 4, padding: "8px 10px", fontSize: SIZE.sm, color: palette.text }}>
          这波下跌是普跌还是结构性的？
        </div>
        <div style={{ fontSize: SIZE.sm, color: palette.textSecondary, lineHeight: 1.75 }}>
          上涨 1941 家、下跌 3055 家，属普跌结构；涨停 50 家说明仍有局部热点，
          但赚钱效应集中在少数连板股。
          <div style={{ marginTop: 8, fontSize: 10, color: palette.textTertiary, fontFamily: FONT.mono }}>
            数据 as-of 2026-10-21 · run 7f3a2c
          </div>
        </div>
      </div>

      <div style={{ borderTop: `1px solid ${palette.border}`, padding: 10, flex: "0 0 auto" }}>
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
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [agentCollapsed, setAgentCollapsed] = useState(false);
  const palette = dark ? DARK : LIGHT;

  return (
    <ConfigProvider theme={{
      ...buildTheme(palette),
      algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    }}>
      <div style={{ position: "fixed", inset: 0, background: palette.bg, fontFamily: FONT.ui }}>
        <Layout style={{ height: "100%", background: palette.bg }}>
          <Sider
            width={176}
            collapsedWidth={52}
            collapsed={navCollapsed}
            collapsible
            trigger={null}
            theme="light"
            style={{ background: palette.panel, borderRight: `1px solid ${palette.border}` }}
          >
            <div
              onClick={() => setNavCollapsed((c) => !c)}
              style={{
                height: 48, display: "flex", alignItems: "center", gap: 8, padding: "0 14px",
                borderBottom: `1px solid ${palette.border}`, cursor: "pointer",
              }}
            >
              <div style={{
                width: 20, height: 20, borderRadius: 3, background: palette.accent, flex: "0 0 auto",
                display: "flex", alignItems: "center", justifyContent: "center",
                color: "#fff", fontSize: 11, fontWeight: 700,
              }}>A</div>
              {!navCollapsed && (
                <span style={{ fontSize: SIZE.md, fontWeight: 600, color: palette.text }}>AlphaCopilot</span>
              )}
            </div>
            <Menu
              mode="inline"
              selectedKeys={["/daily-review"]}
              items={NAV}
              style={{ background: "transparent", borderInlineEnd: "none", fontSize: SIZE.sm, paddingTop: 4 }}
            />
          </Sider>

          <Layout style={{ background: palette.bg }}>
            <Header style={{
              height: 48, lineHeight: "48px", padding: "0 16px", background: palette.panel,
              borderBottom: `1px solid ${palette.border}`, display: "flex", alignItems: "center", gap: 12,
            }}>
              {/* 标的切换：去掉自选表后的替代入口。它是工具，不占纵向空间 */}
              <Select
                size="small"
                value={code}
                onChange={setCode}
                options={UNIVERSE}
                style={{ width: 165, fontSize: SIZE.xs }}
                variant="filled"
              />
              <Segmented
                size="small"
                options={[{ label: "自选", value: "watch" }, { label: "盘面", value: "market" }, { label: "研究", value: "research" }]}
                defaultValue="market"
              />
              <Input
                size="small"
                prefix={<SearchOutlined style={{ color: palette.textTertiary }} />}
                placeholder="搜代码/名称，或 ⌘K 命令"
                style={{ width: 240, fontSize: SIZE.xs }}
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

            {/* 主区：主画布 1fr + Agent 栏（展开 360 / 折叠 44） */}
            <Content style={{
              display: "grid",
              gridTemplateColumns: `1fr ${agentCollapsed ? 44 : 360}px`,
              transition: "grid-template-columns 160ms ease",
              overflow: "hidden",
            }}>
              <div style={{ padding: "12px 16px", minWidth: 0, overflow: "hidden" }}>
                <MainCanvas palette={palette} code={code} />
              </div>
              <AgentPanel
                palette={palette}
                collapsed={agentCollapsed}
                onToggle={() => setAgentCollapsed((c) => !c)}
              />
            </Content>

            <Footer style={{
              height: 28, lineHeight: "28px", padding: "0 16px", background: palette.panel,
              borderTop: `1px solid ${palette.border}`,
              display: "flex", alignItems: "center", gap: 14,
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
