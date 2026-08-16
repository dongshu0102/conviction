// Tests for the Form 3/4/5 Insider Transactions page. Real data
// shapes used throughout, matching what production actually returned
// tonight (Jennifer Newstead's real Apple S-Sale, and a real,
// paired M-Exempt price=0 event).

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import InsiderTransactionsPage from "./page";
import { api, ApiError, InsiderTransactionsResponse } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/insider-transactions",
  useRouter: () => ({ push: pushMock }),
}));

const SAMPLE_TRANSACTIONS: InsiderTransactionsResponse = {
  ticker: "AAPL",
  transactions: [
    {
      filing_date: "2026-08-13", transaction_date: "2026-08-11",
      reporting_cik: "0001780525", company_cik: "0000320193",
      reporting_name: "Newstead Jennifer", type_of_owner: "officer: SVP, GC and Secretary",
      transaction_type: "S-Sale", acquisition_or_disposition: "D", direct_or_indirect: "D",
      security_name: "Common Stock", securities_transacted: 1439, securities_owned: 40107,
      price: 307.75, source_url: "https://www.sec.gov/Archives/edgar/data/320193/000114036126032884/0001140361-26-032884-index.htm",
    },
  ],
  source_note: "Form 3/4/5 insider transactions, live from FMP.",
};

const SAMPLE_ZERO_PRICE_TRANSACTIONS: InsiderTransactionsResponse = {
  ticker: "AAPL",
  transactions: [
    {
      filing_date: "2026-06-17", transaction_date: "2026-06-15",
      reporting_cik: "0001780525", company_cik: "0000320193",
      reporting_name: "Newstead Jennifer", type_of_owner: "officer: SVP, GC and Secretary",
      transaction_type: "M-Exempt", acquisition_or_disposition: "D", direct_or_indirect: "D",
      security_name: "Restricted Stock Unit", securities_transacted: 30104, securities_owned: 210728,
      price: 0, source_url: "https://www.sec.gov/Archives/edgar/data/320193/000114036126025622/0001140361-26-025622-index.htm",
    },
  ],
  source_note: "Form 3/4/5 insider transactions, live from FMP.",
};

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
  vi.spyOn(api, "getCompanyList").mockResolvedValue({ companies: [] });
});

describe("Insider Transactions page", () => {
  it("redirects to /login when no API key is stored", async () => {
    localStorage.clear();
    render(<InsiderTransactionsPage />);
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/login");
    });
  });

  it("shows a real search box defaulting to AAPL", async () => {
    render(<InsiderTransactionsPage />);
    expect(screen.getByPlaceholderText("e.g. AAPL, TSLA, MSFT")).toHaveValue("AAPL");
    // TickerAutocomplete fetches the company list on mount -- await it
    // here so that resolution doesn't happen after this test has
    // already finished, which is what caused a real
    // not-wrapped-in-act() warning.
    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
  });

  it("searching calls getInsiderTransactions with the entered ticker", async () => {
    const spy = vi.spyOn(api, "getInsiderTransactions").mockResolvedValue(SAMPLE_TRANSACTIONS);
    render(<InsiderTransactionsPage />);

    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => expect(spy).toHaveBeenCalledWith("AAPL"));
  });

  it("displays a real transaction with its reporting person and real price", async () => {
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue(SAMPLE_TRANSACTIONS);
    render(<InsiderTransactionsPage />);

    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("Newstead Jennifer"));
    expect(screen.getByText("$307.75")).toBeInTheDocument();
    expect(screen.getByText("S-Sale")).toBeInTheDocument();
  });

  it("shows a dash, not a fabricated price, for a genuine price=0 transaction", async () => {
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue(SAMPLE_ZERO_PRICE_TRANSACTIONS);
    render(<InsiderTransactionsPage />);

    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("M-Exempt"));
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
  });

  it("shows a real, honest empty state when no transactions are found", async () => {
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({
      ticker: "ZZZZ", transactions: [], source_note: "Form 3/4/5 insider transactions, live from FMP.",
    });
    render(<InsiderTransactionsPage />);

    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, TSLA, MSFT"), {
      target: { value: "ZZZZ" },
    });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("No insider transactions found."));
  });

  it("shows the real error message for a 404 response rather than a generic one", async () => {
    vi.spyOn(api, "getInsiderTransactions").mockRejectedValue(
      new ApiError(404, "No such ticker")
    );
    render(<InsiderTransactionsPage />);

    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("No such ticker"));
  });
});
