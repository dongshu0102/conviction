// Thin client over the FinInsight API. Auth is deliberately simple for this
// MVP: the API key lives in localStorage, attached as X-Api-Key on every
// request. There is no session/cookie layer — that's a real gap versus a
// production auth system, consistent with the backend's own "unauthenticated
// user_id was Phase 3-4's known limitation" pattern: closing it further is a
// reasonable next step, not something silently pretended away here.

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://p8xpcshdn9.us-east-1.awsapprunner.com";
const STORAGE_KEY = "fininsight_api_key";

export function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}

export function setApiKey(key: string): void {
  window.localStorage.setItem(STORAGE_KEY, key);
}

export function clearApiKey(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const key = getApiKey();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (key) headers["X-Api-Key"] = key;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// --- Types (mirroring the backend's Pydantic schemas) -----------------------

export interface WatchlistItem {
  ticker: string;
  added_at: string;
  notes: string | null;
  list_name: string;
  target_price: number | null;
  alert_threshold_pct: number | null;
  added_price: number | null;
  added_pe: number | null;
}

export interface TriageSignals {
  day_move_pct: number | null;
  move_since_added_pct: number | null;
  momentum_1m_pct: number | null;
  pe_drift_pct: number | null;
  target_crossed: boolean;
  current_price: number | null;
  current_pe: number | null;
}

export interface TriageItem {
  ticker: string;
  list_name: string;
  triage_score: number;
  signals: TriageSignals;
  notes: string | null;
}

export interface TriageResponse {
  as_of: string;
  scoring_note: string;
  items: TriageItem[];
  tickers_excluded: string[];
}

export interface NewsArticle {
  ticker: string;
  title: string;
  published_at: string | null;
  source: string | null;
  url: string | null;
  snippet: string | null;
}

export interface WatchlistNewsResponse {
  news: Record<string, NewsArticle[]>;
  tickers_failed: string[];
}

export interface Portfolio {
  portfolio_id: string;
  name: string;
  created_at: string;
  holdings: { ticker: string; shares: number; cost_basis_per_share: number }[];
}

export interface PositionValue {
  ticker: string;
  shares: number;
  current_price: number;
  market_value: number;
  unrealized_gain: number;
  unrealized_gain_pct: number | null;
  weight: number | null;
}

export interface PortfolioValuation {
  portfolio_id: string;
  name: string;
  positions: PositionValue[];
  total_market_value: number;
  total_cost_basis: number;
  total_unrealized_gain: number;
  total_unrealized_gain_pct: number | null;
}

export interface DailyBrief {
  narrative: string;
  generated_at: string;
  unread_alert_count: number;
  watchlist_moves: { ticker: string; current_price: number; change_pct: number | null }[];
  portfolio_summaries: {
    portfolio_id: string;
    name: string;
    total_market_value: number;
    total_unrealized_gain_pct: number | null;
  }[];
}

// --- Calls --------------------------------------------------------------

export interface CompanyValuation {
  price: number;
}

// --- Factor scoring ---------------------------------------------------------

export interface FactorRawMetrics {
  price_to_earnings: number | null;
  return_on_equity: number | null;
  revenue_growth_yoy: number | null;
  momentum_1m_pct: number | null;
  market_cap: number | null;
}

export interface RankedFactorScore {
  ticker: string;
  as_of: string;
  composite_score: number | null;
  factors_used: number;
  value_z: number | null;
  quality_z: number | null;
  growth_z: number | null;
  momentum_z: number | null;
  size_z: number | null;
  raw: FactorRawMetrics;
}

export interface FactorScoreResponse {
  scoring_note: string;
  result: RankedFactorScore;
}

export interface FactorRankingResponse {
  scoring_note: string;
  results: RankedFactorScore[];
}

export interface FactorWeights {
  weight_value?: number;
  weight_quality?: number;
  weight_growth?: number;
  weight_momentum?: number;
  weight_size?: number;
}

function weightsToQuery(w?: FactorWeights): URLSearchParams {
  const params = new URLSearchParams();
  if (!w) return params;
  if (w.weight_value !== undefined) params.set("weight_value", String(w.weight_value));
  if (w.weight_quality !== undefined) params.set("weight_quality", String(w.weight_quality));
  if (w.weight_growth !== undefined) params.set("weight_growth", String(w.weight_growth));
  if (w.weight_momentum !== undefined) params.set("weight_momentum", String(w.weight_momentum));
  if (w.weight_size !== undefined) params.set("weight_size", String(w.weight_size));
  return params;
}

// --- Universe themes ---------------------------------------------------------

export interface UniverseTheme {
  name: string;
  description: string | null;
  created_at: string;
}

export interface UniverseThemeSummary {
  theme: UniverseTheme;
  member_count: number;
}

export interface ThemeSynthesisReport {
  theme_name: string;
  generated_at: string;
  tickers_covered: string[];
  tickers_excluded: string[];
  overview: string;
  common_threads: string;
  notable_divergences: string;
  key_risks: string;
  model_used: string;
}

// --- Risk parity construction ------------------------------------------------

export interface RiskParityAllocation {
  ticker: string;
  daily_volatility: number;
  target_weight: number;
  target_dollar_amount: number;
  current_price: number;
  suggested_shares: number;
}

export interface RiskParityConstructionResponse {
  as_of: string;
  total_investment: number;
  allocations: RiskParityAllocation[];
  excluded: string[];
  methodology_note: string;
}

// --- Portfolio risk analysis (volatility/correlation/VaR) -------------------

export interface SectorExposure {
  sector: string;
  weight: number;
}

export interface PairwiseCorrelation {
  ticker_a: string;
  ticker_b: string;
  correlation: number;
}

export interface PortfolioRiskAnalysis {
  portfolio_id: string;
  as_of: string;
  largest_position_weight: number | null;
  herfindahl_index: number | null;
  sector_exposures: SectorExposure[];
  weighted_avg_debt_to_equity: number | null;
  excluded_from_leverage_calc: string[];
  portfolio_daily_volatility: number | null;
  portfolio_annualized_volatility: number | null;
  parametric_var_95_1day_dollar: number | null;
  volatility_covered_weight: number | null;
  volatility_lookback_days_used: number | null;
  pairwise_correlations: PairwiseCorrelation[];
  excluded_from_volatility_calc: string[];
}

// --- ETF ingestion -----------------------------------------------------------

export interface EtfIngestResult {
  ticker: string;
  name: string;
  expense_ratio: number | null;
  aum: number | null;
}

// --- Earnings alerts -----------------------------------------------------------

export interface EarningsEvent {
  ticker: string;
  report_date: string;
  eps_estimated: number | null;
  eps_actual: number | null;
  revenue_estimated: number | null;
  revenue_actual: number | null;
}

export interface UpcomingEarningsResponse {
  events: EarningsEvent[];
}

export const api = {
  createApiKey: (userId: string, name: string) =>
    request<{ plaintext_key: string }>(
      `/api-keys?user_id=${encodeURIComponent(userId)}&name=${encodeURIComponent(name)}`,
      { method: "POST" }
    ),
  getWatchlist: () => request<WatchlistItem[]>("/watchlist"),
  addToWatchlist: (ticker: string) =>
    request<WatchlistItem>(`/watchlist/${encodeURIComponent(ticker.toUpperCase())}`, {
      method: "POST",
    }),
  listPortfolios: () => request<Portfolio[]>("/portfolios"),
  createPortfolio: (name: string) =>
    request<Portfolio>(`/portfolios?name=${encodeURIComponent(name)}`, { method: "POST" }),
  getPortfolioValuation: (id: string) =>
    request<PortfolioValuation>(`/portfolios/${id}/valuation`),
  getPortfolioRisk: (id: string) =>
    request<PortfolioRiskAnalysis>(`/portfolios/${id}/risk`),
  addHolding: (portfolioId: string, ticker: string, shares: number, costBasisPerShare: number) =>
    request(
      `/portfolios/${portfolioId}/holdings/${encodeURIComponent(ticker.toUpperCase())}` +
        `?shares=${shares}&cost_basis_per_share=${costBasisPerShare}`,
      { method: "POST" }
    ),
  getDailyBrief: () => request<DailyBrief>("/brief"),
  getTriage: (listName?: string) =>
    request<TriageResponse>(
      `/watchlist/triage${listName ? `?list_name=${encodeURIComponent(listName)}` : ""}`
    ),
  getWatchlistNews: (listName?: string, limitPerTicker = 3) => {
    const params = new URLSearchParams({ limit_per_ticker: String(limitPerTicker) });
    if (listName) params.set("list_name", listName);
    return request<WatchlistNewsResponse>(`/watchlist/news?${params.toString()}`);
  },
  getCompanyValuation: (ticker: string) =>
    request<CompanyValuation>(`/companies/${ticker}/valuation`),

  // Factor scoring
  getFactorScore: (ticker: string, weights?: FactorWeights) =>
    request<FactorScoreResponse>(
      `/companies/${ticker}/factor-score?${weightsToQuery(weights).toString()}`
    ),
  getFactorRankings: (topN = 25, weights?: FactorWeights) => {
    const params = weightsToQuery(weights);
    params.set("top_n", String(topN));
    return request<FactorRankingResponse>(`/companies/factor-rankings?${params.toString()}`);
  },

  // Universe themes
  listThemes: () => request<{ themes: UniverseThemeSummary[] }>("/universe/themes"),
  createTheme: (name: string, description?: string) =>
    request<UniverseTheme>(
      `/universe/themes/${encodeURIComponent(name)}${description ? `?description=${encodeURIComponent(description)}` : ""}`,
      { method: "POST" }
    ),
  getThemeTickers: (name: string) =>
    request<{ theme_name: string; tickers: string[] }>(
      `/universe/themes/${encodeURIComponent(name)}/tickers`
    ),
  addTickerToTheme: (name: string, ticker: string) =>
    request(`/universe/themes/${encodeURIComponent(name)}/tickers/${ticker.toUpperCase()}`, {
      method: "POST",
    }),
  removeTickerFromTheme: (name: string, ticker: string) =>
    request(`/universe/themes/${encodeURIComponent(name)}/tickers/${ticker.toUpperCase()}`, {
      method: "DELETE",
    }),
  generateThemeSynthesis: (name: string) =>
    request<ThemeSynthesisReport>(`/universe/themes/${encodeURIComponent(name)}/synthesis`, {
      method: "POST",
    }),

  // Risk parity construction
  constructRiskParity: (tickers: string[], totalInvestment: number) =>
    request<RiskParityConstructionResponse>(`/portfolios/construct-risk-parity`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tickers: tickers.map((t) => t.toUpperCase()),
        total_investment: totalInvestment,
      }),
    }),

  // ETF ingestion
  ingestEtf: (ticker: string) =>
    request<EtfIngestResult>(`/companies/${encodeURIComponent(ticker.toUpperCase())}/ingest-etf`, {
      method: "POST",
    }),

  // Earnings alerts
  getUpcomingEarnings: (listName?: string, lookaheadDays = 14) => {
    const params = new URLSearchParams({ lookahead_days: String(lookaheadDays) });
    if (listName) params.set("list_name", listName);
    return request<UpcomingEarningsResponse>(`/watchlist/earnings?${params.toString()}`);
  },
};
