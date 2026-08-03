// Tests for the Portfolios index page. Same unverified-in-this-sandbox
// caveat as everything else. Mocks the `api` object's methods directly
// (rather than mocking fetch, already covered by lib/api.test.ts) since
// this file is testing the PAGE's logic — loading, empty state,
// creating, navigating — not api.ts's own HTTP mechanics again.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import PortfoliosIndexPage from "./page";
import { api } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/portfolios",
  useRouter: () => ({ push: pushMock }),
}));

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("fininsight_api_key", "fi_live_test123");
  vi.restoreAllMocks();
});

describe("Portfolios index page", () => {
  it("redirects to /login when no API key is stored", () => {
    localStorage.clear();
    vi.spyOn(api, "listPortfolios").mockResolvedValue([]);
    render(<PortfoliosIndexPage />);
    expect(pushMock).toHaveBeenCalledWith("/login");
  });

  it("shows the empty state when there are no portfolios", async () => {
    vi.spyOn(api, "listPortfolios").mockResolvedValue([]);
    render(<PortfoliosIndexPage />);
    await waitFor(() => {
      expect(screen.getByText(/No portfolios yet/)).toBeInTheDocument();
    });
  });

  it("lists existing portfolios with holding counts", async () => {
    vi.spyOn(api, "listPortfolios").mockResolvedValue([
      { portfolio_id: "abc", name: "Growth", created_at: "2026-01-01", holdings: [
        { ticker: "AAPL", shares: 10, cost_basis_per_share: 150 },
        { ticker: "NVDA", shares: 5, cost_basis_per_share: 400 },
      ]},
      { portfolio_id: "def", name: "Income", created_at: "2026-01-01", holdings: [] },
    ]);
    render(<PortfoliosIndexPage />);

    await waitFor(() => {
      expect(screen.getByText("Growth")).toBeInTheDocument();
    });
    expect(screen.getByText("2 holdings")).toBeInTheDocument();
    expect(screen.getByText("Income")).toBeInTheDocument();
    expect(screen.getByText("0 holdings")).toBeInTheDocument();
  });

  it("creating a portfolio navigates to its detail page", async () => {
    vi.spyOn(api, "listPortfolios").mockResolvedValue([]);
    vi.spyOn(api, "createPortfolio").mockResolvedValue({
      portfolio_id: "new-id-123", name: "Retirement", created_at: "2026-01-01", holdings: [],
    });
    render(<PortfoliosIndexPage />);

    await waitFor(() => screen.getByPlaceholderText(/Portfolio name/));
    fireEvent.change(screen.getByPlaceholderText(/Portfolio name/), {
      target: { value: "Retirement" },
    });
    fireEvent.click(screen.getByText("Create"));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/portfolios/new-id-123");
    });
  });

  it("shows an error message if loading portfolios fails", async () => {
    vi.spyOn(api, "listPortfolios").mockRejectedValue(new Error("Network down"));
    render(<PortfoliosIndexPage />);
    await waitFor(() => {
      expect(screen.getByText("Network down")).toBeInTheDocument();
    });
  });
});
