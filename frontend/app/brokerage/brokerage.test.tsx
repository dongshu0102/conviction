// Tests for the Real Brokerage Trading page. Given real money is at
// stake, special focus on the multi-layer confirmation safeguards:
// preview never places a real order, the "type the ticker" gate, and
// the brokerage's own separate warning-confirmation flow.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import BrokeragePage from "./page";
import { api, PlaceOrderResponse, BrokerageAccountSummary } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/brokerage",
  useRouter: () => ({ push: pushMock }),
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
