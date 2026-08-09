// Tests for the Capital Flow page — a broad, market-wide feed, unlike
// Alerts which is per-user. No unread/read state here (there's no
// concept of a per-user "read" event on a shared platform-wide feed).

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import CapitalFlowPage from "./page";
import { api, CapitalFlowEvent } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/capital-flow",
  useRouter: () => ({ push: pushMock }),
}));

const SAMPLE_INSIDER_EVENT: CapitalFlowEvent = {
  source: "INSIDER",
  symbol: "NVDA",
  event_date: "2026-08-06",
  direction: "BUY",
  headline: "HUANG JENSEN (director, officer: CEO) bought 10,000 shares of NVDA at $180.00 ($1,800,000 total)",
  detail_url: "https://www.sec.gov/test",
  detected_at: "2026-08-07T00:33:57Z",
};

const SAMPLE_MACRO_EVENT: CapitalFlowEvent = {
  source: "MACRO",
  symbol: null,
  event_date: "2026-04-01",
  direction: "BUY",
  headline: "Foreign Direct Investment in U.S. moved +87.5% — 150,000.0 vs 80,000.0 the prior period",
  detail_url: null,
  detected_at: "2026-08-08T12:00:00Z",
};

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
});

describe("Capital Flow page", () => {
  it("redirects to /login when no API key is stored", async () => {
    localStorage.clear();
    render(<CapitalFlowPage />);
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/login");
    });
  });

  it("shows the empty state when there are no events", async () => {
    vi.spyOn(api, "getCapitalFlow").mockResolvedValue([]);
    render(<CapitalFlowPage />);
    await waitFor(() => {
      expect(screen.getByText("No unusually large capital flow events detected yet.")).toBeInTheDocument();
    });
  });

  it("renders a real insider event with its symbol, source, and headline", async () => {
    vi.spyOn(api, "getCapitalFlow").mockResolvedValue([SAMPLE_INSIDER_EVENT]);
    render(<CapitalFlowPage />);

    await waitFor(() => screen.getByText("NVDA"));
    const row = screen.getByText("NVDA").closest(".ledger-row") as HTMLElement;
    expect(within(row).getByText("Insider")).toBeInTheDocument();
    expect(within(row).getByText(SAMPLE_INSIDER_EVENT.headline)).toBeInTheDocument();
    expect(within(row).getByText("BUY")).toBeInTheDocument();
  });

  it("renders a macro event as market-wide, with no ticker", async () => {
    vi.spyOn(api, "getCapitalFlow").mockResolvedValue([SAMPLE_MACRO_EVENT]);
    render(<CapitalFlowPage />);

    await waitFor(() => screen.getByText("Market-wide"));
    const row = screen.getByText("Market-wide").closest(".ledger-row") as HTMLElement;
    expect(within(row).getByText("Macro")).toBeInTheDocument();
  });

  it("linkifies the headline when a detail_url is present", async () => {
    vi.spyOn(api, "getCapitalFlow").mockResolvedValue([SAMPLE_INSIDER_EVENT]);
    render(<CapitalFlowPage />);

    await waitFor(() => screen.getByText(SAMPLE_INSIDER_EVENT.headline));
    const link = screen.getByText(SAMPLE_INSIDER_EVENT.headline).closest("a");
    expect(link).toHaveAttribute("href", "https://www.sec.gov/test");
  });

  it("does not linkify the headline when detail_url is null", async () => {
    vi.spyOn(api, "getCapitalFlow").mockResolvedValue([SAMPLE_MACRO_EVENT]);
    render(<CapitalFlowPage />);

    await waitFor(() => screen.getByText(SAMPLE_MACRO_EVENT.headline));
    const link = screen.getByText(SAMPLE_MACRO_EVENT.headline).closest("a");
    expect(link).toBeNull();
  });

  it("changing the source filter calls the API with the correct source", async () => {
    const getSpy = vi.spyOn(api, "getCapitalFlow").mockResolvedValue([]);
    render(<CapitalFlowPage />);

    await waitFor(() => expect(getSpy).toHaveBeenCalledWith({ source: undefined }));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "SENATE" } });

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith({ source: "SENATE" });
    });
  });

  it("clicking Scan now calls the API and shows a real result message", async () => {
    vi.spyOn(api, "getCapitalFlow").mockResolvedValue([]);
    const scanSpy = vi.spyOn(api, "triggerCapitalFlowScan").mockResolvedValue({ new_event_count: 0, events: [] });
    render(<CapitalFlowPage />);

    await waitFor(() => screen.getByText("Scan now"));
    fireEvent.click(screen.getByText("Scan now"));

    await waitFor(() => {
      expect(scanSpy).toHaveBeenCalled();
      expect(
        screen.getByText("No new unusually large capital flow events detected since the last scan.")
      ).toBeInTheDocument();
    });
  });

  it("clicking Scan now with real new events shows the correct count", async () => {
    vi.spyOn(api, "getCapitalFlow").mockResolvedValue([]);
    vi.spyOn(api, "triggerCapitalFlowScan").mockResolvedValue({
      new_event_count: 2, events: [SAMPLE_INSIDER_EVENT, SAMPLE_MACRO_EVENT],
    });
    render(<CapitalFlowPage />);

    await waitFor(() => screen.getByText("Scan now"));
    fireEvent.click(screen.getByText("Scan now"));

    await waitFor(() => {
      expect(screen.getByText("2 new events detected.")).toBeInTheDocument();
    });
  });

  it("shows a real error message if loading events fails", async () => {
    vi.spyOn(api, "getCapitalFlow").mockRejectedValue(new Error("Server error"));
    render(<CapitalFlowPage />);

    await waitFor(() => {
      expect(screen.getByText("Server error")).toBeInTheDocument();
    });
  });
});
