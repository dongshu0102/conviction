import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import SecResearchPage from "./page";
import {
  api, CompanyListItem, InstitutionalHolding,
  BeneficialOwnershipDisclosure, InsiderTransaction,
} from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/sec-research",
  useRouter: () => ({ push: pushMock }),
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
    amount_beneficially_owned: 1000, percent_of_class: 0.06, type_of_reporting_person: "13D",
    ...overrides,
  } as BeneficialOwnershipDisclosure;
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
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
  vi.spyOn(api, "getCompanyList").mockResolvedValue({ companies: SAMPLE_COMPANIES });
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
});
