// Thin client over the Conviction API. Auth is deliberately simple for this
// MVP: the API key lives in localStorage, attached as X-Api-Key on every
// request. There is no session/cookie layer — that's a real gap versus a
// production auth system, consistent with the backend's own "unauthenticated
// user_id was Phase 3-4's known limitation" pattern: closing it further is a
// reasonable next step, not something silently pretended away here.

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://p8xpcshdn9.us-east-1.awsapprunner.com";
const STORAGE_KEY = "conviction_api_key";

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

export interface PortfolioGreeks {
  total_delta: number;
  total_gamma: number;
  total_theta: number;
  total_vega: number;
  positions_included: number;
  positions_excluded: string[];
}

export interface HedgingSuggestion {
  underlying_ticker: string;
  net_delta: number;
  shares_to_trade: number;
  resulting_delta: number;
}

export interface HedgingPlan {
  suggestions: HedgingSuggestion[];
  positions_excluded: string[];
  note: string | null;
}

export interface RecommendationPick {
  ticker: string;
  gap_sector: string;
  current_sector_weight: number;
  price: number;
  price_to_earnings: number | null;
  return_on_equity: number | null;
  composite_score: number | null;
}

export interface Recommendations {
  gap_sectors: string[];
  scoring_note: string | null;
  picks: RecommendationPick[];
  note: string | null;
}

export interface RebalanceSuggestion {
  ticker: string;
  current_weight: number;
  target_weight: number;
  shares_to_trim: number;
  estimated_proceeds: number;
}

export interface RebalancePlan {
  target_max_weight: number;
  suggestions: RebalanceSuggestion[];
  note: string | null;
}

export interface OptionPosition {
  contract: string;
  underlying_ticker: string;
  strike: number;
  expiration: string;
  option_type: "call" | "put";
  contracts_held: number;
  current_price: number;
  market_value: number;
  unrealized_gain: number;
  unrealized_gain_pct: number;
}

export interface OptionPortfolioValuation {
  total_market_value: number;
  total_cost_basis: number;
  total_unrealized_gain: number;
  total_unrealized_gain_pct: number;
  positions: OptionPosition[];
  positions_excluded: string[];
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

export interface SpeculativeGrowthAssessment {
  ticker: string;
  as_of: string;
  market_cap: number | null;
  revenue_growth_latest_yoy: number | null;
  revenue_growth_prior_yoy: number | null;
  growth_trend: "accelerating" | "decelerating" | "insufficient_data";
  is_profitable: boolean | null;
  net_income_latest: number | null;
  cash_runway_months: number | null;
  years_of_data_available: number;
  risk_flags: string[];
}

export interface SpeculativeGrowthCandidate {
  ticker: string;
  added_at: string;
  last_growth_trend: string | null;
  last_cash_runway_months: number | null;
  last_market_cap: number | null;
  last_checked_at: string | null;
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

export interface SuggestedTicker {
  ticker: string;
  company_name: string;
  reasoning: string;
  already_ingested: boolean;
}

export interface ThemeSuggestion {
  theme_name: string;
  rationale: string;
  candidate_tickers: SuggestedTicker[];
  sourced_headlines: string[];
  generated_at: string;
  model_used: string;
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

export interface Alert {
  id: number;
  user_id: string;
  ticker: string;
  alert_type: string;
  message: string;
  change_pct: number | null;
  is_read: boolean;
  created_at: string;
}

export interface TreasuryRates {
  as_of: string;
  month1: number | null;
  month2: number | null;
  month3: number | null;
  month6: number | null;
  year1: number | null;
  year2: number | null;
  year3: number | null;
  year5: number | null;
  year7: number | null;
  year10: number | null;
  year20: number | null;
  year30: number | null;
  suggested_discount_rate: number | null;
}

export interface EconomicIndicator {
  name: string;
  as_of: string;
  value: number;
}

export interface MarketRiskPremium {
  country: string;
  country_risk_premium: number;
  total_equity_risk_premium: number;
}

export interface GeneralNewsHeadline {
  title: string;
  published_at: string | null;
  publisher: string | null;
  url: string | null;
  snippet: string | null;
}

export interface MacroSnapshot {
  as_of: string;
  gdp: EconomicIndicator | null;
  cpi: EconomicIndicator | null;
  inflation_rate: EconomicIndicator | null;
  unemployment_rate: EconomicIndicator | null;
  risk_premium: MarketRiskPremium | null;
  recent_news: GeneralNewsHeadline[];
}

export interface YieldCurveReading {
  spread_10y_2y: number | null;
  spread_10y_3m: number | null;
  is_inverted: boolean;
  interpretation: string;
}

export interface TaylorRuleResult {
  target_rate: number;
  current_rate: number | null;
  gap: number | null;
  inflation_rate: number;
  output_gap_pct: number | null;
  interpretation: string;
}

export interface RateSignals {
  as_of: string;
  yield_curve: YieldCurveReading;
  taylor_rule: TaylorRuleResult | null;
  taylor_rule_unavailable_reason: string | null;
}

export interface ValuationSnapshot {
  ticker: string;
  as_of: string;
  price: number;
  market_cap: number;
  enterprise_value: number | null;
  fundamentals_fiscal_year: number;
  price_to_earnings: number | null;
  price_to_sales: number | null;
  price_to_book: number | null;
  price_to_free_cash_flow: number | null;
  ev_to_ebitda: number | null;
}

export interface DcfProjectionYear {
  year: number;
  projected_fcf: number;
  present_value: number;
}

export interface DcfAssumptions {
  base_fcf: number;
  growth_rate: number;
  growth_rate_was_default: boolean;
  discount_rate: number;
  terminal_growth_rate: number;
  years: number;
  net_debt: number;
  shares_outstanding: number | null;
}

export interface DcfResponse {
  ticker: string;
  as_of: string;
  assumptions: DcfAssumptions;
  enterprise_value: number;
  equity_value: number;
  per_share_value: number | null;
  terminal_value: number;
  present_value_of_terminal_value: number;
  projections: DcfProjectionYear[];
}

export interface ReverseDcfResponse {
  ticker: string;
  as_of: string;
  current_price: number;
  implied_growth_rate: number | null;
  assumptions: {
    base_fcf: number;
    discount_rate: number;
    terminal_growth_rate: number;
    years: number;
    net_debt: number;
    shares_outstanding: number;
  };
}

export interface IrrResponse {
  ticker: string | null;
  as_of: string;
  irr: number | null;
  scenario: {
    entry_price: number;
    exit_price: number;
    years: number;
    annual_dividend_per_share: number;
    cash_flows: number[];
  };
}

export type CompsMetric = "pe" | "ev_ebitda" | "ps" | "pfcf";

export interface CompsResponse {
  ticker: string;
  as_of: string;
  metric: string;
  peers_considered: string[];
  peers_used: string[];
  peers_skipped: string[];
  peer_count: number;
  median_multiple: number;
  mean_multiple: number;
  implied_enterprise_value: number | null;
  implied_equity_value: number | null;
  implied_per_share_value: number | null;
}

export const api = {
  signUp: (email: string, password: string) =>
    request<{ plaintext_key: string; user_id: string }>("/auth/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  logIn: (email: string, password: string) =>
    request<{ plaintext_key: string; user_id: string }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  forgotPassword: (email: string) =>
    request<{ message: string }>("/auth/forgot-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    }),
  resetPassword: (token: string, newPassword: string) =>
    request<{ plaintext_key: string; user_id: string }>("/auth/reset-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, new_password: newPassword }),
    }),
  createApiKey: (name: string) =>
    request<{ plaintext_key: string }>(`/api-keys?name=${encodeURIComponent(name)}`, {
      method: "POST",
    }),
  getWatchlist: () => request<WatchlistItem[]>("/watchlist"),
  addToWatchlist: (ticker: string, listName?: string) =>
    request<WatchlistItem>(
      `/watchlist/${encodeURIComponent(ticker.toUpperCase())}${
        listName ? `?list_name=${encodeURIComponent(listName)}` : ""
      }`,
      { method: "POST" }
    ),
  removeFromWatchlist: (ticker: string, listName?: string) =>
    request<{ removed: boolean }>(
      `/watchlist/${encodeURIComponent(ticker.toUpperCase())}${
        listName ? `?list_name=${encodeURIComponent(listName)}` : ""
      }`,
      { method: "DELETE" }
    ),
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
  removeHolding: (portfolioId: string, ticker: string) =>
    request(`/portfolios/${portfolioId}/holdings/${encodeURIComponent(ticker.toUpperCase())}`, {
      method: "DELETE",
    }),
  deletePortfolio: (portfolioId: string) =>
    request(`/portfolios/${portfolioId}`, { method: "DELETE" }),
  addOptionHolding: (
    portfolioId: string,
    underlyingTicker: string,
    strike: number,
    expiration: string,
    optionType: "call" | "put",
    contractsHeld: number,
    costBasisPerContract: number
  ) =>
    request(`/portfolios/${portfolioId}/options`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        underlying_ticker: underlyingTicker.toUpperCase(),
        strike,
        expiration,
        option_type: optionType,
        contracts_held: contractsHeld,
        cost_basis_per_contract: costBasisPerContract,
      }),
    }),
  removeOptionHolding: (
    portfolioId: string,
    underlyingTicker: string,
    strike: number,
    expiration: string,
    optionType: "call" | "put"
  ) =>
    request(`/portfolios/${portfolioId}/options`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        underlying_ticker: underlyingTicker.toUpperCase(),
        strike,
        expiration,
        option_type: optionType,
      }),
    }),
  getOptionPortfolioValuation: (portfolioId: string) =>
    request<OptionPortfolioValuation>(`/portfolios/${portfolioId}/options/valuation`),
  getPortfolioGreeks: (portfolioId: string) =>
    request<PortfolioGreeks>(`/portfolios/${portfolioId}/options/greeks`),
  getHedgingSuggestion: (portfolioId: string) =>
    request<HedgingPlan>(`/portfolios/${portfolioId}/options/hedging-suggestion`),
  getRecommendations: (portfolioId: string, maxRecommendations = 5) =>
    request<Recommendations>(
      `/portfolios/${portfolioId}/recommendations?max_recommendations=${maxRecommendations}`
    ),
  getRebalanceSuggestion: (portfolioId: string, targetMaxWeight = 0.3) =>
    request<RebalancePlan>(
      `/portfolios/${portfolioId}/rebalance-suggestion?target_max_weight=${targetMaxWeight}`
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
  ingestCompany: (ticker: string, years = 5) =>
    request<{ ticker: string; income_statements_ingested: number }>(
      `/companies/${encodeURIComponent(ticker.toUpperCase())}/ingest?years=${years}`,
      { method: "POST" }
    ),
  getSpeculativeGrowth: (ticker: string) =>
    request<SpeculativeGrowthAssessment>(
      `/companies/${encodeURIComponent(ticker.toUpperCase())}/speculative-growth`
    ),
  listGrowthCandidates: () => request<SpeculativeGrowthCandidate[]>("/growth-candidates"),
  addGrowthCandidate: (ticker: string) =>
    request<SpeculativeGrowthCandidate>(
      `/growth-candidates/${encodeURIComponent(ticker.toUpperCase())}`,
      { method: "POST" }
    ),
  removeGrowthCandidate: (ticker: string) =>
    request(`/growth-candidates/${encodeURIComponent(ticker.toUpperCase())}`, {
      method: "DELETE",
    }),
  checkGrowthCandidates: () =>
    request<{ id: number; ticker: string; message: string; created_at: string }[]>(
      "/growth-candidates/check",
      { method: "POST" }
    ),
  getAlerts: (unreadOnly = false) =>
    request<Alert[]>(`/alerts?unread_only=${unreadOnly}`),
  markAlertRead: (alertId: number) =>
    request(`/alerts/${alertId}/read`, { method: "POST" }),
  checkAlerts: () => request<Alert[]>("/alerts/check", { method: "POST" }),
  getTreasuryRates: () => request<TreasuryRates>("/companies/treasury-rates"),
  getMacroSnapshot: (newsLimit: number = 5) =>
    request<MacroSnapshot>(`/companies/macro-snapshot?news_limit=${newsLimit}`),
  getRateSignals: (opts?: { neutral_real_rate?: number; target_inflation?: number }) => {
    const params = new URLSearchParams();
    if (opts?.neutral_real_rate !== undefined) params.set("neutral_real_rate", String(opts.neutral_real_rate));
    if (opts?.target_inflation !== undefined) params.set("target_inflation", String(opts.target_inflation));
    const qs = params.toString();
    return request<RateSignals>(`/companies/rate-signals${qs ? `?${qs}` : ""}`);
  },
  getValuation: (ticker: string) =>
    request<ValuationSnapshot>(`/companies/${encodeURIComponent(ticker.toUpperCase())}/valuation`),
  getDcf: (
    ticker: string,
    opts?: { growth_rate?: number; discount_rate?: number; terminal_growth_rate?: number; years?: number }
  ) => {
    const params = new URLSearchParams();
    if (opts?.growth_rate !== undefined) params.set("growth_rate", String(opts.growth_rate));
    params.set("discount_rate", String(opts?.discount_rate ?? 0.10));
    params.set("terminal_growth_rate", String(opts?.terminal_growth_rate ?? 0.025));
    params.set("years", String(opts?.years ?? 5));
    return request<DcfResponse>(
      `/companies/${encodeURIComponent(ticker.toUpperCase())}/dcf?${params.toString()}`
    );
  },
  getReverseDcf: (
    ticker: string,
    opts?: { discount_rate?: number; terminal_growth_rate?: number; years?: number }
  ) => {
    const params = new URLSearchParams();
    params.set("discount_rate", String(opts?.discount_rate ?? 0.10));
    params.set("terminal_growth_rate", String(opts?.terminal_growth_rate ?? 0.025));
    params.set("years", String(opts?.years ?? 5));
    return request<ReverseDcfResponse>(
      `/companies/${encodeURIComponent(ticker.toUpperCase())}/reverse-dcf?${params.toString()}`
    );
  },
  getIrr: (
    ticker: string,
    exitPrice: number,
    years: number,
    opts?: { entry_price?: number; annual_dividend_per_share?: number }
  ) => {
    const params = new URLSearchParams();
    params.set("exit_price", String(exitPrice));
    params.set("years", String(years));
    if (opts?.entry_price !== undefined) params.set("entry_price", String(opts.entry_price));
    params.set("annual_dividend_per_share", String(opts?.annual_dividend_per_share ?? 0));
    return request<IrrResponse>(
      `/companies/${encodeURIComponent(ticker.toUpperCase())}/irr?${params.toString()}`
    );
  },
  getComps: (ticker: string, metric: CompsMetric = "pe") =>
    request<CompsResponse>(
      `/companies/${encodeURIComponent(ticker.toUpperCase())}/comps?metric=${metric}`
    ),

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
  deleteTheme: (name: string) =>
    request(`/universe/themes/${encodeURIComponent(name)}`, { method: "DELETE" }),
  suggestTheme: (userHint?: string) =>
    request<ThemeSuggestion>(
      `/universe/suggest-theme${userHint ? `?user_hint=${encodeURIComponent(userHint)}` : ""}`,
      { method: "POST" }
    ),
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
