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
    fireEvent.click(screen.getAllByText("Compute")[0]);
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
    fireEvent.click(screen.getAllByText("Compute")[0]);

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
    fireEvent.click(screen.getAllByText("Compute")[1]);

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
    fireEvent.click(screen.getAllByText("Compute")[2]);

    await waitFor(() => {
      expect(screen.getByText("No solution")).toBeInTheDocument();
    });
  });

  it("IRR validates a positive exit price and years before calling the API", () => {
    const spy = vi.spyOn(api, "getIrr");
    render(<ValuationPage />);
    enterTicker();
    fireEvent.click(screen.getAllByText("Compute")[3]);

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
    fireEvent.click(screen.getAllByText("Compute")[3]);

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith("NVDA", 110, 5, { entry_price: undefined, annual_dividend_per_share: 0 });
      expect(screen.getByText("10.0%")).toBeInTheDocument();
    });
  });

  it("computing Comps defaults to the pe metric and shows which peers were used", async () => {
    const spy = vi.spyOn(api, "getComps").mockResolvedValue({
      ticker: "NVDA", as_of: "2026-08-06T00:00:00Z", metric: "pe",
      peers_considered: ["AMD", "INTC"], peers_used: ["AMD", "INTC"], peers_skipped: [],
      peer_count: 2, median_multiple: 20.0, mean_multiple: 20.0,
      implied_enterprise_value: null, implied_equity_value: 2000, implied_per_share_value: 20,
    });
    render(<ValuationPage />);
    enterTicker();
    fireEvent.click(screen.getAllByText("Compute")[4]);

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith("NVDA", "pe");
      expect(screen.getByText(/2 peers used \(AMD, INTC\)/)).toBeInTheDocument();
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
});
