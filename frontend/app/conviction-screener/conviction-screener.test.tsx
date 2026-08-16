import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import ConvictionScreenerPage from "./page";
import { api, ConvictionScreenerResult } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/conviction-screener",
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

const SAMPLE_RESULTS: ConvictionScreenerResult[] = [
  { ticker: "NVDA", institutional_signal: true, activist_signal: false, insider_signal: true, signal_count: 2, as_of: "2026-08-16T02:00:00Z" },
  { ticker: "AAPL", institutional_signal: true, activist_signal: false, insider_signal: false, signal_count: 1, as_of: "2026-08-16T02:00:00Z" },
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
});
