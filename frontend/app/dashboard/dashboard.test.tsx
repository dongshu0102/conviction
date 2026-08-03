// Tests for the redesigned Dashboard page. Same unverified-in-sandbox
// caveat as the rest. The core thing worth proving here: Dashboard no
// longer duplicates the full watchlist table or full chat panel (the
// exact overlap problem the redesign was meant to fix) — it shows
// counts and links instead.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import DashboardPage from "./page";
import { api } from "@/lib/api";

const pushMock = vi.fn();
const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}));

beforeEach(() => {
  pushMock.mockClear();
  replaceMock.mockClear();
  localStorage.clear();
  localStorage.setItem("fininsight_api_key", "fi_live_test123");
  vi.restoreAllMocks();
});

function mockLoads(portfolios: any[] = [], watchlist: any[] = []) {
  vi.spyOn(api, "listPortfolios").mockResolvedValue(portfolios);
  vi.spyOn(api, "getWatchlist").mockResolvedValue(watchlist);
}

describe("Dashboard page", () => {
  it("redirects to /login when no API key is stored", () => {
    localStorage.clear();
    mockLoads();
    render(<DashboardPage />);
    expect(replaceMock).toHaveBeenCalledWith("/login");
  });

  it("shows portfolio and watchlist counts as snapshot cards, not full tables", async () => {
    mockLoads(
      [{ portfolio_id: "a", name: "Growth", created_at: "2026-01-01", holdings: [] }],
      [
        { ticker: "AAPL", added_at: "2026-01-01" },
        { ticker: "NVDA", added_at: "2026-01-01" },
      ]
    );
    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Portfolios")).toBeInTheDocument();
    });
    // The count, not a rendered list of every holding/ticker — proves
    // this is a snapshot, not a duplicate of the full watchlist table.
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
    expect(screen.queryByText("NVDA")).not.toBeInTheDocument();
  });

  it("links the snapshot cards to their dedicated full pages", async () => {
    mockLoads();
    render(<DashboardPage />);

    await waitFor(() => screen.getByText("View all →"));
    expect(screen.getByText("View all →").closest("a")).toHaveAttribute("href", "/portfolios");
    expect(screen.getByText(/Triage, news, earnings/).closest("a")).toHaveAttribute("href", "/terminal");
    expect(screen.getByText("Open chat →").closest("a")).toHaveAttribute("href", "/chat");
  });

  it("does not render a full chat panel inline — Chat is a link, not embedded", async () => {
    mockLoads();
    render(<DashboardPage />);
    await waitFor(() => screen.getByText("Ask FinInsight"));
    // No message input on the dashboard itself — that lives at /chat now.
    expect(screen.queryByPlaceholderText(/Ask a question/)).not.toBeInTheDocument();
  });

  it("generating the daily brief calls the API and renders the narrative", async () => {
    mockLoads();
    vi.spyOn(api, "getDailyBrief").mockResolvedValue({
      narrative: "Your portfolio is up 2% today.",
      generated_at: "2026-01-01T12:00:00Z",
    });
    render(<DashboardPage />);

    await waitFor(() => screen.getByText("Get today's brief"));
    fireEvent.click(screen.getByText("Get today's brief"));

    await waitFor(() => {
      expect(screen.getByText("Your portfolio is up 2% today.")).toBeInTheDocument();
    });
  });
});
