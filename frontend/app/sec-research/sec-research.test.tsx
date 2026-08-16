import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import SecResearchPage from "./page";
import {
  api, CompanyListItem, InstitutionalHolding,
  BeneficialOwnershipDisclosure, InsiderTransaction, ConvictionSummary,
} from "@/lib/api";

const pushMock = vi.fn();
const searchParamsMock = vi.fn(() => new URLSearchParams());

vi.mock("next/navigation", () => ({
  usePathname: () => "/sec-research",
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => searchParamsMock(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

const SAMPLE_COMPANIES: CompanyListItem[] = [
  { ticker: "AAPL", name: "APPLE INC" },
  { ticker: "JPM", name: "JPMORGAN CHASE & CO" },
];

function holding(overrides: Partial<InstitutionalHolding> = {}): InstitutionalHolding {
  return {
    filer_name: "Vanguard", issuer_name: "APPLE INC", cusip: "037833100", ticker: "AAPL",
    title_of_class: "COM", value_usd: 1000000, shares_or_principal_amount: 1000,
    share_type: "SH", put_call: null, investment_discretion: "SOLE", ...overrides,
  };
}

function disclosure(overrides: Partial<BeneficialOwnershipDisclosure> = {}): BeneficialOwnershipDisclosure {
  return {
    cik: "1", filing_date: "2026-06-01", accepted_date: "2026-06-01", cusip: "037833100",
    name_of_reporting_person: "Some Fund", citizenship_or_place_of_organization: "DE",
    sole_voting_power: 0, shared_voting_power: 0, sole_dispositive_power: 0, shared_dispositive_power: 0,
    amount_beneficially_owned: 1000, percent_of_class: 0.06, type_of_reporting_person: "IA",
    form_type: "13D", // the real, correct field for the 13D/13G distinction
    ...overrides,
  } as BeneficialOwnershipDisclosure;
}

function convictionSummary(overrides: Partial<ConvictionSummary> = {}): ConvictionSummary {
  return {
    ticker: "AAPL", institutional_holders: [], institutional_signal: false,
    activist_disclosures_13d: [], activist_signal: false,
    insider_purchases: [], insider_signal: false, signal_count: 0, source_note: "test",
    ...overrides,
  };
}

function transaction(overrides: Partial<InsiderTransaction> = {}): InsiderTransaction {
  return {
    filing_date: "2026-06-01", transaction_date: "2026-06-01", reporting_cik: "1", company_cik: "1",
    reporting_name: "Some Officer", type_of_owner: "officer", transaction_type: "P-Purchase",
    acquisition_or_disposition: "A", direct_or_indirect: "D", security_name: "Common Stock",
    securities_transacted: 100, securities_owned: 1000, price: 150.0, source_url: "https://example.com",
    ...overrides,
  } as InsiderTransaction;
}

beforeEach(() => {
  pushMock.mockClear();
  searchParamsMock.mockReturnValue(new URLSearchParams());
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
  vi.spyOn(api, "getCompanyList").mockResolvedValue({ companies: SAMPLE_COMPANIES });
  vi.spyOn(api, "getConvictionSummary").mockResolvedValue(convictionSummary());
});

describe("SEC Research page", () => {
  it("redirects to /login when no API key is stored", async () => {
    localStorage.clear();
    render(<SecResearchPage />);
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/login");
    });
  });

  it("fetches and shows all three sections for a known ticker", async () => {
    vi.spyOn(api, "getInstitutionalHolders").mockResolvedValue({
      issuer_query: "APPLE INC", issuer_name: "APPLE INC", period_of_report: "2026-03-31",
      holders: [holding()], source: "sec_bulk", source_note: "test",
    });
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({
      ticker: "AAPL", disclosures: [disclosure()], source_note: "test",
    });
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({
      ticker: "AAPL", transactions: [transaction()], source_note: "test",
    });

    render(<SecResearchPage />);
    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, JPM, RBLX"), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("Vanguard"));
    expect(screen.getByText("Some Fund")).toBeInTheDocument();
    expect(screen.getByText("Some Officer")).toBeInTheDocument();
  });

  it("filters out a 13D/13G disclosure whose CUSIP doesn't match the ground-truth CUSIP from 13F", async () => {
    vi.spyOn(api, "getInstitutionalHolders").mockResolvedValue({
      issuer_query: "JPMORGAN CHASE & CO", issuer_name: "JPMORGAN CHASE & CO", period_of_report: "2026-03-31",
      holders: [holding({ filer_name: "State Street", cusip: "46625H100" })], // JPM's real CUSIP
      source: "sec_bulk", source_note: "test",
    });
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({
      ticker: "JPM",
      disclosures: [
        disclosure({ name_of_reporting_person: "Real activist fund", cusip: "46625H100" }),
        disclosure({ name_of_reporting_person: "JPMorgan Chase & Co.", cusip: "092479609" }), // mismatched, misattributed
      ],
      source_note: "test",
    });
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({ ticker: "JPM", transactions: [], source_note: "test" });

    render(<SecResearchPage />);
    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, JPM, RBLX"), { target: { value: "JPM" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("Real activist fund"));
    expect(screen.queryByText("JPMorgan Chase & Co.")).not.toBeInTheDocument();
  });

  it("shows an honest error for the 13F section, while the other two sections still load", async () => {
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({
      ticker: "RBLX", disclosures: [disclosure({ name_of_reporting_person: "Some Fund" })], source_note: "test",
    });
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({
      ticker: "RBLX", transactions: [transaction({ reporting_name: "Some Officer" })], source_note: "test",
    });

    render(<SecResearchPage />);
    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    // RBLX is not in the mocked company list, so the 13F section fails honestly.
    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, JPM, RBLX"), { target: { value: "RBLX" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText(/isn't in this app's own, ingested company list yet/));
    await waitFor(() => screen.getByText("Some Fund"));
    expect(screen.getByText("Some Officer")).toBeInTheDocument();
  });

  it("shows an honest placeholder when a 13F holder's filer_name is genuinely blank in the source data", async () => {
    vi.spyOn(api, "getInstitutionalHolders").mockResolvedValue({
      issuer_query: "APPLE INC", issuer_name: "APPLE INC", period_of_report: "2026-03-31",
      holders: [holding({ filer_name: "" })], // real, confirmed live data gap, not a bug in this app's own parsing
      source: "fmp_live", source_note: "test",
    });
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({ ticker: "AAPL", disclosures: [], source_note: "test" });
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({ ticker: "AAPL", transactions: [], source_note: "test" });

    render(<SecResearchPage />);
    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, JPM, RBLX"), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("(filer name not provided by source)"));
  });

  it("shows the Conviction Summary tally at the top", async () => {
    vi.spyOn(api, "getConvictionSummary").mockResolvedValue(convictionSummary({ signal_count: 2, institutional_signal: true, activist_signal: true }));
    vi.spyOn(api, "getInstitutionalHolders").mockResolvedValue({
      issuer_query: "APPLE INC", issuer_name: "APPLE INC", period_of_report: "2026-03-31",
      holders: [holding()], source: "sec_bulk", source_note: "test",
    });
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({ ticker: "AAPL", disclosures: [], source_note: "test" });
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({ ticker: "AAPL", transactions: [], source_note: "test" });

    render(<SecResearchPage />);
    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, JPM, RBLX"), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("2 of 3 signals"));
    expect(screen.getByText("● Institutional")).toBeInTheDocument();
    expect(screen.getByText("● Activist (13D)")).toBeInTheDocument();
    expect(screen.getByText("○ Insider buying")).toBeInTheDocument();
  });

  it("labels a real 13D disclosure as activist intent, and a 13G as passive", async () => {
    vi.spyOn(api, "getInstitutionalHolders").mockResolvedValue({
      issuer_query: "APPLE INC", issuer_name: "APPLE INC", period_of_report: "2026-03-31",
      holders: [holding()], source: "sec_bulk", source_note: "test",
    });
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({
      ticker: "AAPL",
      disclosures: [
        disclosure({ name_of_reporting_person: "Activist fund", form_type: "13D" }),
        disclosure({ name_of_reporting_person: "Passive fund", form_type: "13G" }),
      ],
      source_note: "test",
    });
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({ ticker: "AAPL", transactions: [], source_note: "test" });

    render(<SecResearchPage />);
    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, JPM, RBLX"), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("Activist fund"));
    expect(screen.getByText("13D · activist intent")).toBeInTheDocument();
    expect(screen.getByText("13G · passive")).toBeInTheDocument();
  });

  it("flags a known passive index manager in the 13F holders list", async () => {
    vi.spyOn(api, "getInstitutionalHolders").mockResolvedValue({
      issuer_query: "APPLE INC", issuer_name: "APPLE INC", period_of_report: "2026-03-31",
      holders: [holding({ filer_name: "VANGUARD CAPITAL MANAGEMENT LLC" })],
      source: "sec_bulk", source_note: "test",
    });
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({ ticker: "AAPL", disclosures: [], source_note: "test" });
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({ ticker: "AAPL", transactions: [], source_note: "test" });

    render(<SecResearchPage />);
    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, JPM, RBLX"), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText(/VANGUARD CAPITAL MANAGEMENT LLC/));
    expect(screen.getByText("(often passive)")).toBeInTheDocument();
  });

  it("translates raw insider transaction codes into plain English", async () => {
    vi.spyOn(api, "getInstitutionalHolders").mockResolvedValue({
      issuer_query: "APPLE INC", issuer_name: "APPLE INC", period_of_report: "2026-03-31",
      holders: [], source: "sec_bulk", source_note: "test",
    });
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({ ticker: "AAPL", disclosures: [], source_note: "test" });
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({
      ticker: "AAPL",
      transactions: [transaction({ reporting_name: "Some Officer", transaction_type: "M-Exempt", price: 0 })],
      source_note: "test",
    });

    render(<SecResearchPage />);
    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, JPM, RBLX"), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("Option exercise / RSU vesting — routine"));
  });

  it("visually highlights a genuine P-Purchase differently from routine transactions", async () => {
    vi.spyOn(api, "getInstitutionalHolders").mockResolvedValue({
      issuer_query: "APPLE INC", issuer_name: "APPLE INC", period_of_report: "2026-03-31",
      holders: [], source: "sec_bulk", source_note: "test",
    });
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({ ticker: "AAPL", disclosures: [], source_note: "test" });
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({
      ticker: "AAPL",
      transactions: [transaction({ reporting_name: "Real Buyer", transaction_type: "P-Purchase", price: 150.0 })],
      source_note: "test",
    });

    render(<SecResearchPage />);
    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, JPM, RBLX"), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("Real Buyer"));
    expect(screen.getByText("Purchase — real, discretionary signal")).toBeInTheDocument();
    expect(screen.getByText("Real Buyer")).toHaveStyle({ fontWeight: "700" });
  });

  it("shows a real, honest error for the summary section if it fails, without breaking the rest of the page", async () => {
    vi.spyOn(api, "getConvictionSummary").mockRejectedValue(new Error("summary failed"));
    vi.spyOn(api, "getInstitutionalHolders").mockResolvedValue({
      issuer_query: "APPLE INC", issuer_name: "APPLE INC", period_of_report: "2026-03-31",
      holders: [holding()], source: "sec_bulk", source_note: "test",
    });
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({ ticker: "AAPL", disclosures: [], source_note: "test" });
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({ ticker: "AAPL", transactions: [], source_note: "test" });

    render(<SecResearchPage />);
    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, JPM, RBLX"), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("summary failed"));
    await waitFor(() => screen.getByText("Vanguard"));
  });

  it("auto-searches when a ticker is present in the URL, e.g. arriving from Conviction Summary", async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams({ ticker: "AAPL" }));
    vi.spyOn(api, "getInstitutionalHolders").mockResolvedValue({
      issuer_query: "APPLE INC", issuer_name: "APPLE INC", period_of_report: "2026-03-31",
      holders: [holding({ filer_name: "FMR LLC" })], source: "sec_bulk", source_note: "test",
    });
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({ ticker: "AAPL", disclosures: [], source_note: "test" });
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({ ticker: "AAPL", transactions: [], source_note: "test" });

    render(<SecResearchPage />);

    await waitFor(() => screen.getByText("FMR LLC"));
  });

  it("links back to the Conviction Screener once a search has been made", async () => {
    vi.spyOn(api, "getInstitutionalHolders").mockResolvedValue({
      issuer_query: "APPLE INC", issuer_name: "APPLE INC", period_of_report: "2026-03-31",
      holders: [holding()], source: "sec_bulk", source_note: "test",
    });
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({ ticker: "AAPL", disclosures: [], source_note: "test" });
    vi.spyOn(api, "getInsiderTransactions").mockResolvedValue({ ticker: "AAPL", transactions: [], source_note: "test" });

    render(<SecResearchPage />);
    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, JPM, RBLX"), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("← Back to Conviction Screener"));
    expect(screen.getByText("← Back to Conviction Screener").closest("a")).toHaveAttribute("href", "/conviction-screener");
  });
});
