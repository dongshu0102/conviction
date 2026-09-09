import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import MarketWorkflowPage from "./page";
import { api } from "@/lib/api";

const pushMock = vi.fn();
// A stable object reference, not a fresh {push: pushMock} literal on
// every call -- the same, confirmed root cause found repeatedly
// tonight: this page's own handlers depend on router, so an unstable
// mock reference would re-trigger effects on every step change.
const mockRouter = { push: pushMock };

vi.mock("next/navigation", () => ({
  usePathname: () => "/market-workflow",
  useRouter: () => mockRouter,
}));

beforeEach(() => {
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
  pushMock.mockClear();
  // A default, real-shaped mock so every existing test's own mount
  // doesn't hit an unmocked fetch call from this page's own
  // getEconomicCycle effect -- tests that specifically care about the
  // real cycle banner override this individually.
  vi.spyOn(api, "getEconomicCycle").mockResolvedValue({
    state: "Expansion", yield_curve_inverted: false, sahm_rule_triggered: false,
    reasoning: ["Neither the Sahm Rule nor yield curve inversion is currently present."],
  });
  // Same reasoning as the getEconomicCycle default above -- any
  // existing test that clicks "Rank →" now also triggers this real
  // call via handleSelectForRanking's own Promise.allSettled.
  vi.spyOn(api, "getDemandSignals").mockResolvedValue({
    ticker: "AAPL", latest_revenue_growth_yoy: 0.064, prior_revenue_growth_yoy: 0.020,
    revenue_growth_accelerating: true, recent_upgrades: 1, recent_downgrades: 2,
    analyst_consensus_direction: "More bearish", last_quarter_avg_price_target: 327.18,
    economic_cycle_state: "Expansion",
  });
});

const SAMPLE_CANDIDATES = [
  {
    ticker: "AAPL", company_name: "Apple Inc.", market_cap: 4_699_513_299_320.0,
    price: 319.97, beta: 1.085, last_annual_dividend: 1.06, volume: 39_606_884,
    sector: "Technology", industry: "Consumer Electronics", exchange: "NASDAQ", country: "US",
  },
];

const SAMPLE_RATINGS = {
  ticker: "AAPL",
  recent_grades: [
    { grading_company: "DA Davidson", date: "2026-09-02", previous_grade: "Neutral", new_grade: "Neutral", action: "maintain" },
  ],
  last_month_avg_price_target: 331.83, last_month_count: 2,
  last_quarter_avg_price_target: 331.69, last_quarter_count: 17,
  last_year_avg_price_target: 309.56, last_year_count: 69,
};

const SAMPLE_CANDLES = [
  { ticker: "AAPL", timestamp: "2026-09-01T04:00:00Z", open: 310, high: 315, low: 308, close: 312, volume: 1000000 },
];

describe("Market Workflow page", () => {
  it("Step 1: screening renders real candidates with a Rank action", async () => {
    vi.spyOn(api, "screenMarket").mockResolvedValue({ candidates: SAMPLE_CANDIDATES });
    render(<MarketWorkflowPage />);

    fireEvent.click(screen.getByText("Screen"));

    await waitFor(() => screen.getByText("AAPL"));
    expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
    expect(screen.getByText("Rank →")).toBeInTheDocument();
  });

  it("Step 1: shows an honest error message when screening fails", async () => {
    vi.spyOn(api, "screenMarket").mockRejectedValue(new Error("FMP request failed"));
    render(<MarketWorkflowPage />);

    fireEvent.click(screen.getByText("Screen"));

    await waitFor(() => screen.getByText("FMP request failed"));
  });

  it("clicking Rank moves to Step 2 and shows real analyst ratings", async () => {
    vi.spyOn(api, "screenMarket").mockResolvedValue({ candidates: SAMPLE_CANDIDATES });
    vi.spyOn(api, "getAnalystRatings").mockResolvedValue(SAMPLE_RATINGS);
    render(<MarketWorkflowPage />);

    fireEvent.click(screen.getByText("Screen"));
    await waitFor(() => screen.getByText("Rank →"));
    fireEvent.click(screen.getByText("Rank →"));

    await waitFor(() => screen.getByText("DA Davidson"));
    expect(screen.getByText(/17 analysts/)).toBeInTheDocument();
  });

  it("honestly shows no coverage message when analyst ratings are genuinely null", async () => {
    vi.spyOn(api, "screenMarket").mockResolvedValue({ candidates: SAMPLE_CANDIDATES });
    vi.spyOn(api, "getAnalystRatings").mockResolvedValue(null);
    render(<MarketWorkflowPage />);

    fireEvent.click(screen.getByText("Screen"));
    await waitFor(() => screen.getByText("Rank →"));
    fireEvent.click(screen.getByText("Rank →"));

    await waitFor(() => screen.getByText(/No real analyst coverage found/));
  });

  it("clicking Validate moves to Step 3 and loads real price candles", async () => {
    vi.spyOn(api, "screenMarket").mockResolvedValue({ candidates: SAMPLE_CANDIDATES });
    vi.spyOn(api, "getAnalystRatings").mockResolvedValue(SAMPLE_RATINGS);
    vi.spyOn(api, "getStockCandles").mockResolvedValue(SAMPLE_CANDLES);
    render(<MarketWorkflowPage />);

    fireEvent.click(screen.getByText("Screen"));
    await waitFor(() => screen.getByText("Rank →"));
    fireEvent.click(screen.getByText("Rank →"));
    await waitFor(() => screen.getByText("Validate price trend →"));
    fireEvent.click(screen.getByText("Validate price trend →"));

    await waitFor(() => expect(api.getStockCandles).toHaveBeenCalledWith(
      "AAPL", expect.any(String), expect.any(String)
    ));
  });

  it("clicking Add to watchlist calls the real API and moves to Step 4", async () => {
    vi.spyOn(api, "screenMarket").mockResolvedValue({ candidates: SAMPLE_CANDIDATES });
    vi.spyOn(api, "getAnalystRatings").mockResolvedValue(SAMPLE_RATINGS);
    vi.spyOn(api, "getStockCandles").mockResolvedValue(SAMPLE_CANDLES);
    const addSpy = vi.spyOn(api, "addToWatchlist").mockResolvedValue({} as any);
    render(<MarketWorkflowPage />);

    fireEvent.click(screen.getByText("Screen"));
    await waitFor(() => screen.getByText("Rank →"));
    fireEvent.click(screen.getByText("Rank →"));
    await waitFor(() => screen.getByText("Validate price trend →"));
    fireEvent.click(screen.getByText("Validate price trend →"));
    await waitFor(() => screen.getByText("Add to watchlist →"));
    fireEvent.click(screen.getByText("Add to watchlist →"));

    await waitFor(() => expect(addSpy).toHaveBeenCalledWith("AAPL"));
    await waitFor(() => screen.getByText(/added to your watchlist/));
  });

  it("redirects to /login when there is no API key", async () => {
    localStorage.removeItem("conviction_api_key");
    render(<MarketWorkflowPage />);

    fireEvent.click(screen.getByText("Screen"));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/login"));
  });

  it("shows the real economic cycle state and reasoning on mount", async () => {
    vi.spyOn(api, "getEconomicCycle").mockResolvedValue({
      state: "Late-cycle warning", yield_curve_inverted: true, sahm_rule_triggered: false,
      reasoning: ["The yield curve is genuinely inverted — a real, leading warning sign, though not itself a confirmed recession signal."],
    });
    render(<MarketWorkflowPage />);

    await waitFor(() => screen.getByText("Late-cycle warning"));
    expect(screen.getByText(/leading warning sign/)).toBeInTheDocument();
  });

  it("shows an honest error message when the real cycle request fails, without breaking the rest of the page", async () => {
    vi.spyOn(api, "getEconomicCycle").mockRejectedValue(new Error("Rate signals unavailable"));
    vi.spyOn(api, "screenMarket").mockResolvedValue({ candidates: SAMPLE_CANDIDATES });
    render(<MarketWorkflowPage />);

    await waitFor(() => screen.getByText("Rate signals unavailable"));
    // The rest of the page must still work correctly.
    fireEvent.click(screen.getByText("Screen"));
    await waitFor(() => screen.getByText("AAPL"));
  });

  it("shows real demand signals after selecting a candidate for ranking", async () => {
    vi.spyOn(api, "screenMarket").mockResolvedValue({ candidates: SAMPLE_CANDIDATES });
    vi.spyOn(api, "getAnalystRatings").mockResolvedValue(SAMPLE_RATINGS);
    render(<MarketWorkflowPage />);

    fireEvent.click(screen.getByText("Screen"));
    await waitFor(() => screen.getByText("Rank →"));
    fireEvent.click(screen.getByText("Rank →"));

    await waitFor(() => screen.getByText(/6\.4%/));
    expect(screen.getAllByText(/accelerating/).length).toBeGreaterThan(0);
    expect(screen.getByText(/1 upgrades, 2 downgrades/)).toBeInTheDocument();
    expect(screen.getByText("More bearish")).toBeInTheDocument();
  });

  it("shows an honest error message when the real demand signals request fails", async () => {
    vi.spyOn(api, "screenMarket").mockResolvedValue({ candidates: SAMPLE_CANDIDATES });
    vi.spyOn(api, "getAnalystRatings").mockResolvedValue(SAMPLE_RATINGS);
    vi.spyOn(api, "getDemandSignals").mockRejectedValue(new Error("Company not found"));
    render(<MarketWorkflowPage />);

    fireEvent.click(screen.getByText("Screen"));
    await waitFor(() => screen.getByText("Rank →"));
    fireEvent.click(screen.getByText("Rank →"));

    await waitFor(() => screen.getByText("Company not found"));
  });
});
