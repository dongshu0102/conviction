// Tests for the Alerts page — before this, the entire monitoring
// pipeline's output was invisible on the web, despite both price
// monitoring and growth-candidate checks genuinely running on a
// production schedule.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import AlertsPage from "./page";
import { api, Alert } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/alerts",
  useRouter: () => ({ push: pushMock }),
}));

const SAMPLE_ALERT: Alert = {
  id: 1,
  user_id: "alice",
  ticker: "NVDA",
  alert_type: "GROWTH_CONDITION_CHANGED",
  message: "NVDA: revenue growth trend flipped from accelerating to decelerating.",
  change_pct: null,
  is_read: false,
  created_at: "2026-08-06T20:01:47Z",
};

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
});

describe("Alerts page", () => {
  it("redirects to /login when no API key is stored", async () => {
    localStorage.clear();
    render(<AlertsPage />);
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/login");
    });
  });

  it("shows the empty state when there are no alerts", async () => {
    vi.spyOn(api, "getAlerts").mockResolvedValue([]);
    render(<AlertsPage />);
    await waitFor(() => {
      expect(screen.getByText("No alerts yet.")).toBeInTheDocument();
    });
  });

  it("renders a real alert with its ticker, type, and message", async () => {
    vi.spyOn(api, "getAlerts").mockResolvedValue([SAMPLE_ALERT]);
    render(<AlertsPage />);

    await waitFor(() => screen.getByText("NVDA"));
    expect(screen.getByText("Growth condition changed")).toBeInTheDocument();
    expect(
      screen.getByText("NVDA: revenue growth trend flipped from accelerating to decelerating.")
    ).toBeInTheDocument();
  });

  it("toggling Unread only calls the API with the correct flag", async () => {
    const getSpy = vi.spyOn(api, "getAlerts").mockResolvedValue([]);
    render(<AlertsPage />);

    await waitFor(() => expect(getSpy).toHaveBeenCalledWith(false));
    fireEvent.click(screen.getByRole("checkbox"));

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith(true);
    });
  });

  it("clicking Mark read calls the API with the correct alert id", async () => {
    vi.spyOn(api, "getAlerts").mockResolvedValue([SAMPLE_ALERT]);
    const markSpy = vi.spyOn(api, "markAlertRead").mockResolvedValue(undefined as any);
    render(<AlertsPage />);

    await waitFor(() => screen.getByText("Mark read"));
    fireEvent.click(screen.getByText("Mark read"));

    await waitFor(() => {
      expect(markSpy).toHaveBeenCalledWith(1);
    });
  });

  it("does not show a Mark read button for an already-read alert", async () => {
    vi.spyOn(api, "getAlerts").mockResolvedValue([{ ...SAMPLE_ALERT, is_read: true }]);
    render(<AlertsPage />);

    await waitFor(() => screen.getByText("NVDA"));
    expect(screen.queryByText("Mark read")).not.toBeInTheDocument();
  });

  it("clicking Check now calls the API and shows a real result message", async () => {
    vi.spyOn(api, "getAlerts").mockResolvedValue([]);
    const checkSpy = vi.spyOn(api, "checkAlerts").mockResolvedValue([]);
    render(<AlertsPage />);

    await waitFor(() => screen.getByText("Check now"));
    fireEvent.click(screen.getByText("Check now"));

    await waitFor(() => {
      expect(checkSpy).toHaveBeenCalled();
      expect(
        screen.getByText("No new price moves or earnings alerts detected since the last check.")
      ).toBeInTheDocument();
    });
  });

  it("shows a real error message if loading alerts fails", async () => {
    vi.spyOn(api, "getAlerts").mockRejectedValue(new Error("Server error"));
    render(<AlertsPage />);

    await waitFor(() => {
      expect(screen.getByText("Server error")).toBeInTheDocument();
    });
  });
});
