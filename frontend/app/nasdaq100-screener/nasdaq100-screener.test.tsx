import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import Nasdaq100ScreenerPage from "./page";
import { api } from "@/lib/api";

const pushMock = vi.fn();
// A stable object reference, not a fresh {push: pushMock} literal on
// every call -- the same, confirmed root cause found twice already
// tonight (Conviction Screener, Universe): this page's own useEffect
// depends on [loadAll, router], so an unstable mock reference would
// re-trigger loadAll() on every client-side state change.
const mockRouter = { push: pushMock };

vi.mock("next/navigation", () => ({
  usePathname: () => "/nasdaq100-screener",
  useRouter: () => mockRouter,
}));

beforeEach(() => {
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
  pushMock.mockClear();
});

const SAMPLE_RESULTS = [
  {
    ticker: "NVDA", as_of: "2026-08-25T00:00:00Z", industry: "Semiconductors",
    market_structure_category: "Oligopoly", hhi: 4150.0,
    value_chain_position: "Midstream — Design/Development", business_model: "Hardware/Product Sales",
    market_cap_tier: "Mega-Cap", maturity_stage: "Hyper-Growth",
    market_cap: 3_000_000_000_000.0, revenue_growth: 0.35,
  },
  {
    ticker: "AAPL", as_of: "2026-08-25T00:00:00Z", industry: "Consumer Electronics",
    market_structure_category: "Monopolistic Competition", hhi: 1800.0,
    value_chain_position: "Downstream — End-Product/Retail", business_model: "Hardware/Product Sales",
    market_cap_tier: "Mega-Cap", maturity_stage: "Mature",
    market_cap: 3_400_000_000_000.0, revenue_growth: 0.05,
  },
];

describe("Nasdaq-100 Screener page", () => {
  it("shows the real, loaded results on mount", async () => {
    vi.spyOn(api, "getNasdaq100ScreenerResults").mockResolvedValue({ results: SAMPLE_RESULTS });
    render(<Nasdaq100ScreenerPage />);

    await waitFor(() => screen.getByText("NVDA"));
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getAllByText("Oligopoly")).toHaveLength(2); // one dropdown option, one table cell
  });

  it("shows an honest empty state when there is no classification data yet", async () => {
    vi.spyOn(api, "getNasdaq100ScreenerResults").mockResolvedValue({ results: [] });
    render(<Nasdaq100ScreenerPage />);

    await waitFor(() => screen.getByText(/No classification data yet/));
  });

  it("filter dropdown options are derived from the real, loaded data", async () => {
    vi.spyOn(api, "getNasdaq100ScreenerResults").mockResolvedValue({ results: SAMPLE_RESULTS });
    render(<Nasdaq100ScreenerPage />);

    await waitFor(() => screen.getByText("NVDA"));
    // Checked specifically within the industry <select>, not the whole
    // page -- both real industries also, legitimately, appear again in
    // the results table below, so a page-wide text query would be
    // genuinely ambiguous.
    const industrySelect = screen.getAllByRole("combobox")[0];
    const optionLabels = Array.from(industrySelect.querySelectorAll("option")).map((o) => o.textContent);
    expect(optionLabels).toContain("Semiconductors");
    expect(optionLabels).toContain("Consumer Electronics");
  });

  it("changing a filter re-fetches with the real, selected filter applied", async () => {
    const spy = vi.spyOn(api, "getNasdaq100ScreenerResults")
      .mockResolvedValueOnce({ results: SAMPLE_RESULTS })
      .mockResolvedValueOnce({ results: [SAMPLE_RESULTS[0]] });
    render(<Nasdaq100ScreenerPage />);
    await waitFor(() => screen.getByText("NVDA"));

    const selects = screen.getAllByRole("combobox");
    const industrySelect = selects[0];
    fireEvent.change(industrySelect, { target: { value: "Semiconductors" } });

    await waitFor(() => expect(spy).toHaveBeenCalledWith({ industry: "Semiconductors" }));
    await waitFor(() => {
      expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
    });
  });

  it("Clear all resets filters and re-fetches the real, unfiltered results", async () => {
    vi.spyOn(api, "getNasdaq100ScreenerResults")
      .mockResolvedValueOnce({ results: SAMPLE_RESULTS })
      .mockResolvedValueOnce({ results: [SAMPLE_RESULTS[0]] })
      .mockResolvedValueOnce({ results: SAMPLE_RESULTS });
    render(<Nasdaq100ScreenerPage />);
    await waitFor(() => screen.getByText("NVDA"));

    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "Semiconductors" } });
    await waitFor(() => screen.getByText("Clear all (1)"));

    fireEvent.click(screen.getByText("Clear all (1)"));

    await waitFor(() => screen.getByText("AAPL"));
    expect(screen.queryByText(/Clear all/)).not.toBeInTheDocument();
  });

  it("Run classification batch shows the real, honest response message", async () => {
    vi.spyOn(api, "getNasdaq100ScreenerResults").mockResolvedValue({ results: SAMPLE_RESULTS });
    vi.spyOn(api, "runNasdaq100Batch").mockResolvedValue({
      status: "started", message: "Nasdaq-100 classification batch started in the background.",
    });
    render(<Nasdaq100ScreenerPage />);
    await waitFor(() => screen.getByText("NVDA"));

    fireEvent.click(screen.getByText("Run classification batch"));

    await waitFor(() => screen.getByText(/started in the background/));
  });

  it("redirects to /login when there is no API key", async () => {
    localStorage.removeItem("conviction_api_key");
    render(<Nasdaq100ScreenerPage />);

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/login"));
  });
});
