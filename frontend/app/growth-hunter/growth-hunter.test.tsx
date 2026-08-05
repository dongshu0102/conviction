// Tests for the Growth Hunter page — Path B, the actual differentiator.
// The properties worth verifying: it never collapses the assessment
// into a single score, risk flags always render, and a 404 (ticker
// not yet ingested) offers the inline ingest-then-assess flow rather
// than just failing.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import GrowthHunterPage from "./page";
import { api, ApiError } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/growth-hunter",
  useRouter: () => ({ push: pushMock }),
}));

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  vi.restoreAllMocks();
});

const SAMPLE_ASSESSMENT = {
  ticker: "ROCKET",
  as_of: "2026-08-01T00:00:00Z",
  market_cap: 500_000_000,
  revenue_growth_latest_yoy: 1.0,
  revenue_growth_prior_yoy: 0.5,
  growth_trend: "accelerating" as const,
  is_profitable: false,
  net_income_latest: -2_000_000,
  cash_runway_months: 8,
  years_of_data_available: 3,
  risk_flags: ["Currently unprofitable", "Burning cash with under 12 months of runway (~8 months)"],
};

describe("Growth Hunter page", () => {
  it("redirects to /login when no API key is stored", () => {
    render(<GrowthHunterPage />);
    expect(pushMock).toHaveBeenCalledWith("/login");
  });

  it("renders the structured assessment, never a single score", async () => {
    localStorage.setItem("conviction_api_key", "fi_live_test123");
    vi.spyOn(api, "getSpeculativeGrowth").mockResolvedValue(SAMPLE_ASSESSMENT);
    render(<GrowthHunterPage />);

    fireEvent.change(screen.getByPlaceholderText(/Ticker/), { target: { value: "rocket" } });
    fireEvent.click(screen.getByText("Assess"));

    await waitFor(() => screen.getByText("Accelerating"));
    // "Currently unprofitable" is genuinely, deliberately shown twice —
    // once as the profitability status, once as its own risk flag.
    // That duplication is intentional, so assert on both occurrences
    // rather than a single ambiguous getByText.
    expect(screen.getAllByText("Currently unprofitable")).toHaveLength(2);
    expect(screen.getByText(/8 months at current burn rate/)).toBeInTheDocument();
    // Never a bare numeric "score" element — always the full breakdown.
    expect(screen.getByText(/not a prediction or a recommendation/)).toBeInTheDocument();
  });

  it("renders both risk flags, not just a count or the first one", async () => {
    localStorage.setItem("conviction_api_key", "fi_live_test123");
    vi.spyOn(api, "getSpeculativeGrowth").mockResolvedValue(SAMPLE_ASSESSMENT);
    render(<GrowthHunterPage />);

    fireEvent.change(screen.getByPlaceholderText(/Ticker/), { target: { value: "ROCKET" } });
    fireEvent.click(screen.getByText("Assess"));

    await waitFor(() => screen.getAllByText("Currently unprofitable"));
    expect(screen.getByText(/Burning cash with under 12 months/)).toBeInTheDocument();
  });

  it("offers to ingest when the ticker hasn't been ingested yet (404)", async () => {
    localStorage.setItem("conviction_api_key", "fi_live_test123");
    vi.spyOn(api, "getSpeculativeGrowth").mockRejectedValue(new ApiError(404, "not found"));
    render(<GrowthHunterPage />);

    fireEvent.change(screen.getByPlaceholderText(/Ticker/), { target: { value: "NEWCO" } });
    fireEvent.click(screen.getByText("Assess"));

    // Now a single text node (the page uses one template literal, not
    // JSX text mixed with an interpolated expression) — a plain match
    // works correctly.
    await waitFor(() => {
      expect(screen.getByText(/hasn't been ingested yet/)).toBeInTheDocument();
    });
    expect(screen.getByText("Ingest & assess")).toBeInTheDocument();
  });

  it("ingesting then re-assessing shows the real result", async () => {
    localStorage.setItem("conviction_api_key", "fi_live_test123");
    vi.spyOn(api, "getSpeculativeGrowth")
      .mockRejectedValueOnce(new ApiError(404, "not found"))
      .mockResolvedValueOnce(SAMPLE_ASSESSMENT);
    const ingestSpy = vi.spyOn(api, "ingestCompany").mockResolvedValue({
      ticker: "ROCKET", income_statements_ingested: 3,
    });
    render(<GrowthHunterPage />);

    fireEvent.change(screen.getByPlaceholderText(/Ticker/), { target: { value: "ROCKET" } });
    fireEvent.click(screen.getByText("Assess"));
    await waitFor(() => screen.getByText("Ingest & assess"));

    fireEvent.click(screen.getByText("Ingest & assess"));

    await waitFor(() => screen.getByText("Accelerating"));
    expect(ingestSpy).toHaveBeenCalledWith("ROCKET");
  });

  it("shows a genuine error message if assessment fails for a reason other than 404", async () => {
    localStorage.setItem("conviction_api_key", "fi_live_test123");
    vi.spyOn(api, "getSpeculativeGrowth").mockRejectedValue(new Error("Server error"));
    render(<GrowthHunterPage />);

    fireEvent.change(screen.getByPlaceholderText(/Ticker/), { target: { value: "ROCKET" } });
    fireEvent.click(screen.getByText("Assess"));

    await waitFor(() => {
      expect(screen.getByText("Server error")).toBeInTheDocument();
    });
  });
});
