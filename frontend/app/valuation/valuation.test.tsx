// Tests for the Valuation page — before this, none of these 5 real
// backend endpoints (multiples, DCF, reverse DCF, IRR, comps) were
// surfaced on the web at all.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import ValuationPage from "./page";
import { api } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/valuation",
  useRouter: () => ({ push: pushMock }),
}));

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
});

function enterTicker() {
  fireEvent.change(screen.getByPlaceholderText(/Ticker, e.g. NVDA/), { target: { value: "nvda" } });
}

describe("Valuation page", () => {
  it("redirects to /login when no API key is stored", async () => {
    localStorage.clear();
    render(<ValuationPage />);
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/login");
    });
  });

  it("shows an error and does not call the API when Compute is clicked with no ticker", () => {
    const spy = vi.spyOn(api, "getValuation");
    render(<ValuationPage />);
    fireEvent.click(screen.getAllByText("Compute")[2]);
    expect(screen.getByText("Enter a ticker first.")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("computing Multiples calls the API with the uppercased ticker and renders real data", async () => {
    const spy = vi.spyOn(api, "getValuation").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", price: 180, market_cap: 5_000_000_000_000,
      enterprise_value: 4_900_000_000_000, fundamentals_fiscal_year: 2025,
      price_to_earnings: 45.2, price_to_sales: 25.1, price_to_book: 50.3,
      price_to_free_cash_flow: 60.0, ev_to_ebitda: 35.0,
    });
    render(<ValuationPage />);
    enterTicker();
    fireEvent.click(screen.getAllByText("Compute")[2]);

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith("NVDA");
      expect(screen.getByText("45.2x")).toBeInTheDocument();
    });
  });

  it("computing DCF omits growth_rate when left blank, letting the backend default apply", async () => {
    const spy = vi.spyOn(api, "getDcf").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z",
      assumptions: {
        base_fcf: 1000, growth_rate: 0.10, growth_rate_was_default: true,
        discount_rate: 0.10, terminal_growth_rate: 0.025, years: 5,
        net_debt: 0, shares_outstanding: 100,
      },
      enterprise_value: 5000, equity_value: 5000, per_share_value: 50,
      terminal_value: 4000, present_value_of_terminal_value: 3500,
      projections: [{ year: 1, projected_fcf: 1100, present_value: 1000 }],
    });
    render(<ValuationPage />);
    enterTicker();
    fireEvent.click(screen.getAllByText("Compute")[3]);

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith("NVDA", {
        growth_rate: undefined, discount_rate: 0.10, terminal_growth_rate: 0.025, years: 5,
      });
      expect(screen.getByText(/historical CAGR, no override supplied/)).toBeInTheDocument();
    });
  });

  it("reverse DCF honestly shows 'No solution' rather than a fabricated number", async () => {
    vi.spyOn(api, "getReverseDcf").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", current_price: 999999,
      implied_growth_rate: null,
      assumptions: { base_fcf: 1000, discount_rate: 0.10, terminal_growth_rate: 0.025, years: 5, net_debt: 0, shares_outstanding: 100 },
    });
    render(<ValuationPage />);
    enterTicker();
    fireEvent.click(screen.getAllByText("Compute")[4]);

    await waitFor(() => {
      expect(screen.getByText("No solution")).toBeInTheDocument();
    });
  });

  it("IRR validates a positive exit price and years before calling the API", () => {
    const spy = vi.spyOn(api, "getIrr");
    render(<ValuationPage />);
    enterTicker();
    fireEvent.click(screen.getAllByText("Compute")[5]);

    expect(screen.getByText("Enter a positive exit price and at least 1 year.")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("computing IRR with valid inputs calls the API and renders the real result", async () => {
    const spy = vi.spyOn(api, "getIrr").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", irr: 0.10,
      scenario: { entry_price: 100, exit_price: 110, years: 1, annual_dividend_per_share: 0, cash_flows: [-100, 110] },
    });
    render(<ValuationPage />);
    enterTicker();
    fireEvent.change(screen.getByPlaceholderText("Exit price"), { target: { value: "110" } });
    fireEvent.click(screen.getAllByText("Compute")[5]);

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith("NVDA", 110, 5, { entry_price: undefined, annual_dividend_per_share: 0 });
      expect(screen.getByText("10.0%")).toBeInTheDocument();
    });
  });

  it("computing Comps defaults to the pe metric and shows which peers were used", async () => {
    const spy = vi.spyOn(api, "getComps").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", metric: "pe", peer_match_level: "industry",
      peers_considered: ["AMD", "INTC"], peers_used: ["AMD", "INTC"], peers_skipped: [],
      peer_count: 2, median_multiple: 20.0, mean_multiple: 20.0,
      implied_enterprise_value: null, implied_equity_value: 2000, implied_per_share_value: 20,
    });
    render(<ValuationPage />);
    enterTicker();
    fireEvent.click(screen.getAllByText("Compute")[6]);

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith("NVDA", "pe");
      expect(screen.getByText(/2 peers used \(AMD, INTC\)/)).toBeInTheDocument();
      expect(screen.getByText(/peer match: same industry/)).toBeInTheDocument();
    });
  });

  it("shows a warning when Comps had to fall back to sector-level peers", async () => {
    vi.spyOn(api, "getComps").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", metric: "pe", peer_match_level: "industry+sector",
      peers_considered: ["AMD"], peers_used: ["AMD"], peers_skipped: [],
      peer_count: 1, median_multiple: 20.0, mean_multiple: 20.0,
      implied_enterprise_value: null, implied_equity_value: 2000, implied_per_share_value: 20,
    });
    render(<ValuationPage />);
    enterTicker();
    fireEvent.click(screen.getAllByText("Compute")[6]);

    await waitFor(() => {
      expect(screen.getByText(/too few same-industry peers were available/)).toBeInTheDocument();
    });
  });

  it("loads Treasury rates automatically on mount, without needing a ticker", async () => {
    const spy = vi.spyOn(api, "getTreasuryRates").mockResolvedValue({
      as_of: "2026-08-06", month1: 0.038, month2: null, month3: 0.039, month6: 0.0399,
      year1: 0.0406, year2: 0.0425, year3: null, year5: 0.044, year7: null,
      year10: 0.0469, year20: null, year30: 0.0522,
      suggested_discount_rate: 0.0969,
    });
    render(<ValuationPage />);

    await waitFor(() => {
      expect(spy).toHaveBeenCalled();
      expect(screen.getByText("4.7%")).toBeInTheDocument(); // year10
    });
  });

  it("shows the suggested discount rate and a working quick-fill into the DCF form", async () => {
    vi.spyOn(api, "getTreasuryRates").mockResolvedValue({
      as_of: "2026-08-06", month1: 0.038, month2: null, month3: 0.039, month6: 0.0399,
      year1: 0.0406, year2: 0.0425, year3: null, year5: 0.044, year7: null,
      year10: 0.0469, year20: null, year30: 0.0522,
      suggested_discount_rate: 0.0969,
    });
    render(<ValuationPage />);

    await waitFor(() => screen.getByText("Use in DCF below"));
    fireEvent.click(screen.getByText("Use in DCF below"));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Discount rate")).toHaveValue(0.0969);
    });
  });

  it("shows a real error message if Treasury rates fail to load", async () => {
    vi.spyOn(api, "getTreasuryRates").mockRejectedValue(new Error("Server error"));
    render(<ValuationPage />);

    await waitFor(() => {
      expect(screen.getByText("Server error")).toBeInTheDocument();
    });
  });

  it("computing Macro Snapshot shows real GDP/inflation/unemployment/risk premium data", async () => {
    const spy = vi.spyOn(api, "getMacroSnapshot").mockResolvedValue({
      as_of: "2026-08-06T00:00:00Z",
      gdp: { name: "GDP", as_of: "2025-10-01", value: 31422.526 },
      cpi: { name: "CPI", as_of: "2025-11-01", value: 325.063 },
      inflation_rate: { name: "inflationRate", as_of: "2025-11-01", value: 2.28 },
      unemployment_rate: { name: "unemploymentRate", as_of: "2025-11-01", value: 4.1 },
      risk_premium: { country: "United States", country_risk_premium: 0.0023, total_equity_risk_premium: 0.0446 },
      recent_news: [{ title: "Fed holds rates steady", published_at: null, publisher: "Reuters", url: null, snippet: null }],
    });
    render(<ValuationPage />);
    await waitFor(() => screen.getByText("Macro Snapshot"));
    fireEvent.click(screen.getAllByText("Compute")[0]);

    await waitFor(() => {
      expect(spy).toHaveBeenCalled();
      expect(screen.getByText("$31,422.526B")).toBeInTheDocument();
      expect(screen.getByText("2.28%")).toBeInTheDocument();
      expect(screen.getByText("4.1%")).toBeInTheDocument();
      expect(screen.getByText("4.46%")).toBeInTheDocument(); // risk premium, 2-decimal to disambiguate from unemployment's 1-decimal display
      expect(screen.getByText("Fed holds rates steady")).toBeInTheDocument();
    });
  });

  it("Macro Snapshot shows an em dash, not a crash, for indicators that are genuinely unavailable", async () => {
    vi.spyOn(api, "getMacroSnapshot").mockResolvedValue({
      as_of: "2026-08-06T00:00:00Z",
      gdp: null, cpi: null, inflation_rate: null, unemployment_rate: null, risk_premium: null, recent_news: [],
    });
    render(<ValuationPage />);
    await waitFor(() => screen.getByText("Macro Snapshot"));
    fireEvent.click(screen.getAllByText("Compute")[0]);

    await waitFor(() => {
      expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    });
  });

  it("shows a real error message if the Macro Snapshot fails to load", async () => {
    vi.spyOn(api, "getMacroSnapshot").mockRejectedValue(new Error("Server error"));
    render(<ValuationPage />);
    await waitFor(() => screen.getByText("Macro Snapshot"));
    fireEvent.click(screen.getAllByText("Compute")[0]);

    await waitFor(() => {
      expect(screen.getAllByText("Server error").length).toBeGreaterThan(0);
    });
  });

  it("computing Rate Signals shows a real yield curve reading and Taylor Rule", async () => {
    const spy = vi.spyOn(api, "getRateSignals").mockResolvedValue({
      as_of: "2026-08-06T00:00:00Z",
      yield_curve: {
        spread_10y_2y: 0.44, spread_10y_3m: 0.79, is_inverted: false,
        interpretation: "The yield curve is not inverted (normal, upward-sloping).",
      },
      taylor_rule: {
        target_rate: 3.58, current_rate: 3.88, gap: 0.30, inflation_rate: 2.3,
        output_gap_pct: 1.27, interpretation: "Taylor Rule implies a target rate of 3.58%, below the current 3.88% — room to cut.",
      },
      taylor_rule_unavailable_reason: null,
    });
    render(<ValuationPage />);
    await waitFor(() => screen.getByText("Rate Signals"));
    fireEvent.click(screen.getAllByText("Compute")[1]);

    await waitFor(() => {
      expect(spy).toHaveBeenCalled();
      expect(screen.getByText("Not inverted")).toBeInTheDocument();
      expect(screen.getByText(/implied target/)).toBeInTheDocument();
    });
  });

  it("Rate Signals honestly shows why the Taylor Rule is unavailable, rather than a fabricated number", async () => {
    vi.spyOn(api, "getRateSignals").mockResolvedValue({
      as_of: "2026-08-06T00:00:00Z",
      yield_curve: { spread_10y_2y: null, spread_10y_3m: null, is_inverted: false, interpretation: "Insufficient yield data to read the curve." },
      taylor_rule: null,
      taylor_rule_unavailable_reason: "The real, current inflation rate reading is unavailable.",
    });
    render(<ValuationPage />);
    await waitFor(() => screen.getByText("Rate Signals"));
    fireEvent.click(screen.getAllByText("Compute")[1]);

    await waitFor(() => {
      expect(screen.getByText("The real, current inflation rate reading is unavailable.")).toBeInTheDocument();
    });
  });

  it("shows a real error message if Rate Signals fail to load", async () => {
    vi.spyOn(api, "getRateSignals").mockRejectedValue(new Error("Server error"));
    render(<ValuationPage />);
    await waitFor(() => screen.getByText("Rate Signals"));
    fireEvent.click(screen.getAllByText("Compute")[1]);

    await waitFor(() => {
      expect(screen.getAllByText("Server error").length).toBeGreaterThan(0);
    });
  });

  it("Run All shows an error and calls nothing when clicked with no ticker", () => {
    const spy = vi.spyOn(api, "getValuation");
    render(<ValuationPage />);
    fireEvent.click(screen.getByText("Run All"));
    expect(screen.getByText("Enter a ticker first.")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("Run All computes Multiples, DCF, Reverse DCF, and Comps, but skips IRR when no exit price is set", async () => {
    const valuationSpy = vi.spyOn(api, "getValuation").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", price: 180, market_cap: 5_000_000_000_000,
      enterprise_value: 4_900_000_000_000, fundamentals_fiscal_year: 2025,
      price_to_earnings: 45.2, price_to_sales: 25.1, price_to_book: 50.3,
      price_to_free_cash_flow: 60.0, ev_to_ebitda: 35.0,
    });
    const dcfSpy = vi.spyOn(api, "getDcf").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z",
      assumptions: { base_fcf: 1000, growth_rate: 0.10, growth_rate_was_default: true, discount_rate: 0.10, terminal_growth_rate: 0.025, years: 5, net_debt: 0, shares_outstanding: 100 },
      enterprise_value: 5000, equity_value: 5000, per_share_value: 50, terminal_value: 4000, present_value_of_terminal_value: 3500, projections: [],
    });
    const reverseDcfSpy = vi.spyOn(api, "getReverseDcf").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", current_price: 180, implied_growth_rate: 0.08,
      assumptions: { base_fcf: 1000, discount_rate: 0.10, terminal_growth_rate: 0.025, years: 5, net_debt: 0, shares_outstanding: 100 },
    });
    const compsSpy = vi.spyOn(api, "getComps").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", metric: "pe", peer_match_level: "industry",
      peers_considered: ["AMD"], peers_used: ["AMD"], peers_skipped: [],
      peer_count: 1, median_multiple: 20.0, mean_multiple: 20.0,
      implied_enterprise_value: null, implied_equity_value: 2000, implied_per_share_value: 20,
    });
    const irrSpy = vi.spyOn(api, "getIrr");

    render(<ValuationPage />);
    enterTicker();
    fireEvent.click(screen.getByText("Run All"));

    await waitFor(() => {
      expect(valuationSpy).toHaveBeenCalledWith("NVDA");
      expect(dcfSpy).toHaveBeenCalled();
      expect(reverseDcfSpy).toHaveBeenCalled();
      expect(compsSpy).toHaveBeenCalled();
    });
    expect(irrSpy).not.toHaveBeenCalled();
  });

  it("Run All includes IRR when the user has already specified an exit price", async () => {
    vi.spyOn(api, "getValuation").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", price: 180, market_cap: 5_000_000_000_000,
      enterprise_value: 4_900_000_000_000, fundamentals_fiscal_year: 2025,
      price_to_earnings: 45.2, price_to_sales: 25.1, price_to_book: 50.3,
      price_to_free_cash_flow: 60.0, ev_to_ebitda: 35.0,
    });
    vi.spyOn(api, "getDcf").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z",
      assumptions: { base_fcf: 1000, growth_rate: 0.10, growth_rate_was_default: true, discount_rate: 0.10, terminal_growth_rate: 0.025, years: 5, net_debt: 0, shares_outstanding: 100 },
      enterprise_value: 5000, equity_value: 5000, per_share_value: 50, terminal_value: 4000, present_value_of_terminal_value: 3500, projections: [],
    });
    vi.spyOn(api, "getReverseDcf").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", current_price: 180, implied_growth_rate: 0.08,
      assumptions: { base_fcf: 1000, discount_rate: 0.10, terminal_growth_rate: 0.025, years: 5, net_debt: 0, shares_outstanding: 100 },
    });
    vi.spyOn(api, "getComps").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", metric: "pe", peer_match_level: "industry",
      peers_considered: ["AMD"], peers_used: ["AMD"], peers_skipped: [],
      peer_count: 1, median_multiple: 20.0, mean_multiple: 20.0,
      implied_enterprise_value: null, implied_equity_value: 2000, implied_per_share_value: 20,
    });
    const irrSpy = vi.spyOn(api, "getIrr").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", irr: 0.10,
      scenario: { entry_price: 100, exit_price: 110, years: 1, annual_dividend_per_share: 0, cash_flows: [-100, 110] },
    });

    render(<ValuationPage />);
    enterTicker();
    fireEvent.change(screen.getByPlaceholderText("Exit price"), { target: { value: "110" } });
    fireEvent.click(screen.getByText("Run All"));

    await waitFor(() => {
      expect(irrSpy).toHaveBeenCalled();
    });
  });
});
