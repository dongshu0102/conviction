// Tests for the Real Brokerage Trading page. Given real money is at
// stake, special focus on the multi-layer confirmation safeguards:
// preview never places a real order, the "type the ticker" gate, and
// the brokerage's own separate warning-confirmation flow.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import BrokeragePage from "./page";
import { api, PlaceOrderResponse, BrokerageAccountSummary } from "@/lib/api";

const pushMock = vi.fn();
// A stable object reference, not a fresh {push: pushMock} literal on
// every call -- confirmed as a real, root-cause bug source earlier
// tonight (see conviction-screener.test.tsx): this page's own
// useEffect depends on [router], so an unstable mock reference would
// re-trigger every fetch inside it on every client-side state change
// (e.g. toggling a checkbox), not just on genuine navigation.
const mockRouter = { push: pushMock };

vi.mock("next/navigation", () => ({
  usePathname: () => "/brokerage",
  useRouter: () => mockRouter,
}));

const SAMPLE_ACCOUNT: BrokerageAccountSummary = {
  account_id: "DU1234567", cash: 50000, buying_power: 100000, equity: 75000, currency: "USD",
};

const PREVIEW_RESPONSE: PlaceOrderResponse = {
  confirmed: false, order_result: null,
  source_note: "Interactive Brokers, live brokerage integration.",
};

const SUBMITTED_RESPONSE: PlaceOrderResponse = {
  confirmed: true,
  order_result: { status: "submitted", order_id: "ORD-999", reply_id: null, warning_messages: [], rejection_reason: null },
  source_note: "Interactive Brokers, live brokerage integration.",
};

const NEEDS_CONFIRMATION_RESPONSE: PlaceOrderResponse = {
  confirmed: true,
  order_result: {
    status: "needs_confirmation", order_id: null, reply_id: "reply-abc",
    warning_messages: ["price exceeds the 3% constraint"], rejection_reason: null,
  },
  source_note: "Interactive Brokers, live brokerage integration.",
};

const REJECTED_RESPONSE: PlaceOrderResponse = {
  confirmed: true,
  order_result: { status: "rejected", order_id: null, reply_id: null, warning_messages: [], rejection_reason: "insufficient buying power" },
  source_note: "Interactive Brokers, live brokerage integration.",
};

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
  localStorage.setItem("conviction_api_key", "fi_live_test123");
  vi.restoreAllMocks();
  vi.spyOn(api, "getBrokerageAccountSummary").mockResolvedValue(SAMPLE_ACCOUNT);
  vi.spyOn(api, "getBrokeragePositions").mockResolvedValue({ positions: [] });
});

async function fillAndPreview() {
  // Wait for BrokeragePage's own mount-time fetches (account summary,
  // positions) to resolve first -- without this, their state updates
  // can land after this helper's own fireEvent calls, causing a real
  // not-wrapped-in-act() warning in every test that uses this helper.
  await waitFor(() => expect(api.getBrokerageAccountSummary).toHaveBeenCalled());
  fireEvent.change(screen.getByPlaceholderText("Ticker, e.g. AAPL"), { target: { value: "AAPL" } });
  fireEvent.change(screen.getByPlaceholderText("Shares"), { target: { value: "10" } });
  fireEvent.click(screen.getByText("Preview order"));
  await waitFor(() => screen.getByText("Order preview — nothing placed yet"));
}

describe("Brokerage Trading page", () => {
  it("redirects to /login when no API key is stored", async () => {
    localStorage.clear();
    render(<BrokeragePage />);
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/login");
    });
  });

  it("shows the real account summary", async () => {
    render(<BrokeragePage />);
    await waitFor(() => screen.getByText("Cash: $50,000.00"));
    expect(screen.getByText("Buying power: $100,000.00")).toBeInTheDocument();
  });

  it("previewing calls placeOrder with confirm=false and never places a real order", async () => {
    const spy = vi.spyOn(api, "placeOrder").mockResolvedValue(PREVIEW_RESPONSE);
    render(<BrokeragePage />);
    await fillAndPreview();

    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ confirm: false, ticker: "AAPL", quantity: 10 }));
  });

  it("the confirm button stays disabled until the exact ticker is typed", async () => {
    vi.spyOn(api, "placeOrder").mockResolvedValue(PREVIEW_RESPONSE);
    render(<BrokeragePage />);
    await fillAndPreview();

    const confirmButton = screen.getByText("Confirm and place real order");
    expect(confirmButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('Type "AAPL" to confirm'), { target: { value: "WRONG" } });
    expect(confirmButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('Type "AAPL" to confirm'), { target: { value: "AAPL" } });
    expect(confirmButton).not.toBeDisabled();
  });

  it("confirming with the correct ticker calls placeOrder with confirm=true", async () => {
    const spy = vi.spyOn(api, "placeOrder")
      .mockResolvedValueOnce(PREVIEW_RESPONSE)
      .mockResolvedValueOnce(SUBMITTED_RESPONSE);
    render(<BrokeragePage />);
    await fillAndPreview();

    fireEvent.change(screen.getByPlaceholderText('Type "AAPL" to confirm'), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByText("Confirm and place real order"));

    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.objectContaining({ confirm: true })));
    await waitFor(() => screen.getByText("Order submitted — brokerage order id ORD-999"));
  });

  it("a needs_confirmation result shows the real warning and requires the checkbox before confirming", async () => {
    vi.spyOn(api, "placeOrder")
      .mockResolvedValueOnce(PREVIEW_RESPONSE)
      .mockResolvedValueOnce(NEEDS_CONFIRMATION_RESPONSE);
    const confirmSpy = vi.spyOn(api, "confirmBrokerageOrder").mockResolvedValue(
      { status: "submitted", order_id: "ORD-1000", reply_id: null, warning_messages: [], rejection_reason: null }
    );
    render(<BrokeragePage />);
    await fillAndPreview();

    fireEvent.change(screen.getByPlaceholderText('Type "AAPL" to confirm'), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByText("Confirm and place real order"));

    await waitFor(() => screen.getByText("price exceeds the 3% constraint"));

    const warningConfirmButton = screen.getByText("Confirm warning and place real order");
    expect(warningConfirmButton).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox"));
    expect(warningConfirmButton).not.toBeDisabled();

    fireEvent.click(warningConfirmButton);
    await waitFor(() => expect(confirmSpy).toHaveBeenCalledWith("reply-abc"));
  });

  it("a rejected order shows the real rejection reason and a way to start over", async () => {
    vi.spyOn(api, "placeOrder")
      .mockResolvedValueOnce(PREVIEW_RESPONSE)
      .mockResolvedValueOnce(REJECTED_RESPONSE);
    render(<BrokeragePage />);
    await fillAndPreview();

    fireEvent.change(screen.getByPlaceholderText('Type "AAPL" to confirm'), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByText("Confirm and place real order"));

    await waitFor(() => screen.getByText("Rejected by the brokerage: insufficient buying power"));
    expect(screen.getByText("Start over")).toBeInTheDocument();
  });
});

const SAMPLE_HISTORY_ENTRY = {
  order_id: "ORD-1", ticker: "AAPL", side: "buy", quantity: 1, order_type: "market",
  status: "filled", filled_quantity: 1, filled_avg_price: 150.25, submitted_at: "2026-08-21T13:30:00Z",
};

describe("Brokerage Trading page — order history, status, cancel, sync", () => {
  beforeEach(() => {
    vi.spyOn(api, "getOrderHistory").mockResolvedValue({ entries: [SAMPLE_HISTORY_ENTRY] });
  });

  it("shows the real order history on load", async () => {
    render(<BrokeragePage />);

    await waitFor(() => screen.getByText("AAPL"));
    expect(screen.getByText("buy 1 · market")).toBeInTheDocument();
    expect(screen.getByText("filled")).toBeInTheDocument();
  });

  it("shows an honest empty state when there is no order history yet", async () => {
    vi.spyOn(api, "getOrderHistory").mockResolvedValue({ entries: [] });
    render(<BrokeragePage />);

    await waitFor(() => screen.getByText("No orders yet."));
  });

  it("checking status shows the real, live result inline", async () => {
    const statusSpy = vi.spyOn(api, "getOrderStatus").mockResolvedValue({
      order_id: "ORD-1", status: "filled", filled_quantity: 1, filled_avg_price: 150.25,
    });
    render(<BrokeragePage />);
    await waitFor(() => screen.getByText("AAPL"));

    fireEvent.click(screen.getByText("Check status"));

    await waitFor(() => expect(statusSpy).toHaveBeenCalledWith("ORD-1"));
    await waitFor(() => screen.getByText("Status: filled — 1 filled @ $150.25"));
  });

  it("canceling requires a genuine, explicit confirmation, not just one click", async () => {
    const cancelSpy = vi.spyOn(api, "cancelOrder").mockResolvedValue({ success: true, reason: null });
    render(<BrokeragePage />);
    await waitFor(() => screen.getByText("AAPL"));

    fireEvent.click(screen.getByText("Cancel"));

    // The real cancellation must NOT have been called yet -- only a
    // confirmation prompt should have appeared.
    await waitFor(() => screen.getByText("Confirm cancel"));
    expect(cancelSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("Never mind"));
    expect(screen.queryByText("Confirm cancel")).not.toBeInTheDocument();
    expect(cancelSpy).not.toHaveBeenCalled();
  });

  it("canceling a genuinely cancelable order shows success and refreshes history", async () => {
    const cancelSpy = vi.spyOn(api, "cancelOrder").mockResolvedValue({ success: true, reason: null });
    // A "successful" cancel still re-verifies the real, current status
    // before declaring "Canceled." -- see the honest re-verification test below.
    vi.spyOn(api, "getOrderStatus").mockResolvedValue({
      order_id: "ORD-1", status: "canceled", filled_quantity: 0, filled_avg_price: null,
    });
    render(<BrokeragePage />);
    await waitFor(() => screen.getByText("AAPL"));

    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() => screen.getByText("Confirm cancel"));
    fireEvent.click(screen.getByText("Confirm cancel"));

    await waitFor(() => expect(cancelSpy).toHaveBeenCalledWith("ORD-1"));
    await waitFor(() => screen.getByText("Canceled."));
    // A successful, verified cancel triggers a real refresh, not just a local guess.
    expect(api.getOrderHistory).toHaveBeenCalledTimes(2);
  });

  it("honestly reports when a cancel is accepted but the order's real status is not actually canceled", async () => {
    // The real, known race: the brokerage accepts the cancel REQUEST
    // (success: true), but the order genuinely, actually filled just
    // before the cancel reached it -- this must never be shown as a
    // plain "Canceled." that misrepresents the order's real state.
    vi.spyOn(api, "cancelOrder").mockResolvedValue({ success: true, reason: null });
    vi.spyOn(api, "getOrderStatus").mockResolvedValue({
      order_id: "ORD-1", status: "filled", filled_quantity: 1, filled_avg_price: 150.25,
    });
    render(<BrokeragePage />);
    await waitFor(() => screen.getByText("AAPL"));

    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() => screen.getByText("Confirm cancel"));
    fireEvent.click(screen.getByText("Confirm cancel"));

    await waitFor(() => screen.getByText(/real, current status is "filled"/));
    expect(screen.queryByText("Canceled.")).not.toBeInTheDocument();
  });

  it("a genuinely non-cancelable order shows the real, honest reason, not a fabricated success", async () => {
    vi.spyOn(api, "cancelOrder").mockResolvedValue({
      success: false, reason: "Order is no longer cancelable (e.g. already filled).",
    });
    render(<BrokeragePage />);
    await waitFor(() => screen.getByText("AAPL"));

    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() => screen.getByText("Confirm cancel"));
    fireEvent.click(screen.getByText("Confirm cancel"));

    await waitFor(() => screen.getByText("Order is no longer cancelable (e.g. already filled)."));
  });

  it("the Sync to portfolio button is disabled for a genuinely unfilled order", async () => {
    vi.spyOn(api, "getOrderHistory").mockResolvedValue({
      entries: [{ ...SAMPLE_HISTORY_ENTRY, status: "accepted", filled_quantity: 0, filled_avg_price: null }],
    });
    render(<BrokeragePage />);

    await waitFor(() => screen.getByText("AAPL"));
    expect(screen.getByText("Sync to portfolio")).toBeDisabled();
  });

  it("syncing a genuinely filled order shows the real, resulting position", async () => {
    const syncSpy = vi.spyOn(api, "syncOrderToPortfolio").mockResolvedValue({
      ticker: "AAPL", shares: 1, cost_basis_per_share: 150.25, position_closed: false,
    });
    render(<BrokeragePage />);
    await waitFor(() => screen.getByText("AAPL"));

    fireEvent.click(screen.getByText("Sync to portfolio"));

    await waitFor(() => expect(syncSpy).toHaveBeenCalledWith("ORD-1", "AAPL", "buy"));
    await waitFor(() => screen.getByText("Synced — now 1 sh of AAPL @ $150.25 avg."));
  });

  it("the Sync button disables itself right after a real, successful sync, preventing an accidental re-click", async () => {
    vi.spyOn(api, "syncOrderToPortfolio").mockResolvedValue({
      ticker: "AAPL", shares: 1, cost_basis_per_share: 150.25, position_closed: false,
    });
    render(<BrokeragePage />);
    await waitFor(() => screen.getByText("AAPL"));

    fireEvent.click(screen.getByText("Sync to portfolio"));

    await waitFor(() => screen.getByText("Synced"));
    expect(screen.getByText("Synced")).toBeDisabled();
    expect(screen.queryByText("Sync to portfolio")).not.toBeInTheDocument();
  });

  it("bulk-syncing selected orders reports a real, honest per-order summary", async () => {
    vi.spyOn(api, "getOrderHistory").mockResolvedValue({
      entries: [SAMPLE_HISTORY_ENTRY, { ...SAMPLE_HISTORY_ENTRY, order_id: "ORD-2", ticker: "MSFT" }],
    });
    const bulkSpy = vi.spyOn(api, "syncMultipleOrdersToPortfolio").mockResolvedValue({
      outcomes: [
        { order_id: "ORD-1", succeeded: true, ticker: "AAPL", shares: 1, cost_basis_per_share: 150.25, position_closed: false, error: null },
        { order_id: "ORD-2", succeeded: false, ticker: null, shares: null, cost_basis_per_share: null, position_closed: false, error: "sold more than held" },
      ],
    });
    render(<BrokeragePage />);
    await waitFor(() => screen.getByText("AAPL"));

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);
    fireEvent.click(screen.getByText("Sync 2 selected to portfolio"));

    await waitFor(() => expect(bulkSpy).toHaveBeenCalledWith(["ORD-1", "ORD-2"]));
    await waitFor(() => screen.getByText("Synced 1 of 2 — 1 failed (see individual results below)."));
    expect(screen.getByText("sold more than held")).toBeInTheDocument();
  });

  it("the bulk sync button is disabled until at least one order is selected", async () => {
    render(<BrokeragePage />);
    await waitFor(() => screen.getByText("AAPL"));

    expect(screen.getByText("Sync 0 selected to portfolio")).toBeDisabled();
  });
});
