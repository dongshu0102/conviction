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
  is_late_filing: null,
};

const SAMPLE_MACRO_EVENT: CapitalFlowEvent = {
  source: "MACRO",
  symbol: null,
  event_date: "2026-04-01",
  direction: "BUY",
  headline: "Foreign Direct Investment in U.S. moved +87.5% — 150,000.0 vs 80,000.0 the prior period",
  detail_url: null,
  detected_at: "2026-08-08T12:00:00Z",
  is_late_filing: null,
};

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
  vi.spyOn(api, "getNext13FDeadline").mockResolvedValue({
    next_deadline: null, days_until: null, source_note: "",
  });
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

  it("groups events under a real date heading, most recent date first", async () => {
    const older = { ...SAMPLE_MACRO_EVENT, event_date: "2026-08-01", symbol: "OLDER" };
    const newer = { ...SAMPLE_INSIDER_EVENT, event_date: "2026-08-06" };
    vi.spyOn(api, "getCapitalFlow").mockResolvedValue([newer, older]);
    render(<CapitalFlowPage />);

    await waitFor(() => screen.getByText("NVDA"));
    const headings = screen.getAllByText(/2026/);
    // The Aug 6 heading (newer) must appear before the Aug 1 heading (older) in document order.
    const aug6Index = headings.findIndex((h) => h.textContent?.includes("August 6"));
    const aug1Index = headings.findIndex((h) => h.textContent?.includes("August 1"));
    expect(aug6Index).toBeGreaterThanOrEqual(0);
    expect(aug1Index).toBeGreaterThan(aug6Index);
  });

  it("shows a LATE FILING badge for a real late Senate disclosure", async () => {
    const lateEvent = { ...SAMPLE_INSIDER_EVENT, is_late_filing: true };
    vi.spyOn(api, "getCapitalFlow").mockResolvedValue([lateEvent]);
    render(<CapitalFlowPage />);

    await waitFor(() => screen.getByText("NVDA"));
    expect(screen.getByText("LATE FILING")).toBeInTheDocument();
  });

  it("does not show a LATE FILING badge when is_late_filing is null", async () => {
    vi.spyOn(api, "getCapitalFlow").mockResolvedValue([SAMPLE_INSIDER_EVENT]);
    render(<CapitalFlowPage />);

    await waitFor(() => screen.getByText("NVDA"));
    expect(screen.queryByText("LATE FILING")).not.toBeInTheDocument();
  });

  it("shows the next real 13F deadline when available", async () => {
    vi.spyOn(api, "getCapitalFlow").mockResolvedValue([]);
    vi.spyOn(api, "getNext13FDeadline").mockResolvedValue({
      next_deadline: "2026-08-14", days_until: 6, source_note: "From the SEC's own published FAQ table.",
    });
    render(<CapitalFlowPage />);

    await waitFor(() => {
      expect(screen.getByText("2026-08-14")).toBeInTheDocument();
      expect(screen.getByText(/6 days away/)).toBeInTheDocument();
    });
  });

  it("does not show a 13F deadline banner when none is available", async () => {
    vi.spyOn(api, "getCapitalFlow").mockResolvedValue([]);
    render(<CapitalFlowPage />);

    await waitFor(() => screen.getByText("No unusually large capital flow events detected yet."));
    expect(screen.queryByText(/Next Form 13F filing deadline/)).not.toBeInTheDocument();
  });
});
