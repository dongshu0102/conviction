import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import TreasuryYieldsPage from "./page";
import { api } from "@/lib/api";

const pushMock = vi.fn();
const mockRouter = { push: pushMock };

vi.mock("next/navigation", () => ({
  usePathname: () => "/treasury-yields",
  useRouter: () => mockRouter,
}));

beforeEach(() => {
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
  pushMock.mockClear();
});

const NORMAL_CURVE = {
  as_of: "2026-08-25", month1: 0.0400, month2: 0.0398, month3: 0.0395, month6: 0.0390,
  year1: 0.0385, year2: 0.0380, year3: 0.0385, year5: 0.0395, year7: 0.0405,
  year10: 0.0415, year20: 0.0435, year30: 0.0445, suggested_discount_rate: 0.0410,
};

const INVERTED_CURVE = { ...NORMAL_CURVE, year2: 0.0480, year10: 0.0410 };

describe("Treasury Yields page", () => {
  it("shows the real, loaded yield curve data by maturity", async () => {
    vi.spyOn(api, "getTreasuryRates").mockResolvedValue(NORMAL_CURVE);
    render(<TreasuryYieldsPage />);

    await waitFor(() => screen.getByText("As of 2026-08-25"));
    expect(screen.getByText("4.15%")).toBeInTheDocument(); // 10Y
    expect(screen.getByText("4.00%")).toBeInTheDocument(); // 1M
  });

  it("shows an honest error message when the real request fails", async () => {
    vi.spyOn(api, "getTreasuryRates").mockRejectedValue(new Error("FMP request failed"));
    render(<TreasuryYieldsPage />);

    await waitFor(() => screen.getByText("FMP request failed"));
  });

  it("flags a genuine 10Y/2Y inversion as a real, honest signal", async () => {
    vi.spyOn(api, "getTreasuryRates").mockResolvedValue(INVERTED_CURVE);
    render(<TreasuryYieldsPage />);

    await waitFor(() => screen.getByText(/inverted/));
  });

  it("does not flag inversion for a genuine, normal upward-sloping curve", async () => {
    vi.spyOn(api, "getTreasuryRates").mockResolvedValue(NORMAL_CURVE);
    render(<TreasuryYieldsPage />);

    await waitFor(() => screen.getByText("As of 2026-08-25"));
    expect(screen.queryByText(/inverted/)).not.toBeInTheDocument();
  });

  it("redirects to /login when there is no API key", async () => {
    localStorage.removeItem("conviction_api_key");
    render(<TreasuryYieldsPage />);

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/login"));
  });

  it("shows a real dash, not a fabricated value, for a genuinely missing maturity", async () => {
    vi.spyOn(api, "getTreasuryRates").mockResolvedValue({ ...NORMAL_CURVE, year20: null });
    render(<TreasuryYieldsPage />);

    await waitFor(() => screen.getByText("As of 2026-08-25"));
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
