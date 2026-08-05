// Tests for SuggestTheme — exposing a backend capability (suggest_theme)
// that previously had zero UI. Key properties worth verifying: nothing
// gets created until the person explicitly confirms, individual
// candidates can be deselected, and only already_ingested=false
// tickers get an ingest call before being added.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { SuggestTheme } from "./SuggestTheme";
import { api } from "@/lib/api";

const onCreated = vi.fn();

beforeEach(() => {
  onCreated.mockClear();
  vi.restoreAllMocks();
});

const SAMPLE_SUGGESTION = {
  theme_name: "AI Infrastructure",
  rationale: "Companies building the compute backbone for AI workloads.",
  candidate_tickers: [
    { ticker: "NVDA", company_name: "NVIDIA", reasoning: "GPU leader", already_ingested: true },
    { ticker: "NEWCO", company_name: "New Co", reasoning: "Emerging player", already_ingested: false },
  ],
  sourced_headlines: ["Some real headline about AI chips"],
  generated_at: "2026-08-05T00:00:00Z",
  model_used: "test-model",
};

describe("SuggestTheme", () => {
  it("does nothing until the person clicks Suggest — no autonomous action on mount", () => {
    const spy = vi.spyOn(api, "suggestTheme");
    render(<SuggestTheme onCreated={onCreated} />);
    expect(spy).not.toHaveBeenCalled();
  });

  it("shows the suggestion with all candidates pre-selected", async () => {
    vi.spyOn(api, "suggestTheme").mockResolvedValue(SAMPLE_SUGGESTION);
    render(<SuggestTheme onCreated={onCreated} />);

    fireEvent.click(screen.getByText("Suggest"));
    await waitFor(() => screen.getByText("AI Infrastructure"));

    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(checkboxes).toHaveLength(2);
    expect(checkboxes.every((c) => c.checked)).toBe(true);
  });

  it("deselecting a candidate excludes it from the create step", async () => {
    vi.spyOn(api, "suggestTheme").mockResolvedValue(SAMPLE_SUGGESTION);
    const createThemeSpy = vi.spyOn(api, "createTheme").mockResolvedValue({} as any);
    const addSpy = vi.spyOn(api, "addTickerToTheme").mockResolvedValue({} as any);
    render(<SuggestTheme onCreated={onCreated} />);

    fireEvent.click(screen.getByText("Suggest"));
    await waitFor(() => screen.getByText("AI Infrastructure"));

    // Deselect NEWCO, leaving only NVDA.
    const newcoCheckbox = screen.getByText("NEWCO").closest("label")!.querySelector("input")!;
    fireEvent.click(newcoCheckbox);

    fireEvent.click(screen.getByText(/Create theme with 1 ticker/));

    await waitFor(() => {
      expect(createThemeSpy).toHaveBeenCalledWith("AI Infrastructure", SAMPLE_SUGGESTION.rationale);
    });
    await waitFor(() => {
      expect(addSpy).toHaveBeenCalledWith("AI Infrastructure", "NVDA");
    });
    expect(addSpy).not.toHaveBeenCalledWith("AI Infrastructure", "NEWCO");
  });

  it("ingests only the not-already-ingested candidates before adding them", async () => {
    vi.spyOn(api, "suggestTheme").mockResolvedValue(SAMPLE_SUGGESTION);
    vi.spyOn(api, "createTheme").mockResolvedValue({} as any);
    vi.spyOn(api, "addTickerToTheme").mockResolvedValue({} as any);
    const ingestSpy = vi.spyOn(api, "ingestCompany").mockResolvedValue({ ticker: "NEWCO", income_statements_ingested: 3 });
    render(<SuggestTheme onCreated={onCreated} />);

    fireEvent.click(screen.getByText("Suggest"));
    await waitFor(() => screen.getByText("AI Infrastructure"));
    fireEvent.click(screen.getByText(/Create theme with 2 tickers/));

    await waitFor(() => {
      expect(ingestSpy).toHaveBeenCalledWith("NEWCO");
    });
    expect(ingestSpy).not.toHaveBeenCalledWith("NVDA");
  });

  it("calls onCreated with the theme name after a successful create", async () => {
    vi.spyOn(api, "suggestTheme").mockResolvedValue(SAMPLE_SUGGESTION);
    vi.spyOn(api, "createTheme").mockResolvedValue({} as any);
    vi.spyOn(api, "addTickerToTheme").mockResolvedValue({} as any);
    vi.spyOn(api, "ingestCompany").mockResolvedValue({ ticker: "NEWCO", income_statements_ingested: 3 });
    render(<SuggestTheme onCreated={onCreated} />);

    fireEvent.click(screen.getByText("Suggest"));
    await waitFor(() => screen.getByText("AI Infrastructure"));
    fireEvent.click(screen.getByText(/Create theme with 2 tickers/));

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith("AI Infrastructure");
    });
  });

  it("shows an error message if the suggestion request fails, without crashing", async () => {
    vi.spyOn(api, "suggestTheme").mockRejectedValue(new Error("News unavailable"));
    render(<SuggestTheme onCreated={onCreated} />);

    fireEvent.click(screen.getByText("Suggest"));

    await waitFor(() => {
      expect(screen.getByText("News unavailable")).toBeInTheDocument();
    });
  });
});
