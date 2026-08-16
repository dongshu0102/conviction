import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { useState } from "react";
import { TickerAutocomplete } from "./TickerAutocomplete";
import { api, CompanyListItem } from "@/lib/api";

const SAMPLE_COMPANIES: CompanyListItem[] = [
  { ticker: "AAPL", name: "APPLE INC" },
  { ticker: "AMD", name: "ADVANCED MICRO DEVICES INC" },
  { ticker: "MSFT", name: "MICROSOFT CORP" },
];

function Harness({ onSelect }: { onSelect?: (item: CompanyListItem) => void }) {
  const [value, setValue] = useState("");
  return <TickerAutocomplete value={value} onChange={setValue} onSelect={onSelect} placeholder="Ticker" />;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("TickerAutocomplete", () => {
  it("shows suggestions matching by ticker prefix", async () => {
    vi.spyOn(api, "getCompanyList").mockResolvedValue({ companies: SAMPLE_COMPANIES });
    render(<Harness />);

    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("Ticker"), { target: { value: "AA" } });

    await waitFor(() => screen.getByText("AAPL"));
    expect(screen.queryByText("MSFT")).not.toBeInTheDocument();
  });

  it("shows suggestions matching by company name substring", async () => {
    vi.spyOn(api, "getCompanyList").mockResolvedValue({ companies: SAMPLE_COMPANIES });
    render(<Harness />);

    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("Ticker"), { target: { value: "micro" } });

    await waitFor(() => screen.getByText("MICROSOFT CORP"));
    expect(screen.getByText("ADVANCED MICRO DEVICES INC")).toBeInTheDocument();
  });

  it("clicking a suggestion selects it and closes the dropdown", async () => {
    const onSelect = vi.fn();
    vi.spyOn(api, "getCompanyList").mockResolvedValue({ companies: SAMPLE_COMPANIES });
    render(<Harness onSelect={onSelect} />);

    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("Ticker"), { target: { value: "AA" } });
    await waitFor(() => screen.getByText("AAPL"));

    fireEvent.mouseDown(screen.getByText("AAPL"));

    expect(onSelect).toHaveBeenCalledWith({ ticker: "AAPL", name: "APPLE INC" });
    await waitFor(() => expect(screen.queryByText("APPLE INC")).not.toBeInTheDocument());
  });

  it("shows no suggestions when the input is empty", async () => {
    vi.spyOn(api, "getCompanyList").mockResolvedValue({ companies: SAMPLE_COMPANIES });
    render(<Harness />);

    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
  });

  it("degrades gracefully when the company list request fails", async () => {
    vi.spyOn(api, "getCompanyList").mockRejectedValue(new Error("network error"));
    render(<Harness />);

    fireEvent.change(screen.getByPlaceholderText("Ticker"), { target: { value: "AA" } });

    // The input itself keeps working; no crash, no suggestions, no visible error.
    expect(screen.getByPlaceholderText("Ticker")).toHaveValue("AA");
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
  });

  it("arrow-down then enter selects the highlighted suggestion", async () => {
    const onSelect = vi.fn();
    vi.spyOn(api, "getCompanyList").mockResolvedValue({ companies: SAMPLE_COMPANIES });
    render(<Harness onSelect={onSelect} />);

    await waitFor(() => expect(api.getCompanyList).toHaveBeenCalled());
    const input = screen.getByPlaceholderText("Ticker");
    fireEvent.change(input, { target: { value: "A" } }); // matches AAPL and AMD
    await waitFor(() => screen.getByText("AAPL"));

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onSelect).toHaveBeenCalledWith({ ticker: "AMD", name: "ADVANCED MICRO DEVICES INC" });
  });
});
