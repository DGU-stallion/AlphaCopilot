// frontend/src/types/research.ts — Research API response types

export interface StockQuote {
  code: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  turnover: number;
  pe: number;
  pb: number;
  marketCap: number;
  high: number;
  low: number;
  open: number;
  prevClose: number;
}

export interface IndexQuote {
  code: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  change_pct: number;
}

export interface SectorFlowItem {
  name: string;
  change: number;
  netInflow: number;
}

export interface MarketOverview {
  indices: IndexQuote[];
  sectorFlow: SectorFlowItem[];
  emotion: MarketEmotion;
}

export interface MarketEmotion {
  limitUp: number;
  limitDown: number;
  maxConsecutive: number;
  sealRate: number;
  failRate: number;
  ladder: LadderStock[];
}

export interface LadderStock {
  code: string;
  name: string;
  consecutive: number;
}

export interface KlineBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface RadarData {
  tracks: RadarTrack[];
}

export interface RadarTrack {
  name: string;
  items: RadarItem[];
}

export interface RadarItem {
  title: string;
  url: string;
  source: string;
  time: string;
  summary?: string;
}

export interface ValuationData {
  price: number;
  pe: number;
  pb: number;
  forwardPE?: number;
  peg?: number;
  digestYears?: number;
  consensus?: Record<string, unknown>;
}

export interface FinancialItem {
  label: string;
  value: number | string;
}

export interface Financials {
  items: FinancialItem[];
}

export interface PortfolioHolding {
  code: string;
  name: string;
  shares: number;
  cost: number;
  price: number;
  profit: number;
  profitPercent: number;
  marketValue: number;
}

export interface ClosedPosition {
  code: string;
  name: string;
  date: string;
  price: number;
  shares: number;
  cost: number;
  profit: number;
}

export interface PortfolioData {
  holdings: PortfolioHolding[];
  closed: ClosedPosition[];
  totalProfit: number;
  totalMarketValue: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface LLMConfig {
  provider: string;
  baseURL: string;
  apiKey: string;
  model: string;
}

export interface Report {
  id: string;
  name: string;
  tags: string[];
  createdAt: string;
}


// --- Page-level types used by DailyReview, StockData, Intel, Portfolio, MyReports, Watchlist ---

export interface Quote {
  name: string;
  code: string;
  price: number;
  change_pct: number;
  pe_ttm?: number;
  pb?: number;
  turnover_pct?: number;
}

export interface PageMarketOverview {
  sentiment?: MarketSentiment;
  sectors: SectorRow[];
}

export interface MarketSentiment {
  date?: string;
  breadth?: string;
  speculation?: string;
  up: number;
  down: number;
  flat: number;
  zt: number;
  zt_real: number;
  dt: number;
  dt_real: number;
  active: number;
}

export interface SectorRow {
  name: string;
  pct: number;
  net: number;
  inflow: number;
  outflow: number;
  firms: number;
}

export interface ShortTermEmotion {
  date?: string;
  zt_count: number;
  dt_count: number;
  max_boards: number;
  lianban_count: number;
  seal_rate: number | null;
  break_rate: number | null;
  promotion_rate: number | null;
  lianban_stocks: LianbanStock[];
}

export interface LianbanStock {
  code: string;
  name: string;
  boards: number;
  price: number;
  pct: number;
  amount: number | null;
  float_cap: number | null;
  industry: string;
}

export interface TurnoverTop {
  updated?: string;
  stocks: TurnoverStock[];
}

export interface TurnoverStock {
  code: string;
  name: string;
  price: number | null;
  pct: number | null;
  amount: number | null;
  mcap: number | null;
  industry: string;
}

export interface GlobalIndex {
  key: string;
  name: string;
  region: string;
  price: number | null;
  change_pct: number | null;
}

export interface Valuation {
  code: string;
  name: string;
  price: number;
  pe_ttm: number | null;
  pb: number | null;
  mcap_yi: number | null;
  eps_26e: number | null;
  pe_26e: number | null;
  peg: number | null;
  digest_years: number | null;
  analyst_count: number;
  forecast_note?: string;
}

export interface ResearchReport {
  title: string;
  publishDate?: string;
  orgSName?: string;
  pdfUrl?: string;
  emRatingName?: string;
}

export interface NewsItem {
  新闻标题: string;
  新闻链接?: string;
  发布时间?: string;
}

export interface ValMetric {
  current: number;
  min: number;
  max: number;
  p20: number;
  p50: number;
  p80: number;
  percentile: number;
  n: number;
}

export interface ValPercentile {
  period: string;
  metrics: {
    pe_ttm?: ValMetric;
    pb?: ValMetric;
  };
}

export interface StockFinancials {
  period?: string;
  revenue?: string;
  revenue_yoy?: string;
  net_profit?: string;
  net_profit_yoy?: string;
  eps?: string;
  roe?: string;
  gross_margin?: string;
  net_margin?: string;
  bvps?: string;
  op_cf_ps?: string;
}

export interface Announcement {
  date: string;
  title: string;
  type?: string;
  url?: string;
}

export interface MarginRow {
  date: string;
  rzye: number;
  rqye: number;
}

export interface BlockTradeRow {
  date: string;
  price: number;
  premium_pct: number;
  buyer: string;
  seller: string;
}

export interface HolderRow {
  holder_num: number;
  change_ratio: number | null;
}

export interface DividendRow {
  date: string;
  bonus_rmb: number;
}

export interface FundFlowRow {
  main_net: number;
}

export interface DragonTiger {
  records: DragonTigerRecord[];
  seats: { buy: DragonTigerSeat[]; sell: DragonTigerSeat[] };
}

export interface DragonTigerRecord {
  date: string;
  reason: string;
  net_buy: number;
}

export interface DragonTigerSeat {
  name: string;
  net: number;
}

export interface Lockup {
  upcoming: LockupItem[];
  history: LockupItem[];
}

export interface LockupItem {
  date: string;
  type: string;
  ratio?: number | null;
}

export interface Blocks {
  concept_tags: string[];
}

export interface HotConcept {
  concept: string;
}

export interface QaRow {
  question: string;
  answer: string;
  ask_time: string;
}

export interface GlobalStock {
  code: string;
  name: string;
  market: string;
  quote: GlobalStockQuote;
  metrics?: GlobalStockMetrics;
}

export interface GlobalStockQuote {
  price: number | null;
  change_pct: number | null;
  mcap: number | null;
  amount: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  prev_close: number | null;
}

export interface GlobalStockMetrics {
  report_date: string;
  revenue: number | null;
  revenue_yoy: number | null;
  net_profit: number | null;
  eps: number | null;
  roe: number | null;
  gross_margin: number | null;
  net_margin: number | null;
  debt_ratio: number | null;
}

export interface Industry {
  key: string;
  name: string;
  accent: string;
  items: IndustryItem[];
}

export interface IndustryItem {
  title: string;
  zh?: string;
  url: string;
  source: string;
  time: string;
}

export interface MyReport {
  id: string;
  name: string;
  industry: string;
  size: number;
  ts: number;
}

export interface PagePortfolioData {
  holdings: PageHolding[];
  closed: PageClosedPosition[];
  totals?: PagePortfolioTotals;
  realized_pnl: number;
  updated?: string;
}

export interface PageHolding {
  code: string;
  name: string;
  shares: number;
  cost: number;
  price: number;
  market_value: number;
  pnl: number;
  pnl_pct: number;
}

export interface PageClosedPosition {
  code: string;
  name: string;
  date: string;
  price: number;
  shares: number;
  cost: number;
  pnl: number;
  pnl_pct: number;
}

export interface PagePortfolioTotals {
  market_value: number;
  cost: number;
  pnl: number;
  pnl_pct: number;
}

export interface PageRadarData {
  generated_at?: string;
  recent_days?: number;
  stats: { total_sources: number };
  industries: Industry[];
}
