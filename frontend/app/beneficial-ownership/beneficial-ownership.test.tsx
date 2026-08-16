// Tests for the Schedule 13D/13G Beneficial Ownership page. Real data
// shapes used throughout, matching what production actually returned
// tonight (Vanguard Capital Management's real, passive Apple 13G;
// Temasek Capital's real 13D on e2open, a real, reported Elliott
// Management activist situation).

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import BeneficialOwnershipPage from "./page";
import { api, ApiError, BeneficialOwnershipDisclosuresResponse } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/beneficial-ownership",
  useRouter: () => ({ push: pushMock }),
}));

const SAMPLE_DISCLOSURES: BeneficialOwnershipDisclosuresResponse = {
  ticker: "AAPL",
  disclosures: [
    {
      cik: "0000320193", filing_date: "2026-04-29", accepted_date: "2026-04-29",
      cusip: "037833100", name_of_reporting_person: "Vanguard Capital Management",
      citizenship_or_place_of_organization: "PENNSYLVANIA",
      sole_voting_power: 0, shared_voting_power: 0, sole_dispositive_power: 0, shared_dispositive_power: 0,
      amount_beneficially_owned: 1099168953, percent_of_class: 0.0748,
      type_of_reporting_person: "IA", form_type: "13G",
      source_url: "https://www.sec.gov/Archives/edgar/data/320193/000210011926000139/xslSCHEDULE_13G_X02/primary_doc.xml",
    },
  ],
  source_note: "Schedule 13D/13G filings, live from FMP.",
};

const SAMPLE_ETWO_DISCLOSURES: BeneficialOwnershipDisclosuresResponse = {
  ticker: "ETWO",
  disclosures: [
    {
      cik: "0001021944", filing_date: "2025-08-11", accepted_date: "2025-08-11",
      cusip: "29788T103", name_of_reporting_person: "Temasek Capital (Private) Limited",
      citizenship_or_place_of_organization: "U0",
      sole_voting_power: 0, shared_voting_power: 0, sole_dispositive_power: 0, shared_dispositive_power: 0,
      amount_beneficially_owned: 0, percent_of_class: 0,
      type_of_reporting_person: "HC", form_type: "13D",
      source_url: "https://www.sec.gov/Archives/edgar/data/1021944/000110465925076163/xslSCHEDULE_13D_X01/primary_doc.xml",
    },
  ],
  source_note: "Schedule 13D/13G filings, live from FMP.",
};

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
  vi.spyOn(api, "getCompanyList").mockResolvedValue({ companies: [] });
});

describe("Beneficial Ownership page", () => {
  it("redirects to /login when no API key is stored", async () => {
    localStorage.clear();
    render(<BeneficialOwnershipPage />);
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/login");
    });
  });

  it("shows a real search box defaulting to AAPL", () => {
    render(<BeneficialOwnershipPage />);
    expect(screen.getByPlaceholderText("e.g. AAPL, ETWO, DIS")).toHaveValue("AAPL");
  });

  it("searching calls getBeneficialOwnershipDisclosures with the entered ticker", async () => {
    const spy = vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue(SAMPLE_DISCLOSURES);
    render(<BeneficialOwnershipPage />);

    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => expect(spy).toHaveBeenCalledWith("AAPL"));
  });

  it("displays a real 13G disclosure with its reporting person and percentage", async () => {
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue(SAMPLE_DISCLOSURES);
    render(<BeneficialOwnershipPage />);

    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("Vanguard Capital Management"));
    expect(screen.getByText("7.48%")).toBeInTheDocument();
    expect(screen.getByText("13G")).toBeInTheDocument();
  });

  it("displays a real 13D disclosure distinctly from 13G", async () => {
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue(SAMPLE_ETWO_DISCLOSURES);
    render(<BeneficialOwnershipPage />);

    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, ETWO, DIS"), {
      target: { value: "ETWO" },
    });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("Temasek Capital (Private) Limited"));
    const badge = screen.getByText("13D");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveStyle({ color: "var(--accent)" });
  });

  it("shows a real, honest empty state when no disclosures are found", async () => {
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockResolvedValue({
      ticker: "ZZZZ", disclosures: [], source_note: "Schedule 13D/13G filings, live from FMP.",
    });
    render(<BeneficialOwnershipPage />);

    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL, ETWO, DIS"), {
      target: { value: "ZZZZ" },
    });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("No 13D/13G disclosures found."));
  });

  it("shows the real error message for a 404 response rather than a generic one", async () => {
    vi.spyOn(api, "getBeneficialOwnershipDisclosures").mockRejectedValue(
      new ApiError(404, "No such ticker")
    );
    render(<BeneficialOwnershipPage />);

    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => screen.getByText("No such ticker"));
  });
});
