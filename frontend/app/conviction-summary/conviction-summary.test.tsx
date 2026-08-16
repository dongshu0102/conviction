import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import ConvictionSummaryPage from "./page";
import { api, ConvictionSummary } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/conviction-summary",
  useRouter: () => ({ push: pushMock }),
}));

const SAMPLE_SUMMARY: ConvictionSummary = {
  ticker: "AAPL",
  institutional_holders: [
    { filer_name: "Vanguard Capital Management LLC", current_shares: 953847648, current_value_usd: 242076924860, is_increasing: true },
  ],
  institutional_signal: true,
  activist_disclosures_13d: [],
  activist_signal: false,
  insider_purchases: [],
  insider_signal: false,
  signal_count: 1,
  source_note: "test",
};

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
});

describe("Conviction Summary page", () => {
  it("redirects to /login when no API key is stored", async () => {
    localStorage.clear();
    render(<ConvictionSummaryPage />);
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/login");
    });
  });

  it("searches and shows the real signal badges", async () => {
    vi.spyOn(api, "getConvictionSummary").mockResolvedValue(SAMPLE_SUMMARY);
    render(<ConvictionSummaryPage />);

    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("AAPL — 1 of 3 signals"));
    expect(screen.getByText("● Institutional")).toBeInTheDocument();
    expect(screen.getByText("○ Activist (13D)")).toBeInTheDocument();
    expect(screen.getByText("○ Insider buying")).toBeInTheDocument();
  });

  it("shows the top holders with their increasing status", async () => {
    vi.spyOn(api, "getConvictionSummary").mockResolvedValue(SAMPLE_SUMMARY);
    render(<ConvictionSummaryPage />);

    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("Vanguard Capital Management LLC"));
    expect(screen.getByText("$242.08B ↑")).toBeInTheDocument();
  });

  it("shows a real, honest error message when the request fails", async () => {
    vi.spyOn(api, "getConvictionSummary").mockRejectedValue(new Error("no data found"));
    render(<ConvictionSummaryPage />);

    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("no data found"));
  });

  it("does not render the 13D or insider sections when both are empty", async () => {
    vi.spyOn(api, "getConvictionSummary").mockResolvedValue(SAMPLE_SUMMARY);
    render(<ConvictionSummaryPage />);

    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("AAPL — 1 of 3 signals"));
    expect(screen.queryByText("Recent 13D filings")).not.toBeInTheDocument();
    expect(screen.queryByText("Recent insider purchases")).not.toBeInTheDocument();
  });

  it("searching a different ticker calls the API with that ticker", async () => {
    const spy = vi.spyOn(api, "getConvictionSummary").mockResolvedValue(SAMPLE_SUMMARY);
    render(<ConvictionSummaryPage />);

    fireEvent.change(screen.getByPlaceholderText("Ticker, e.g. AAPL"), { target: { value: "MSFT" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => expect(spy).toHaveBeenCalledWith("MSFT"));
  });
});
