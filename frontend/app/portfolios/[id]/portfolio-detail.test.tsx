// Tests for the portfolio detail page. The page previously had zero
// test coverage at all — this file focuses on the two new CRUD gaps
// closed in this pass (remove a holding, delete a portfolio), plus a
// basic smoke test that the page renders real data correctly. Same
// unverified-in-this-sandbox caveat as everything else.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import PortfolioDetailPage from "./page";
import { api, PortfolioValuation, PortfolioRiskAnalysis } from "@/lib/api";

const pushMock = vi.fn();
const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/portfolios/port-1",
  useParams: () => ({ id: "port-1" }),
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}));

const SAMPLE_VALUATION: PortfolioValuation = {
  portfolio_id: "port-1",
  name: "Growth",
  positions: [
    {
      ticker: "NVDA",
      shares: 10,
      current_price: 120,
      market_value: 1200,
      unrealized_gain: 200,
      unrealized_gain_pct: 0.2,
      weight: 1,
    },
  ],
  total_market_value: 1200,
  total_cost_basis: 1000,
  total_unrealized_gain: 200,
  total_unrealized_gain_pct: 0.2,
};

const SAMPLE_RISK: PortfolioRiskAnalysis = {
  portfolio_id: "port-1",
  as_of: "2026-08-05",
  largest_position_weight: 1,
  herfindahl_index: 1,
  sector_exposures: [],
  weighted_avg_debt_to_equity: null,
  excluded_from_leverage_calc: [],
  portfolio_daily_volatility: null,
  portfolio_annualized_volatility: null,
  parametric_var_95_1day_dollar: null,
  volatility_covered_weight: null,
  volatility_lookback_days_used: null,
  pairwise_correlations: [],
  excluded_from_volatility_calc: [],
};

function mockBaseLoads() {
  vi.spyOn(api, "getPortfolioValuation").mockResolvedValue(SAMPLE_VALUATION);
  vi.spyOn(api, "getPortfolioRisk").mockResolvedValue(SAMPLE_RISK);
  vi.spyOn(api, "getOptionPortfolioValuation").mockResolvedValue({
    total_market_value: 0,
    total_cost_basis: 0,
    total_unrealized_gain: 0,
    total_unrealized_gain_pct: 0,
    positions: [],
    positions_excluded: [],
  });
}

beforeEach(() => {
  pushMock.mockClear();
  replaceMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
});

describe("Portfolio detail page", () => {
  it("renders the portfolio name and total value from real data", async () => {
    mockBaseLoads();
    render(<PortfolioDetailPage />);
    await waitFor(() => screen.getByText("Growth"));
    // With a single holding, the portfolio total and that holding's
    // value are legitimately the same number — both should render.
    expect(screen.getAllByText("$1,200")).toHaveLength(2);
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });

  it("clicking the remove button on a holding calls api.removeHolding with the correct ticker", async () => {
    mockBaseLoads();
    const removeSpy = vi.spyOn(api, "removeHolding").mockResolvedValue(undefined as any);
    render(<PortfolioDetailPage />);

    await waitFor(() => screen.getByText("NVDA"));
    fireEvent.click(screen.getByLabelText("Remove NVDA"));

    await waitFor(() => {
      expect(removeSpy).toHaveBeenCalledWith("port-1", "NVDA");
    });
  });

  it("does not delete on a single click — requires explicit confirmation", async () => {
    mockBaseLoads();
    const deleteSpy = vi.spyOn(api, "deletePortfolio");
    render(<PortfolioDetailPage />);

    await waitFor(() => screen.getByText("Delete portfolio"));
    fireEvent.click(screen.getByText("Delete portfolio"));

    await waitFor(() => {
      expect(screen.getByText("Confirm delete")).toBeInTheDocument();
    });
    expect(deleteSpy).not.toHaveBeenCalled();
  });

  it("clicking Confirm delete calls api.deletePortfolio and navigates back to the list", async () => {
    mockBaseLoads();
    const deleteSpy = vi.spyOn(api, "deletePortfolio").mockResolvedValue(undefined as any);
    render(<PortfolioDetailPage />);

    await waitFor(() => screen.getByText("Delete portfolio"));
    fireEvent.click(screen.getByText("Delete portfolio"));
    fireEvent.click(screen.getByText("Confirm delete"));

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith("port-1");
      expect(pushMock).toHaveBeenCalledWith("/portfolios");
    });
  });

  it("clicking Cancel backs out without deleting anything", async () => {
    mockBaseLoads();
    const deleteSpy = vi.spyOn(api, "deletePortfolio");
    render(<PortfolioDetailPage />);

    await waitFor(() => screen.getByText("Delete portfolio"));
    fireEvent.click(screen.getByText("Delete portfolio"));
    fireEvent.click(screen.getByText("Cancel"));

    await waitFor(() => {
      expect(screen.getByText("Delete portfolio")).toBeInTheDocument();
    });
    expect(deleteSpy).not.toHaveBeenCalled();
  });

  it("shows the empty state when there are no option holdings", async () => {
    mockBaseLoads();
    render(<PortfolioDetailPage />);
    await waitFor(() => screen.getByText("No option holdings yet — add one below."));
  });

  it("renders a real option position and its remove button calls the API with the correct fields", async () => {
    mockBaseLoads();
    vi.spyOn(api, "getOptionPortfolioValuation").mockResolvedValue({
      total_market_value: 500,
      total_cost_basis: 400,
      total_unrealized_gain: 100,
      total_unrealized_gain_pct: 0.25,
      positions: [
        {
          contract: "NVDA 2026-09-18 CALL 500.0",
          underlying_ticker: "NVDA",
          strike: 500,
          expiration: "2026-09-18",
          option_type: "call",
          contracts_held: 1,
          current_price: 5,
          market_value: 500,
          unrealized_gain: 100,
          unrealized_gain_pct: 0.25,
        },
      ],
      positions_excluded: [],
    });
    const removeSpy = vi.spyOn(api, "removeOptionHolding").mockResolvedValue(undefined as any);
    render(<PortfolioDetailPage />);

    await waitFor(() => screen.getByText("NVDA 2026-09-18 CALL 500.0"));
    fireEvent.click(screen.getByLabelText("Remove NVDA 2026-09-18 CALL 500.0"));

    await waitFor(() => {
      expect(removeSpy).toHaveBeenCalledWith("port-1", "NVDA", 500, "2026-09-18", "call");
    });
  });

  it("submitting the add-option form calls api.addOptionHolding with the correct fields", async () => {
    mockBaseLoads();
    const addSpy = vi.spyOn(api, "addOptionHolding").mockResolvedValue(undefined as any);
    render(<PortfolioDetailPage />);

    await waitFor(() => screen.getAllByPlaceholderText("Ticker"));
    fireEvent.change(screen.getAllByPlaceholderText("Ticker")[1], { target: { value: "nvda" } });
    fireEvent.change(screen.getByPlaceholderText("Strike"), { target: { value: "500" } });
    fireEvent.change(screen.getByPlaceholderText("Expiration"), { target: { value: "2026-09-18" } });
    fireEvent.change(screen.getByPlaceholderText("Contracts"), { target: { value: "2" } });
    fireEvent.change(screen.getByPlaceholderText("Cost / contract"), { target: { value: "4.50" } });
    fireEvent.click(screen.getAllByText("Add")[1]);

    await waitFor(() => {
      expect(addSpy).toHaveBeenCalledWith("port-1", "NVDA", 500, "2026-09-18", "call", 2, 4.5);
    });
  });
});
