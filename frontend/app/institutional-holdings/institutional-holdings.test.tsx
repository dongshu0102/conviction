// Tests for the Institutional Holdings page — three real 13F
// capabilities behind one tab-switched page. Real data shapes used
// throughout, matching what production actually returned tonight.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import InstitutionalHoldingsPage from "./page";
import {
  api,
  ApiError,
  PositionChangesResponse,
  InstitutionalHoldersResponse,
  InstitutionalPortfolioResponse,
} from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/institutional-holdings",
  useRouter: () => ({ push: pushMock }),
}));

const SAMPLE_CHANGES: PositionChangesResponse = {
  filer_query: "Berkshire",
  filer_name: "Berkshire Hathaway Inc",
  prior_period: "2025-12-31",
  current_period: "2026-03-31",
  filer_had_no_prior_period_data: false,
  changes: [
    {
      cusip: "02079K107", issuer_name: "Alphabet Inc", change_type: "new",
      prior_shares: 0, current_shares: 3585215,
      prior_value_usd: 0, current_value_usd: 1028454775, pct_change: null,
    },
    {
      cusip: "166764100", issuer_name: "Chevron Corporation", change_type: "decreased",
      prior_shares: 130156362, current_shares: 84375856,
      prior_value_usd: 19837131131, current_value_usd: 17457364606, pct_change: -0.3517346774,
    },
    {
      cusip: "57636Q104", issuer_name: "Mastercard Incorporated", change_type: "closed",
      prior_shares: 3986648, current_shares: 0,
      prior_value_usd: 2275897610, current_value_usd: 0, pct_change: null,
    },
  ],
  source_note: "SEC EDGAR Form 13F, free official bulk data set.",
};

const SAMPLE_HOLDERS: InstitutionalHoldersResponse = {
  issuer_query: "Apple",
  issuer_name: "APPLE INC",
  period_of_report: "2026-03-31",
  holders: [
    { filer_name: "VANGUARD CAPITAL MANAGEMENT LLC", issuer_name: "APPLE INC", cusip: "037833100", title_of_class: "COM", value_usd: 242076924860, shares_or_principal_amount: 953847648, share_type: "SH", put_call: null, investment_discretion: "DFND" },
  ],
  source_note: "SEC EDGAR Form 13F, free official bulk data set.",
};

const SAMPLE_PORTFOLIO: InstitutionalPortfolioResponse = {
  filer_query: "Berkshire",
  filer_name: "Berkshire Hathaway Inc",
  period_of_report: "2026-03-31",
  holdings: [
    { filer_name: "Berkshire Hathaway Inc", issuer_name: "AMERICAN EXPRESS CO", cusip: "025816109", title_of_class: "COM", value_usd: 45087984892, shares_or_principal_amount: 149061045, share_type: "SH", put_call: null, investment_discretion: "SOLE" },
  ],
  source_note: "SEC EDGAR Form 13F, free official bulk data set.",
};

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
});

describe("Institutional Holdings page", () => {
  it("redirects to /login when no API key is stored", async () => {
    localStorage.clear();
    render(<InstitutionalHoldingsPage />);
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/login");
    });
  });

  it("defaults to the 'What changed' mode with a real search box", () => {
    render(<InstitutionalHoldingsPage />);
    expect(screen.getByPlaceholderText("e.g. Berkshire, FMR, Vanguard")).toBeInTheDocument();
  });

  it("searching in changes mode calls getPositionChanges and renders grouped results", async () => {
    const spy = vi.spyOn(api, "getPositionChanges").mockResolvedValue(SAMPLE_CHANGES);
    render(<InstitutionalHoldingsPage />);

    fireEvent.change(screen.getByPlaceholderText("e.g. Berkshire, FMR, Vanguard"), {
      target: { value: "Berkshire" },
    });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => expect(spy).toHaveBeenCalledWith("Berkshire"));
    await waitFor(() => screen.getByText("Alphabet Inc"));

    expect(screen.getByText("New positions (1)")).toBeInTheDocument();
    expect(screen.getByText("Trimmed (1)")).toBeInTheDocument();
    expect(screen.getByText("Fully exited (1)")).toBeInTheDocument();
  });

  it("shows the honest no-prior-period-data context, not a blend, when the flag is true", async () => {
    vi.spyOn(api, "getPositionChanges").mockResolvedValue({
      ...SAMPLE_CHANGES,
      filer_had_no_prior_period_data: true,
    });
    render(<InstitutionalHoldingsPage />);

    fireEvent.click(screen.getByText("Search"));
    await waitFor(() => screen.getByText(/not evidence of a real buying spree/));
  });

  it("does not show the no-prior-period-data note when the flag is false", async () => {
    vi.spyOn(api, "getPositionChanges").mockResolvedValue(SAMPLE_CHANGES);
    render(<InstitutionalHoldingsPage />);

    fireEvent.click(screen.getByText("Search"));
    await waitFor(() => screen.getByText("Alphabet Inc"));
    expect(screen.queryByText(/not evidence of a real buying spree/)).not.toBeInTheDocument();
  });

  it("a 'new' position renders with no percentage (pct_change is null)", async () => {
    vi.spyOn(api, "getPositionChanges").mockResolvedValue(SAMPLE_CHANGES);
    render(<InstitutionalHoldingsPage />);

    fireEvent.click(screen.getByText("Search"));
    await waitFor(() => screen.getByText("Alphabet Inc"));

    const row = screen.getByText("Alphabet Inc").closest(".ledger-row") as HTMLElement;
    expect(within(row).queryByText(/%/)).not.toBeInTheDocument();
  });

  it("a 'decreased' position renders its real percentage with the loss class", async () => {
    vi.spyOn(api, "getPositionChanges").mockResolvedValue(SAMPLE_CHANGES);
    render(<InstitutionalHoldingsPage />);

    fireEvent.click(screen.getByText("Search"));
    await waitFor(() => screen.getByText("Chevron Corporation"));

    const pct = screen.getByText("-35.2%");
    expect(pct).toHaveClass("loss");
  });

  it("switching to 'Who holds this' mode changes the placeholder and search target", async () => {
    const spy = vi.spyOn(api, "getInstitutionalHolders").mockResolvedValue(SAMPLE_HOLDERS);
    render(<InstitutionalHoldingsPage />);

    fireEvent.click(screen.getByText("Who holds this"));
    expect(screen.getByPlaceholderText("e.g. Apple, Microsoft, Nvidia")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("e.g. Apple, Microsoft, Nvidia"), {
      target: { value: "Apple" },
    });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => expect(spy).toHaveBeenCalledWith("Apple"));
    await waitFor(() => screen.getByText("VANGUARD CAPITAL MANAGEMENT LLC"));
  });

  it("switching to 'What they hold' mode calls getInstitutionalPortfolio", async () => {
    const spy = vi.spyOn(api, "getInstitutionalPortfolio").mockResolvedValue(SAMPLE_PORTFOLIO);
    render(<InstitutionalHoldingsPage />);

    fireEvent.click(screen.getByText("What they hold"));
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => expect(spy).toHaveBeenCalledWith("Berkshire"));
    await waitFor(() => screen.getByText("AMERICAN EXPRESS CO"));
  });

  it("shows a real 404 error message when no filer matches", async () => {
    vi.spyOn(api, "getPositionChanges").mockRejectedValue(
      new ApiError(404, "No filer matching 'zzz' found for the latest quarter.")
    );
    render(<InstitutionalHoldingsPage />);

    fireEvent.change(screen.getByPlaceholderText("e.g. Berkshire, FMR, Vanguard"), {
      target: { value: "zzz" },
    });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => {
      expect(screen.getByText("No filer matching 'zzz' found for the latest quarter.")).toBeInTheDocument();
    });
  });

  it("shows the empty state when there are no changes at all", async () => {
    vi.spyOn(api, "getPositionChanges").mockResolvedValue({ ...SAMPLE_CHANGES, changes: [] });
    render(<InstitutionalHoldingsPage />);

    fireEvent.click(screen.getByText("Search"));
    await waitFor(() => {
      expect(screen.getByText("No position changes detected.")).toBeInTheDocument();
    });
  });

  it("does not search when the query is blank", async () => {
    const spy = vi.spyOn(api, "getPositionChanges");
    render(<InstitutionalHoldingsPage />);

    fireEvent.change(screen.getByPlaceholderText("e.g. Berkshire, FMR, Vanguard"), {
      target: { value: "   " },
    });
    // The Search button is disabled for a blank/whitespace-only query.
    expect(screen.getByText("Search")).toBeDisabled();
    expect(spy).not.toHaveBeenCalled();
  });
});
