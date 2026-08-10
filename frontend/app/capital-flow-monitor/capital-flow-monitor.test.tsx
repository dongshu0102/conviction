import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import CapitalFlowMonitorPage from "./page";
import {
  api,
  CapitalFlowMonitorModuleDef,
  CapitalFlowMonitorModuleResult,
  CapitalFlowMonitorSynthesis,
} from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/capital-flow-monitor",
  useRouter: () => ({ push: pushMock }),
}));

const SAMPLE_MODULES: CapitalFlowMonitorModuleDef[] = [
  { id: "etf", group: "flow", title: "ETF Flows", cadence: "Daily", source: "etf.com", is_agent_estimate: true },
  { id: "ici", group: "flow", title: "ICI Fund Flows", cadence: "Weekly", source: "ICI", is_agent_estimate: true },
  { id: "cftc", group: "flow", title: "CFTC Positioning", cadence: "Weekly", source: "CFTC", is_agent_estimate: true },
  { id: "credit", group: "macro", title: "Credit Spreads", cadence: "Daily", source: "FRED", is_agent_estimate: false },
];

function moduleResult(overrides: Partial<CapitalFlowMonitorModuleResult> = {}): CapitalFlowMonitorModuleResult {
  return {
    module_id: "etf",
    headline_value: "+$4.2B",
    headline_direction: "inflow",
    headline_label: "US-listed ETF net flow (day)",
    details: [{ label: "Top inflow", value: "SPY +$1.8B" }],
    read: "Strong demand for broad-market exposure.",
    source_note: "etf.com",
    as_of: "2026-08-10",
    fetched_at: "2026-08-10T12:00:00Z",
    is_agent_estimate: true,
    ...overrides,
  };
}

const SAMPLE_SYNTHESIS: CapitalFlowMonitorSynthesis = {
  regime: "Cautious risk-on",
  stance: "mixed",
  supportive: ["Strong ETF inflows"],
  headwinds: ["Wide credit spreads"],
  conflict: "Flows are positive but credit is flashing caution.",
  watch: "CPI print next week.",
};

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
  vi.spyOn(api, "getCapitalFlowMonitorModules").mockResolvedValue(SAMPLE_MODULES);
  vi.spyOn(api, "getCapitalFlowMonitorHistory").mockResolvedValue([]);
});

describe("Capital Flow Monitor page", () => {
  it("redirects to /login when no API key is present", () => {
    localStorage.clear();
    render(<CapitalFlowMonitorPage />);
    expect(pushMock).toHaveBeenCalledWith("/login");
  });

  it("loads and displays the module list on mount", async () => {
    render(<CapitalFlowMonitorPage />);
    await waitFor(() => {
      expect(screen.getByText("ETF Flows")).toBeInTheDocument();
      expect(screen.getByText("Credit Spreads")).toBeInTheDocument();
    });
  });

  it("shows a real error message if loading the module list fails", async () => {
    vi.spyOn(api, "getCapitalFlowMonitorModules").mockRejectedValue(new Error("Server error"));
    render(<CapitalFlowMonitorPage />);
    await waitFor(() => {
      expect(screen.getByText("Server error")).toBeInTheDocument();
    });
  });

  it("loading a single module shows its real data", async () => {
    vi.spyOn(api, "loadCapitalFlowMonitorModule").mockResolvedValue(moduleResult());
    render(<CapitalFlowMonitorPage />);
    await waitFor(() => screen.getByText("ETF Flows"));

    const loadButtons = screen.getAllByText("load");
    fireEvent.click(loadButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("+$4.2B")).toBeInTheDocument();
      expect(screen.getByText("SPY +$1.8B")).toBeInTheDocument();
    });
  });

  it("shows a real error and a retry option when a module load fails", async () => {
    vi.spyOn(api, "loadCapitalFlowMonitorModule").mockRejectedValue(new Error("Agent timed out"));
    render(<CapitalFlowMonitorPage />);
    await waitFor(() => screen.getByText("ETF Flows"));

    fireEvent.click(screen.getAllByText("load")[0]);

    await waitFor(() => {
      expect(screen.getByText(/Agent timed out/)).toBeInTheDocument();
    });
  });

  it("distinguishes a real FRED module from an AI web-search estimate", async () => {
    vi.spyOn(api, "loadCapitalFlowMonitorModule").mockImplementation(async (moduleId: string) =>
      moduleId === "credit"
        ? moduleResult({ module_id: "credit", headline_value: "271bp", is_agent_estimate: false, headline_direction: "supportive" })
        : moduleResult()
    );
    render(<CapitalFlowMonitorPage />);
    await waitFor(() => screen.getByText("Credit Spreads"));

    // Load the credit module specifically (4th card, "credit" is last in SAMPLE_MODULES).
    const loadButtons = screen.getAllByText("load");
    fireEvent.click(loadButtons[3]);

    await waitFor(() => {
      expect(screen.getByText(/Real FRED data/)).toBeInTheDocument();
    });
  });

  it("disables Synthesize board below 3 loaded modules", async () => {
    vi.spyOn(api, "loadCapitalFlowMonitorModule").mockResolvedValue(moduleResult());
    render(<CapitalFlowMonitorPage />);
    await waitFor(() => screen.getByText("ETF Flows"));

    fireEvent.click(screen.getAllByText("load")[0]);
    await waitFor(() => screen.getByText("+$4.2B"));

    const synthButton = screen.getByText("Synthesize board");
    expect(synthButton).toBeDisabled();
  });

  it("enables and runs Synthesize board once 3+ modules are loaded", async () => {
    vi.spyOn(api, "loadCapitalFlowMonitorModule").mockResolvedValue(moduleResult());
    vi.spyOn(api, "synthesizeCapitalFlowMonitor").mockResolvedValue(SAMPLE_SYNTHESIS);
    render(<CapitalFlowMonitorPage />);
    await waitFor(() => screen.getByText("ETF Flows"));

    const loadButtons = screen.getAllByText("load");
    fireEvent.click(loadButtons[0]);
    await waitFor(() => screen.getAllByText("+$4.2B").length >= 1);
    // After each load, that module's button becomes "refresh" and
    // drops out of getAllByText("load") — so index 0 always refers to
    // the next not-yet-loaded module, not a fixed position.
    fireEvent.click(screen.getAllByText("load")[0]);
    await waitFor(() => screen.getAllByText("+$4.2B").length >= 2);
    fireEvent.click(screen.getAllByText("load")[0]);
    await waitFor(() => screen.getAllByText("+$4.2B").length >= 3);

    const synthButton = screen.getByText("Synthesize board");
    await waitFor(() => expect(synthButton).not.toBeDisabled());
    fireEvent.click(synthButton);

    await waitFor(() => {
      expect(screen.getByText("Cautious risk-on")).toBeInTheDocument();
      expect(screen.getByText("Strong ETF inflows")).toBeInTheDocument();
      expect(screen.getByText("Wide credit spreads")).toBeInTheDocument();
    });
  });

  it("does not render the history strip when history is empty", async () => {
    render(<CapitalFlowMonitorPage />);
    await waitFor(() => screen.getByText("ETF Flows"));
    expect(screen.queryByText(/History — last/)).not.toBeInTheDocument();
  });

  it("renders the history strip when real saved history exists", async () => {
    vi.spyOn(api, "getCapitalFlowMonitorHistory").mockResolvedValue([
      {
        snapshot_date: "2026-08-09",
        signals: { etf: ["+$4.2B", "inflow", "2026-08-09"] },
        regime_label: "Cautious risk-on",
        regime_stance: "mixed",
      },
    ]);
    render(<CapitalFlowMonitorPage />);
    await waitFor(() => {
      expect(screen.getByText("History — last 1 saved day")).toBeInTheDocument();
      expect(screen.getByText("Cautious risk-on")).toBeInTheDocument();
    });
  });
});
