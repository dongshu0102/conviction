// Tests for the Watchlist Terminal's add/remove functionality — the
// real gap this polish pass fixed. Before this, addToWatchlist and
// removeFromWatchlist were called from NOWHERE in the frontend at
// all (confirmed by grep before building this), despite the backend
// fully supporting both. Same unverified-in-sandbox caveat as every
// other frontend test this session.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import TerminalPage from "./page";
import { api, ApiError } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/terminal",
  useRouter: () => ({ push: pushMock }),
}));

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
});

const EMPTY_TRIAGE = {
  as_of: "2026-08-03T12:00:00Z",
  scoring_note: "Higher score = more attention-worthy.",
  items: [],
  tickers_excluded: [],
};

function mockLoads(triageItems: any[] = []) {
  vi.spyOn(api, "getTriage").mockResolvedValue({ ...EMPTY_TRIAGE, items: triageItems });
  vi.spyOn(api, "getWatchlistNews").mockResolvedValue({ news: {}, tickers_failed: [] });
  vi.spyOn(api, "getUpcomingEarnings").mockResolvedValue({ events: [] });
}

const SAMPLE_ITEM = {
  ticker: "NVDA",
  list_name: "Default",
  triage_score: 4.2,
  notes: null,
  signals: {
    day_move_pct: 0.012, move_since_added_pct: 0.05, momentum_1m_pct: 0.03,
    pe_drift_pct: null, target_crossed: false, current_price: 180.5, current_pe: 42,
  },
};

describe("Watchlist Terminal — add ticker", () => {
  it("has a visible add-ticker form (the real gap: previously none existed anywhere)", async () => {
    mockLoads([]);
    render(<TerminalPage />);
    await waitFor(() => screen.getByPlaceholderText(/Add ticker/));
  });

  it("submitting the add form calls api.addToWatchlist with the uppercased ticker", async () => {
    mockLoads([]);
    const addSpy = vi.spyOn(api, "addToWatchlist").mockResolvedValue({
      ...SAMPLE_ITEM,
    } as any);
    render(<TerminalPage />);

    await waitFor(() => screen.getByPlaceholderText(/Add ticker/));
    fireEvent.change(screen.getByPlaceholderText(/Add ticker/), { target: { value: "nvda" } });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(addSpy).toHaveBeenCalledWith("NVDA", undefined);
    });
  });

  it("reloads the triage table after a successful add", async () => {
    mockLoads([]);
    vi.spyOn(api, "addToWatchlist").mockResolvedValue(SAMPLE_ITEM as any);
    const triageSpy = vi.spyOn(api, "getTriage").mockResolvedValue({ ...EMPTY_TRIAGE, items: [] });
    render(<TerminalPage />);

    await waitFor(() => screen.getByPlaceholderText(/Add ticker/));
    const callsBefore = triageSpy.mock.calls.length;
    fireEvent.change(screen.getByPlaceholderText(/Add ticker/), { target: { value: "NVDA" } });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(triageSpy.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it("shows an error message if adding fails, without crashing the page", async () => {
    mockLoads([]);
    vi.spyOn(api, "addToWatchlist").mockRejectedValue(new Error("Ticker not ingested"));
    render(<TerminalPage />);

    await waitFor(() => screen.getByPlaceholderText(/Add ticker/));
    fireEvent.change(screen.getByPlaceholderText(/Add ticker/), { target: { value: "ZZZZ" } });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(screen.getByText("Ticker not ingested")).toBeInTheDocument();
    });
  });

  it("rejects a natural-language phrase client-side, without ever calling the API — the real reported bug: the empty-state's own suggested chat phrasing got pasted into this plain-ticker box and sent as a literal ticker", async () => {
    mockLoads([]);
    const addSpy = vi.spyOn(api, "addToWatchlist");
    render(<TerminalPage />);

    await waitFor(() => screen.getByPlaceholderText(/Add ticker/));
    fireEvent.change(screen.getByPlaceholderText(/Add ticker/), {
      target: { value: "add NVDA to my AI Watch list with a $150 entry target" },
    });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(screen.getByText(/doesn't look like a ticker symbol/)).toBeInTheDocument();
    });
    expect(addSpy).not.toHaveBeenCalled();
  });
});

describe("Watchlist Terminal — remove ticker", () => {
  it("has a remove action on each row (the other real gap — previously none existed)", async () => {
    mockLoads([SAMPLE_ITEM]);
    render(<TerminalPage />);
    await waitFor(() => screen.getByText("NVDA"));
    expect(screen.getByLabelText("Remove NVDA from watchlist")).toBeInTheDocument();
  });

  it("clicking remove calls api.removeFromWatchlist with the correct ticker and list", async () => {
    mockLoads([SAMPLE_ITEM]);
    const removeSpy = vi.spyOn(api, "removeFromWatchlist").mockResolvedValue({ removed: true });
    render(<TerminalPage />);

    await waitFor(() => screen.getByText("NVDA"));
    fireEvent.click(screen.getByLabelText("Remove NVDA from watchlist"));

    await waitFor(() => {
      expect(removeSpy).toHaveBeenCalledWith("NVDA", "Default");
    });
  });
});

describe("Watchlist Terminal — add a ticker that hasn't been ingested yet", () => {
  it("offers an inline ingest option instead of just showing a dead-end error", async () => {
    mockLoads([]);
    vi.spyOn(api, "addToWatchlist").mockRejectedValue(
      new ApiError(422, "'PINS' has not been ingested yet — ingest it first via POST /companies/PINS/ingest before adding to a watchlist.")
    );
    render(<TerminalPage />);

    await waitFor(() => screen.getByPlaceholderText(/Add ticker/));
    fireEvent.change(screen.getByPlaceholderText(/Add ticker/), { target: { value: "PINS" } });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(screen.getByText(/hasn't been ingested yet/)).toBeInTheDocument();
    });
    expect(screen.getByText("Ingest & add")).toBeInTheDocument();
  });

  it("ingesting then adding actually adds the ticker", async () => {
    mockLoads([]);
    vi.spyOn(api, "addToWatchlist")
      .mockRejectedValueOnce(new ApiError(422, "'PINS' has not been ingested yet"))
      .mockResolvedValueOnce(SAMPLE_ITEM as any);
    const ingestSpy = vi.spyOn(api, "ingestCompany").mockResolvedValue({
      ticker: "PINS", income_statements_ingested: 5,
    });
    render(<TerminalPage />);

    await waitFor(() => screen.getByPlaceholderText(/Add ticker/));
    fireEvent.change(screen.getByPlaceholderText(/Add ticker/), { target: { value: "PINS" } });
    fireEvent.click(screen.getByText("Add"));
    await waitFor(() => screen.getByText("Ingest & add"));

    fireEvent.click(screen.getByText("Ingest & add"));

    await waitFor(() => {
      expect(ingestSpy).toHaveBeenCalledWith("PINS");
    });
  });

  it("a genuinely malformed ticker never triggers the ingest offer", async () => {
    mockLoads([]);
    const addSpy = vi.spyOn(api, "addToWatchlist");
    render(<TerminalPage />);

    await waitFor(() => screen.getByPlaceholderText(/Add ticker/));
    fireEvent.change(screen.getByPlaceholderText(/Add ticker/), { target: { value: "not a ticker" } });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(screen.getByText(/doesn't look like a ticker symbol/)).toBeInTheDocument();
    });
    expect(addSpy).not.toHaveBeenCalled();
    expect(screen.queryByText("Ingest & add")).not.toBeInTheDocument();
  });
});
