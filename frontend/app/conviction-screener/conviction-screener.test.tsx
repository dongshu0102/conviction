import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import ConvictionScreenerPage from "./page";
import { api, ConvictionScreenerResult } from "@/lib/api";

const pushMock = vi.fn();

// A stable object reference, not a fresh {push: pushMock} literal on
// every call -- real Next.js's own useRouter() is genuinely
// memoized/stable across renders. An unstable mock here was
// confirmed to cause a real, otherwise-invisible bug: this page's own
// useEffect depends on [router], so a fresh reference every render
// re-triggers loadResults (and its own setPage(1)) on every
// state change, silently resetting pagination back to page 1
// immediately after advancing it. Named with the required "mock"
// prefix so Vitest's own hoisting allows referencing it inside the
// hoisted vi.mock() factory below.
const mockRouter = { push: pushMock };

vi.mock("next/navigation", () => ({
  usePathname: () => "/conviction-screener",
  useRouter: () => mockRouter,
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

const SAMPLE_RESULTS: ConvictionScreenerResult[] = [
  { ticker: "NVDA", institutional_signal: true, activist_signal: false, insider_signal: true, signal_count: 2, as_of: "2026-08-16T02:00:00Z", index_memberships: ["S&P 500", "Nasdaq-100"] },
  { ticker: "AAPL", institutional_signal: true, activist_signal: false, insider_signal: false, signal_count: 1, as_of: "2026-08-16T02:00:00Z", index_memberships: ["S&P 500", "Nasdaq-100", "Dow Jones"] },
];

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
});

describe("Conviction Screener page", () => {
  it("redirects to /login when no API key is stored", async () => {
    localStorage.clear();
    render(<ConvictionScreenerPage />);
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/login");
    });
  });

  it("loads and shows the real, stored results sorted by signal count", async () => {
    vi.spyOn(api, "getConvictionScreenResults").mockResolvedValue({ results: SAMPLE_RESULTS, source_note: "test" });
    render(<ConvictionScreenerPage />);

    await waitFor(() => screen.getByText("NVDA"));
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("2/3")).toBeInTheDocument();
    expect(screen.getByText("1/3")).toBeInTheDocument();
  });

  it("shows an honest empty state when there are no stored results yet", async () => {
    vi.spyOn(api, "getConvictionScreenResults").mockResolvedValue({ results: [], source_note: "test" });
    render(<ConvictionScreenerPage />);

    await waitFor(() => screen.getByText(/No stored results yet/));
  });

  it("changing the minimum signal threshold re-fetches with that value", async () => {
    const spy = vi.spyOn(api, "getConvictionScreenResults").mockResolvedValue({ results: SAMPLE_RESULTS, source_note: "test" });
    render(<ConvictionScreenerPage />);

    await waitFor(() => expect(spy).toHaveBeenCalledWith(1));

    fireEvent.change(screen.getByDisplayValue("1+"), { target: { value: "2" } });

    await waitFor(() => expect(spy).toHaveBeenCalledWith(2));
  });

  it("clicking a ticker links to its full conviction summary", async () => {
    vi.spyOn(api, "getConvictionScreenResults").mockResolvedValue({ results: SAMPLE_RESULTS, source_note: "test" });
    render(<ConvictionScreenerPage />);

    await waitFor(() => screen.getByText("NVDA"));
    const link = screen.getByText("NVDA").closest("a");
    expect(link).toHaveAttribute("href", "/conviction-summary?ticker=NVDA");
  });

  it("run new scan triggers the screen and shows the real response message", async () => {
    vi.spyOn(api, "getConvictionScreenResults").mockResolvedValue({ results: [], source_note: "test" });
    const triggerSpy = vi.spyOn(api, "triggerConvictionScreen").mockResolvedValue({
      status: "started", message: "Conviction screen started in the background.",
    });
    render(<ConvictionScreenerPage />);

    await waitFor(() => screen.getByText("Run new scan"));
    fireEvent.click(screen.getByText("Run new scan"));

    await waitFor(() => expect(triggerSpy).toHaveBeenCalled());
    await waitFor(() => screen.getByText("Conviction screen started in the background."));
  });

  it("shows a real, honest error message when loading results fails", async () => {
    vi.spyOn(api, "getConvictionScreenResults").mockRejectedValue(new Error("db unreachable"));
    render(<ConvictionScreenerPage />);

    await waitFor(() => screen.getByText("db unreachable"));
  });

  it("shows each ticker's real index membership tags", async () => {
    vi.spyOn(api, "getConvictionScreenResults").mockResolvedValue({ results: SAMPLE_RESULTS, source_note: "test" });
    render(<ConvictionScreenerPage />);

    await waitFor(() => screen.getByText("NVDA"));
    expect(screen.getAllByText("S&P 500").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Dow Jones").length).toBeGreaterThan(0);
  });

  it("filtering by category shows only tickers genuinely in that index", async () => {
    vi.spyOn(api, "getConvictionScreenResults").mockResolvedValue({ results: SAMPLE_RESULTS, source_note: "test" });
    render(<ConvictionScreenerPage />);

    await waitFor(() => screen.getByText("NVDA"));
    fireEvent.change(screen.getByDisplayValue("All"), { target: { value: "Dow Jones" } });

    await waitFor(() => screen.getByText("AAPL")); // AAPL is in Dow Jones
    expect(screen.queryByText("NVDA")).not.toBeInTheDocument(); // NVDA is not
  });

  it("shows an honest empty state when a category has no matching results", async () => {
    const noDowJonesResults: ConvictionScreenerResult[] = [
      { ticker: "NVDA", institutional_signal: true, activist_signal: false, insider_signal: true, signal_count: 2, as_of: "2026-08-16T02:00:00Z", index_memberships: ["S&P 500", "Nasdaq-100"] },
    ];
    vi.spyOn(api, "getConvictionScreenResults").mockResolvedValue({ results: noDowJonesResults, source_note: "test" });
    render(<ConvictionScreenerPage />);

    await waitFor(() => screen.getByText("NVDA"));
    fireEvent.change(screen.getByDisplayValue("All"), { target: { value: "Dow Jones" } });

    await waitFor(() => screen.getByText(/No results in "Dow Jones"/));
    expect(screen.queryByText("NVDA")).not.toBeInTheDocument();
  });

  it("paginates when results exceed one page", async () => {
    const manyResults: ConvictionScreenerResult[] = Array.from({ length: 30 }, (_, i) => ({
      ticker: `TICK${i}`, institutional_signal: true, activist_signal: false, insider_signal: false,
      signal_count: 1, as_of: "2026-08-16T02:00:00Z", index_memberships: ["S&P 500"],
    }));
    vi.spyOn(api, "getConvictionScreenResults").mockResolvedValue({ results: manyResults, source_note: "test" });
    render(<ConvictionScreenerPage />);

    await waitFor(() => screen.getByText("TICK0"));
    expect(screen.queryByText("TICK25")).not.toBeInTheDocument(); // page 1 only shows the first 25
    expect(screen.getByText("1 / 2")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Next →"));

    await waitFor(() => screen.getByText("TICK25"));
    await waitFor(() => expect(screen.queryByText("TICK0")).not.toBeInTheDocument());
  });
});
