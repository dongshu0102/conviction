// Tests for the two real gaps this polish pass fixed directly in
// page.tsx: AddTickerForm previously had no path forward when a
// ticker wasn't ingested yet (a dead-end error, same class of bug
// already fixed for Watchlist and Growth Hunter), and theme members
// could be added but never removed.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import UniversePage from "./page";
import { api, ApiError } from "@/lib/api";

const pushMock = vi.fn();
// A stable object reference, not a fresh {push: pushMock} literal on
// every call -- the same, confirmed root cause found twice already
// tonight (Conviction Screener, then Brokerage): this page's own
// useEffect depends on [loadThemes, router], so an unstable mock
// reference re-triggers loadThemes() on every client-side state
// change, silently undoing state set moments earlier (here,
// confirmingDelete getting reset right after "Delete theme" sets it).
const mockRouter = { push: pushMock };

vi.mock("next/navigation", () => ({
  usePathname: () => "/universe",
  useRouter: () => mockRouter,
}));

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
});

const SAMPLE_THEME = {
  theme: { name: "AI Infrastructure", description: "Compute backbone", created_at: "2026-08-01T00:00:00Z" },
  member_count: 1,
};

function mockBaseLoads() {
  vi.spyOn(api, "listThemes").mockResolvedValue({ themes: [SAMPLE_THEME] });
  vi.spyOn(api, "getThemeTickers").mockResolvedValue({ theme_name: "AI Infrastructure", tickers: ["NVDA"] });
  vi.spyOn(api, "getFactorRankings").mockResolvedValue({ scoring_note: "test", results: [] });
}

describe("Universe — add ticker to theme", () => {
  it("offers an inline ingest option instead of a dead-end error", async () => {
    mockBaseLoads();
    vi.spyOn(api, "addTickerToTheme").mockRejectedValue(
      new ApiError(422, "'NEWCO' has not been ingested yet — ingest it first via POST /companies/NEWCO/ingest before adding it to a theme.")
    );
    render(<UniversePage />);

    await waitFor(() => screen.getByPlaceholderText("Add ticker"));
    fireEvent.change(screen.getByPlaceholderText("Add ticker"), { target: { value: "NEWCO" } });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(screen.getByText(/hasn't been ingested yet/)).toBeInTheDocument();
    });
    expect(screen.getByText("Ingest & add")).toBeInTheDocument();
  });

  it("ingesting then adding actually adds the ticker to the theme", async () => {
    mockBaseLoads();
    vi.spyOn(api, "addTickerToTheme")
      .mockRejectedValueOnce(new ApiError(422, "'NEWCO' has not been ingested yet"))
      .mockResolvedValueOnce({} as any);
    const ingestSpy = vi.spyOn(api, "ingestCompany").mockResolvedValue({ ticker: "NEWCO", income_statements_ingested: 3 });
    render(<UniversePage />);

    await waitFor(() => screen.getByPlaceholderText("Add ticker"));
    fireEvent.change(screen.getByPlaceholderText("Add ticker"), { target: { value: "NEWCO" } });
    fireEvent.click(screen.getByText("Add"));
    await waitFor(() => screen.getByText("Ingest & add"));

    fireEvent.click(screen.getByText("Ingest & add"));

    await waitFor(() => {
      expect(ingestSpy).toHaveBeenCalledWith("NEWCO");
    });
  });

  it("a genuinely different error (not the not-ingested case) shows as a plain error, not the ingest offer", async () => {
    mockBaseLoads();
    vi.spyOn(api, "addTickerToTheme").mockRejectedValue(new Error("Theme not found"));
    render(<UniversePage />);

    await waitFor(() => screen.getByPlaceholderText("Add ticker"));
    fireEvent.change(screen.getByPlaceholderText("Add ticker"), { target: { value: "XYZ" } });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(screen.getByText("Theme not found")).toBeInTheDocument();
    });
    expect(screen.queryByText("Ingest & add")).not.toBeInTheDocument();
  });
});

describe("Universe — remove ticker from theme", () => {
  it("has a remove action on each member row", async () => {
    mockBaseLoads();
    render(<UniversePage />);

    await waitFor(() => screen.getByText("NVDA"));
    expect(screen.getByLabelText("Remove NVDA from AI Infrastructure")).toBeInTheDocument();
  });

  it("clicking remove calls api.removeTickerFromTheme with the correct ticker and theme", async () => {
    mockBaseLoads();
    const removeSpy = vi.spyOn(api, "removeTickerFromTheme").mockResolvedValue(undefined as any);
    render(<UniversePage />);

    await waitFor(() => screen.getByText("NVDA"));
    fireEvent.click(screen.getByLabelText("Remove NVDA from AI Infrastructure"));

    await waitFor(() => {
      expect(removeSpy).toHaveBeenCalledWith("AI Infrastructure", "NVDA");
    });
  });
});

describe("Universe — delete theme", () => {
  it("does not delete on a single click — requires explicit confirmation", async () => {
    mockBaseLoads();
    const deleteSpy = vi.spyOn(api, "deleteTheme");
    render(<UniversePage />);

    await waitFor(() => screen.getByText("Delete theme"));
    fireEvent.click(screen.getByText("Delete theme"));

    await waitFor(() => {
      expect(screen.getByText("Confirm delete")).toBeInTheDocument();
    });
    expect(deleteSpy).not.toHaveBeenCalled();
  });

  it("clicking Confirm delete actually calls api.deleteTheme with the right name", async () => {
    mockBaseLoads();
    const deleteSpy = vi.spyOn(api, "deleteTheme").mockResolvedValue(undefined as any);
    render(<UniversePage />);

    await waitFor(() => screen.getByText("Delete theme"));
    fireEvent.click(screen.getByText("Delete theme"));
    await waitFor(() => screen.getByText("Confirm delete"));
    fireEvent.click(screen.getByText("Confirm delete"));

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith("AI Infrastructure");
    });
  });

  it("clicking Cancel backs out without deleting anything", async () => {
    mockBaseLoads();
    const deleteSpy = vi.spyOn(api, "deleteTheme");
    render(<UniversePage />);

    await waitFor(() => screen.getByText("Delete theme"));
    fireEvent.click(screen.getByText("Delete theme"));
    await waitFor(() => screen.getByText("Cancel"));
    fireEvent.click(screen.getByText("Cancel"));

    await waitFor(() => {
      expect(screen.getByText("Delete theme")).toBeInTheDocument();
    });
    expect(deleteSpy).not.toHaveBeenCalled();
  });

  it("reloads the theme list after a successful delete", async () => {
    mockBaseLoads();
    vi.spyOn(api, "deleteTheme").mockResolvedValue(undefined as any);
    const listSpy = vi.spyOn(api, "listThemes").mockResolvedValue({ themes: [SAMPLE_THEME] });
    render(<UniversePage />);

    await waitFor(() => screen.getByText("Delete theme"));
    const callsBefore = listSpy.mock.calls.length;
    fireEvent.click(screen.getByText("Delete theme"));
    await waitFor(() => screen.getByText("Confirm delete"));
    fireEvent.click(screen.getByText("Confirm delete"));

    await waitFor(() => {
      expect(listSpy.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });
});

const SAMPLE_STRUCTURE = {
  ticker: "NVDA",
  industry: "Semiconductors",
  category: "Oligopoly",
  hhi: 4150.0,
  company_market_share: 0.45,
  peer_count: 3,
  narrative: "A real, grounded explanation of the oligopoly classification.",
  model_used: "test-model",
};

describe("Universe — market structure classification", () => {
  it("shows a Structure button per member", async () => {
    mockBaseLoads();
    render(<UniversePage />);

    await waitFor(() => screen.getByText("NVDA"));
    expect(screen.getByText("Structure")).toBeInTheDocument();
  });

  it("clicking Structure fetches and shows the real, live classification", async () => {
    mockBaseLoads();
    const structureSpy = vi.spyOn(api, "getMarketStructureClassification").mockResolvedValue(SAMPLE_STRUCTURE);
    render(<UniversePage />);

    await waitFor(() => screen.getByText("NVDA"));
    fireEvent.click(screen.getByText("Structure"));

    await waitFor(() => expect(structureSpy).toHaveBeenCalledWith("NVDA"));
    await waitFor(() => screen.getByText("Oligopoly"));
    expect(screen.getByText(/A real, grounded explanation/)).toBeInTheDocument();
    expect(screen.getByText(/HHI 4150/)).toBeInTheDocument();
  });

  it("clicking Structure again collapses it without re-fetching", async () => {
    mockBaseLoads();
    const structureSpy = vi.spyOn(api, "getMarketStructureClassification").mockResolvedValue(SAMPLE_STRUCTURE);
    render(<UniversePage />);

    await waitFor(() => screen.getByText("NVDA"));
    fireEvent.click(screen.getByText("Structure"));
    await waitFor(() => screen.getByText("Oligopoly"));

    fireEvent.click(screen.getByText("Structure"));

    await waitFor(() => {
      expect(screen.queryByText("Oligopoly")).not.toBeInTheDocument();
    });
    expect(structureSpy).toHaveBeenCalledTimes(1); // collapsing must never re-fetch
  });

  it("shows a real, honest error message when classification fails", async () => {
    mockBaseLoads();
    vi.spyOn(api, "getMarketStructureClassification").mockRejectedValue(new Error("no ingested peers"));
    render(<UniversePage />);

    await waitFor(() => screen.getByText("NVDA"));
    fireEvent.click(screen.getByText("Structure"));

    await waitFor(() => screen.getByText("no ingested peers"));
  });

  it("honestly shows an Unclassifiable result without fabricating a real HHI", async () => {
    mockBaseLoads();
    vi.spyOn(api, "getMarketStructureClassification").mockResolvedValue({
      ...SAMPLE_STRUCTURE,
      category: "Unclassifiable (insufficient ingested peer data)",
      hhi: null, company_market_share: null, peer_count: 1,
    });
    render(<UniversePage />);

    await waitFor(() => screen.getByText("NVDA"));
    fireEvent.click(screen.getByText("Structure"));

    await waitFor(() => screen.getByText("Unclassifiable (insufficient ingested peer data)"));
    expect(screen.queryByText(/HHI/)).not.toBeInTheDocument();
  });
});
