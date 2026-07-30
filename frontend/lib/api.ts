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
  addHolding: (portfolioId: string, ticker: string, shares: number, costBasisPerShare: number) =>
    request(
      `/portfolios/${portfolioId}/holdings/${encodeURIComponent(ticker.toUpperCase())}` +
        `?shares=${shares}&cost_basis_per_share=${costBasisPerShare}`,
      { method: "POST" }
    ),
  getDailyBrief: () => request<DailyBrief>("/brief"),
  getCompanyValuation: (ticker: string) =>
    request<CompanyValuation>(`/companies/${ticker}/valuation`),
};
