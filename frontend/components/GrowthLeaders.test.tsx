// Tests for GrowthLeaders — Path A ("common feature"). The key thing
// worth verifying: it actually calls the factor-rankings endpoint
// with growth weighted at 1.0 and everything else at 0, since that's
// the entire mechanism this component relies on (no new backend, just
// the right weights on an existing endpoint).

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { GrowthLeaders } from "./GrowthLeaders";
import { api } from "@/lib/api";

beforeEach(() => {
  vi.restoreAllMocks();
});

const SAMPLE_RESULTS = [
  {
    ticker: "NVDA", as_of: "2026-08-01", composite_score: 1.2, factors_used: 5,
    value_z: 0.1, quality_z: 0.5, growth_z: 3.8, momentum_z: 0.2, size_z: -1.0,
    raw: {
      price_to_earnings: 40, return_on_equity: 0.7, revenue_growth_yoy: 0.65,
      momentum_1m_pct: 0.02, market_cap: 4_000_000_000_000,
    },
  },
];

describe("GrowthLeaders", () => {
  it("calls getFactorRankings with growth weighted at 1 and everything else at 0", async () => {
    const spy = vi.spyOn(api, "getFactorRankings").mockResolvedValue({
      scoring_note: "test", results: SAMPLE_RESULTS,
    });
    render(<GrowthLeaders />);

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith(10, {
        weight_growth: 1, weight_value: 0, weight_quality: 0, weight_momentum: 0, weight_size: 0,
      });
    });
  });

  it("renders the ranked tickers with their revenue growth", async () => {
    vi.spyOn(api, "getFactorRankings").mockResolvedValue({
      scoring_note: "test", results: SAMPLE_RESULTS,
    });
    render(<GrowthLeaders />);

    await waitFor(() => screen.getByText("NVDA"));
    expect(screen.getByText(/65\.0% rev growth/)).toBeInTheDocument();
  });

  it("shows an error message if loading fails, without crashing", async () => {
    vi.spyOn(api, "getFactorRankings").mockRejectedValue(new Error("Rankings unavailable"));
    render(<GrowthLeaders />);

    await waitFor(() => {
      expect(screen.getByText("Rankings unavailable")).toBeInTheDocument();
    });
  });

  it("shows an empty state when there are no results", async () => {
    vi.spyOn(api, "getFactorRankings").mockResolvedValue({ scoring_note: "test", results: [] });
    render(<GrowthLeaders />);

    await waitFor(() => {
      expect(screen.getByText(/No ranked data available/)).toBeInTheDocument();
    });
  });

  it("links to Chat for speculative-growth hunting, not the same feature", async () => {
    vi.spyOn(api, "getFactorRankings").mockResolvedValue({ scoring_note: "test", results: [] });
    render(<GrowthLeaders />);

    await waitFor(() => screen.getByText(/No ranked data available/));
    const link = screen.getByText(/ask Chat about speculative growth/);
    expect(link.closest("a")).toHaveAttribute("href", "/chat");
  });
});
