import { authHeaders } from "@/lib/apiAuth";
import type {
  StockQuote,
  IndexQuote,
  MarketOverview,
  MarketEmotion,
  KlineBar,
  RadarData,
  ValuationData,
  Financials,
  PortfolioData,
  PortfolioHolding,
  ChatMessage,
  LLMConfig,
  Report,
} from "@/types/research";
import type {
  Quote,
  PageMarketOverview,
  ShortTermEmotion,
  TurnoverTop,
  GlobalIndex,
  Valuation,
  ResearchReport,
  NewsItem,
  ValPercentile,
  StockFinancials,
  Announcement,
  MarginRow,
  BlockTradeRow,
  HolderRow,
  DividendRow,
  FundFlowRow,
  DragonTiger,
  Lockup,
  Blocks,
  HotConcept,
  QaRow,
  GlobalStock,
  MyReport,
  PagePortfolioData,
  PageRadarData,
} from "@/types/research";

const RESEARCH_BASE = "/api/research";

export class ResearchApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ResearchApiError";
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const { headers, ...rest } = options ?? {};
  const mergedHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...authHeaders(),
  };
  if (headers) {
    new Headers(headers).forEach((value, key) => {
      mergedHeaders[key] = value;
    });
  }
  const res = await fetch(`${RESEARCH_BASE}${path}`, {
    ...rest,
    headers: mergedHeaders,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || body.message || detail;
    } catch {
      /* ignore */
    }
    throw new ResearchApiError(detail, res.status);
  }
  const text = await res.text();
  if (!text) return {} as T;
  return JSON.parse(text) as T;
}

export const researchApi = {
  // Health
  getHealth: () => request<{ ok: boolean; service: string }>("/health"),

  // Market
  getMarketOverview: () => request<{ data: MarketOverview }>("/market/overview"),
  getMarketEmotion: () => request<{ data: MarketEmotion }>("/market/emotion"),
  getTurnoverTop: () => request<{ data: unknown[] }>("/market/turnover-top"),

  // Global
  getGlobalIndices: () => request<{ data: unknown[] }>("/global/indices"),
  getGlobalStock: (symbol: string) =>
    request<{ data: unknown }>(`/global/stock?symbol=${encodeURIComponent(symbol)}`),

  // A-Stock indices
  getIndices: () => request<{ data: IndexQuote[] }>("/indices"),

  // Quote & data
  getQuote: (codes: string) =>
    request<{ data: StockQuote[] }>(`/quote?codes=${encodeURIComponent(codes)}`),
  getKline: (code: string, category = 4, offset = 60) =>
    request<{ data: KlineBar[] }>(`/kline?code=${code}&category=${category}&offset=${offset}`),
  getFinancials: (code: string) => request<{ data: Financials }>(`/financials?code=${code}`),
  getValuation: (code: string) => request<{ data: ValuationData }>(`/valuation?code=${code}`),
  getValuationPercentile: (code: string) =>
    request<{ data: unknown }>(`/valuation/percentile?code=${code}`),
  getInfo: (code: string) => request<{ data: unknown }>(`/info?code=${code}`),
  getNews: (code: string, limit = 20) =>
    request<{ data: unknown[] }>(`/news?code=${code}&limit=${limit}`),
  getReports: (code: string, pages = 2) =>
    request<{ data: unknown[] }>(`/reports?code=${code}&pages=${pages}`),
  getAnnouncements: (code: string) => request<{ data: unknown[] }>(`/announcements?code=${code}`),
  getDisclosure: (code: string) => request<{ data: unknown[] }>(`/disclosure?code=${code}`),
  getFinance: (code: string) => request<{ data: unknown[] }>(`/finance?code=${code}`),

  // Radar
  getRadar: () => request<{ data: RadarData }>("/radar"),
  refreshRadar: () => request<{ data: RadarData }>("/radar/refresh", { method: "POST" }),

  // Portfolio
  getPortfolio: () => request<{ data: PortfolioData }>("/portfolio"),
  addHolding: (code: string, shares: number, cost: number) =>
    request<{ data: PortfolioHolding }>("/portfolio/holding", {
      method: "POST",
      body: JSON.stringify({ code, shares, cost }),
    }),
  removeHolding: (code: string) =>
    request<{ data: unknown }>(`/portfolio/holding?code=${code}`, { method: "DELETE" }),
  closePosition: (code: string, date: string, price: number, shares: number, cost: number) =>
    request<{ data: unknown }>("/portfolio/close", {
      method: "POST",
      body: JSON.stringify({ code, date, price, shares, cost }),
    }),
  removeClose: (index: number) =>
    request<{ data: unknown }>(`/portfolio/close?index=${index}`, { method: "DELETE" }),
  refreshPortfolio: () => request<{ data: PortfolioData }>("/portfolio/refresh", { method: "POST" }),

  // Reports
  listReports: () => request<{ data: Report[] }>("/myreports"),
  uploadReport: (name: string, contentB64: string) =>
    request<{ data: Report }>("/myreports", {
      method: "POST",
      body: JSON.stringify({ name, content_b64: contentB64 }),
    }),
  deleteReport: (rid: string) =>
    request<{ data: { ok: boolean } }>(`/myreports/${rid}`, { method: "DELETE" }),
  reportFileUrl: (rid: string) => `${RESEARCH_BASE}/myreports/file/${rid}`,

  // 资金面
  getMargin: (code: string) => request<{ data: unknown }>(`/margin?code=${code}`),
  getBlockTrade: (code: string) => request<{ data: unknown }>(`/block-trade?code=${code}`),
  getHolders: (code: string) => request<{ data: unknown }>(`/holders?code=${code}`),
  getDividend: (code: string) => request<{ data: unknown }>(`/dividend?code=${code}`),
  getFundFlow: (code: string) => request<{ data: unknown }>(`/fund-flow?code=${code}`),
  getDragonTiger: (code: string) => request<{ data: unknown }>(`/dragon-tiger?code=${code}`),
  getLockup: (code: string) => request<{ data: unknown }>(`/lockup?code=${code}`),
  getBlocks: (code: string) => request<{ data: unknown }>(`/blocks?code=${code}`),
  getHotConcepts: (code: string) => request<{ data: unknown }>(`/hot-concepts?code=${code}`),
  getInvestorQA: (code: string) => request<{ data: unknown }>(`/investor-qa?code=${code}`),
  getIndustry: (top = 20) => request<{ data: unknown[] }>(`/industry?top=${top}`),

  // Chat (streaming NDJSON — returns raw Response for caller to handle)
  chat: (messages: ChatMessage[], context: string, llm: LLMConfig) =>
    fetch(`${RESEARCH_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ messages, context, llm }),
    }),
};


// --- Convenience aliases matching old `api.*` call patterns used by research pages ---

export type {
  Quote,
  PageMarketOverview as MarketOverview,
  ShortTermEmotion,
  TurnoverTop,
  GlobalIndex,
  Valuation,
  ResearchReport as Report,
  NewsItem,
  ValPercentile,
  ValMetric,
  StockFinancials as Financials,
  Announcement,
  MarginRow,
  BlockTradeRow,
  HolderRow,
  DividendRow,
  FundFlowRow,
  DragonTiger,
  Lockup,
  Blocks,
  HotConcept,
  QaRow,
  GlobalStock,
  Industry,
  MyReport,
  PagePortfolioData as PortfolioData,
  PageRadarData as RadarData,
} from "@/types/research";

// Re-export ResearchApiError as ApiError so pages can use it in place of the old api's ApiError
export { ResearchApiError as ApiError };

/**
 * Page-facing research API — mirrors the old `api.*` call patterns.
 * Pages import this as `researchApi` and call e.g. `researchApi.indices()`.
 */
export const researchPageApi = {
  // Market
  indices: () => researchApi.getIndices().then((r) => r.data),
  globalIndices: () => researchApi.getGlobalIndices().then((r) => r.data as unknown as GlobalIndex[]),
  marketOverview: () => researchApi.getMarketOverview().then((r) => r.data as unknown as PageMarketOverview),
  emotion: async () => {
    const res = await request<{ data: ShortTermEmotion }>("/market/emotion");
    return res.data;
  },
  turnoverTop: () => researchApi.getTurnoverTop().then((r) => r.data as unknown as TurnoverTop),

  // Quote
  quote: (codes: string) =>
    researchApi.getQuote(codes).then((r) => {
      const map: Record<string, Quote> = {};
      for (const q of r.data as unknown as Quote[]) map[q.code] = q;
      return map;
    }),

  // Radar
  radar: async () => {
    const res = await request<{ data: PageRadarData }>("/radar");
    return res.data;
  },
  radarRefresh: async () => {
    const res = await request<{ data: PageRadarData }>("/radar/refresh", { method: "POST" });
    return res.data;
  },

  // Stock data
  valuation: async (code: string) => {
    const res = await request<{ data: Valuation }>(`/valuation?code=${code}`);
    return res.data;
  },
  reports: async (code: string) => {
    const res = await request<{ data: ResearchReport[] }>(`/reports?code=${code}&pages=2`);
    return res.data ?? [];
  },
  percentile: async (code: string) => {
    const res = await request<{ data: ValPercentile }>(`/valuation/percentile?code=${code}`);
    return res.data;
  },
  financials: async (code: string) => {
    const res = await request<{ data: StockFinancials }>(`/financials?code=${code}`);
    return res.data;
  },
  announcements: async (code: string) => {
    const res = await request<{ data: Announcement[] }>(`/announcements?code=${code}`);
    return res.data ?? [];
  },
  news: async (code: string) => {
    const res = await request<{ data: NewsItem[] }>(`/news?code=${code}&limit=20`);
    return res.data ?? [];
  },
  globalStock: async (symbol: string) => {
    const res = await request<{ data: GlobalStock }>(`/global/stock?symbol=${encodeURIComponent(symbol)}`);
    return res.data;
  },

  // 资金面
  margin: async (code: string) => {
    const res = await request<{ data: MarginRow[] }>(`/margin?code=${code}`);
    return res.data ?? [];
  },
  blockTrade: async (code: string) => {
    const res = await request<{ data: BlockTradeRow[] }>(`/block-trade?code=${code}`);
    return res.data ?? [];
  },
  holders: async (code: string) => {
    const res = await request<{ data: HolderRow[] }>(`/holders?code=${code}`);
    return res.data ?? [];
  },
  dividend: async (code: string) => {
    const res = await request<{ data: DividendRow[] }>(`/dividend?code=${code}`);
    return res.data ?? [];
  },
  fundFlow: async (code: string) => {
    const res = await request<{ data: FundFlowRow[] }>(`/fund-flow?code=${code}`);
    return res.data ?? [];
  },
  dragonTiger: async (code: string) => {
    const res = await request<{ data: DragonTiger }>(`/dragon-tiger?code=${code}`);
    return res.data;
  },
  lockup: async (code: string) => {
    const res = await request<{ data: Lockup }>(`/lockup?code=${code}`);
    return res.data;
  },
  blocks: async (code: string) => {
    const res = await request<{ data: Blocks }>(`/blocks?code=${code}`);
    return res.data;
  },
  hotConcepts: async (code: string) => {
    const res = await request<{ data: HotConcept[] }>(`/hot-concepts?code=${code}`);
    return res.data ?? [];
  },
  investorQa: async (code: string) => {
    const res = await request<{ data: QaRow[] }>(`/investor-qa?code=${code}`);
    return res.data ?? [];
  },

  // Portfolio
  portfolio: async () => {
    const res = await request<{ data: PagePortfolioData }>("/portfolio");
    return res.data;
  },
  refreshPortfolio: async () => {
    const res = await request<{ data: PagePortfolioData }>("/portfolio/refresh", { method: "POST" });
    return res.data;
  },
  addHolding: async (code: string, shares: number, cost: number) => {
    const res = await request<{ data: PagePortfolioData }>("/portfolio/holding", {
      method: "POST",
      body: JSON.stringify({ code, shares, cost }),
    });
    return res.data;
  },
  removeHolding: async (code: string) => {
    const res = await request<{ data: PagePortfolioData }>(`/portfolio/holding?code=${code}`, { method: "DELETE" });
    return res.data;
  },
  closePosition: async (code: string, date: string, price: number, shares: number, cost: number) => {
    const res = await request<{ data: PagePortfolioData }>("/portfolio/close", {
      method: "POST",
      body: JSON.stringify({ code, date, price, shares, cost }),
    });
    return res.data;
  },
  removeClosed: async (i: number) => {
    const res = await request<{ data: PagePortfolioData }>(`/portfolio/close?index=${i}`, { method: "DELETE" });
    return res.data;
  },

  // My Reports
  myReports: async () => {
    const res = await request<{ data: MyReport[] }>("/myreports");
    return res.data ?? [];
  },
  uploadReport: async (name: string, contentB64: string) => {
    const res = await request<{ data: MyReport }>("/myreports", {
      method: "POST",
      body: JSON.stringify({ name, content_b64: contentB64 }),
    });
    return res.data;
  },
  deleteReport: async (rid: string) => {
    const res = await request<{ data: { ok: boolean } }>(`/myreports/${rid}`, { method: "DELETE" });
    return res.data;
  },
};

/** Download a report file by triggering a browser download */
export async function downloadReport(rid: string, filename: string): Promise<void> {
  const url = researchApi.reportFileUrl(rid);
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) throw new ResearchApiError(`下载失败 HTTP ${res.status}`, res.status);
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// --- Access key helpers (for Settings page, stored in localStorage) ---
const ACCESS_KEY_STORAGE = "vr_access_key";

export function loadAccessKey(): string {
  return window.localStorage.getItem(ACCESS_KEY_STORAGE) || "";
}

export function saveAccessKey(key: string): void {
  const trimmed = key.trim();
  if (trimmed) {
    window.localStorage.setItem(ACCESS_KEY_STORAGE, trimmed);
  } else {
    window.localStorage.removeItem(ACCESS_KEY_STORAGE);
  }
}
