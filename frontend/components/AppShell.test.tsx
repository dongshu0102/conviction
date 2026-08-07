// Tests for AppShell. Same unverified-in-this-sandbox caveat as every
// other frontend test this session — written against known-correct
// Vitest conventions, needs `npm test` to be the real first check.
//
// next/navigation's hooks (usePathname, useRouter) require a real
// Next.js app context that doesn't exist in a unit test — mocked here,
// the first test file this session to need that pattern.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { AppShell } from "./AppShell";

const pushMock = vi.fn();
let mockPathname = "/dashboard";

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ push: pushMock }),
}));

beforeEach(() => {
  pushMock.mockClear();
  mockPathname = "/dashboard";
  localStorage.clear();
});

describe("AppShell", () => {
  it("renders all six nav destinations", () => {
    render(<AppShell><div /></AppShell>);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Watchlist")).toBeInTheDocument();
    expect(screen.getByText("Universe")).toBeInTheDocument();
    expect(screen.getByText("Growth Hunter")).toBeInTheDocument();
    expect(screen.getByText("Portfolios")).toBeInTheDocument();
    expect(screen.getByText("Alerts")).toBeInTheDocument();
    expect(screen.getByText("Valuation")).toBeInTheDocument();
    expect(screen.getByText("Chat")).toBeInTheDocument();
  });

  it("renders the children content passed to it", () => {
    render(<AppShell><p>Page content here</p></AppShell>);
    expect(screen.getByText("Page content here")).toBeInTheDocument();
  });

  it("marks the current page's nav link as active by exact path match", () => {
    mockPathname = "/dashboard";
    render(<AppShell><div /></AppShell>);
    const dashboardLink = screen.getByText("Dashboard").closest("a");
    expect(dashboardLink).toHaveStyle({ color: "var(--accent)" });
  });

  it("marks a nav link active for a nested path too (e.g. /portfolios/abc123)", () => {
    mockPathname = "/portfolios/abc123";
    render(<AppShell><div /></AppShell>);
    const portfoliosLink = screen.getByText("Portfolios").closest("a");
    expect(portfoliosLink).toHaveStyle({ color: "var(--accent)" });
  });

  it("does not mark an unrelated page as active", () => {
    mockPathname = "/dashboard";
    render(<AppShell><div /></AppShell>);
    const chatLink = screen.getByText("Chat").closest("a");
    expect(chatLink).not.toHaveStyle({ color: "var(--accent)" });
  });

  it("logout clears the stored API key and redirects to /login", () => {
    localStorage.setItem("conviction_api_key", "fi_live_test123");
    render(<AppShell><div /></AppShell>);

    screen.getByText("Log out").click();

    expect(localStorage.getItem("conviction_api_key")).toBeNull();
    expect(pushMock).toHaveBeenCalledWith("/login");
  });
});
