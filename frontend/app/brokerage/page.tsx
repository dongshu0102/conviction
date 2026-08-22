"use client";

// Real brokerage trading — REAL MONEY IS AT STAKE once an order is
// actually confirmed and submitted. This page deliberately layers
// multiple, genuine confirmation steps on top of the backend's own,
// programmatic safeguard (PlaceOrderUseCase never even calls the
// provider without confirm=true):
//
// 1. The initial "Preview order" button calls the API with
//    confirm=false — this only ever returns a local preview, no real
//    order is placed, matching the backend's own default.
// 2. Only after a real preview is shown does a second, visually
//    distinct "Confirm and place real order" control appear.
// 3. That control requires the user to type the exact ticker symbol
//    again before it's enabled — a real, deliberate extra step, not
//    just a second click, so a real order can't be placed by
//    accidentally double-clicking or misreading a screen.
// 4. If the brokerage itself returns its own, separate warning
//    (status="needs_confirmation"), that warning is shown in full and
//    requires yet another, explicit, separate confirmation before
//    confirm_brokerage_order is ever called — never confirmed
//    automatically.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import {
  api, getApiKey, PlaceOrderResponse, OrderResult,
  BrokerageAccountSummary, BrokeragePosition, OrderHistoryEntry,
} from "@/lib/api";

function fmtUsd(v: number): string {
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

type Step = "form" | "previewed" | "placed";

export default function BrokeragePage() {
  const router = useRouter();

  const [account, setAccount] = useState<BrokerageAccountSummary | null>(null);
  const [positions, setPositions] = useState<BrokeragePosition[] | null>(null);
  const [accountError, setAccountError] = useState<string | null>(null);

  const [history, setHistory] = useState<OrderHistoryEntry[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [rowActionOrderId, setRowActionOrderId] = useState<string | null>(null); // which row's own button is loading
  const [rowActionKind, setRowActionKind] = useState<"status" | "cancel" | "sync" | null>(null); // which specific action
  const [rowMessages, setRowMessages] = useState<Record<string, string>>({}); // per-order, honest result text
  const [rowMessageIsError, setRowMessageIsError] = useState<Record<string, boolean>>({}); // for real color-coding, not string-guessing
  const [syncedOrderIds, setSyncedOrderIds] = useState<Set<string>>(new Set()); // extra, client-side guard on top of the real, server-side one
  const [confirmingCancelOrderId, setConfirmingCancelOrderId] = useState<string | null>(null);
  const [selectedOrderIds, setSelectedOrderIds] = useState<Set<string>>(new Set());
  const [bulkSyncing, setBulkSyncing] = useState(false);
  const [bulkSyncMessage, setBulkSyncMessage] = useState<string | null>(null);

  const [ticker, setTicker] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [quantity, setQuantity] = useState("");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState("");

  const [step, setStep] = useState<Step>("form");
  const [preview, setPreview] = useState<PlaceOrderResponse | null>(null);
  const [confirmTypedTicker, setConfirmTypedTicker] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warningApproved, setWarningApproved] = useState(false);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    api.getBrokerageAccountSummary().then(setAccount).catch((err) => {
      setAccountError(err instanceof Error ? err.message : "Couldn't load account summary");
    });
    api.getBrokeragePositions().then((r) => setPositions(r.positions)).catch(() => {
      // Positions failing to load isn't fatal to the rest of the page — the account
      // summary error above already surfaces a configuration problem if there is one.
    });
    loadHistory();
  }, [router]);

  async function loadHistory() {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const r = await api.getOrderHistory();
      setHistory(r.entries);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : "Couldn't load order history");
    } finally {
      setHistoryLoading(false);
    }
  }

  function resetOrderFlow() {
    setStep("form");
    setPreview(null);
    setConfirmTypedTicker("");
    setWarningApproved(false);
    setError(null);
  }

  async function handlePreview(e: React.FormEvent) {
    e.preventDefault();
    const t = ticker.trim().toUpperCase();
    const qty = parseFloat(quantity);
    if (!t || !qty || qty <= 0) return;
    if (orderType === "limit" && !limitPrice) return;

    setLoading(true);
    setError(null);
    try {
      const result = await api.placeOrder({
        ticker: t, side, quantity: qty, order_type: orderType,
        limit_price: orderType === "limit" ? parseFloat(limitPrice) : undefined,
        confirm: false,
      });
      setPreview(result);
      setStep("previewed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't preview this order");
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirmAndPlace() {
    const t = ticker.trim().toUpperCase();
    const qty = parseFloat(quantity);

    setLoading(true);
    setError(null);
    try {
      const result = await api.placeOrder({
        ticker: t, side, quantity: qty, order_type: orderType,
        limit_price: orderType === "limit" ? parseFloat(limitPrice) : undefined,
        confirm: true,
      });
      setPreview(result);
      if (result.order_result?.status === "submitted") {
        setStep("placed");
      }
      // status "needs_confirmation" or "rejected" stays on the
      // "previewed" step so the real, distinct warning UI below can render.
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't place this order");
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirmBrokerageWarning() {
    if (!preview?.order_result?.reply_id) return;
    setLoading(true);
    setError(null);
    try {
      const result: OrderResult = await api.confirmBrokerageOrder(preview.order_result.reply_id);
      setPreview({ ...preview, order_result: result });
      if (result.status === "submitted") {
        setStep("placed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't confirm this order");
    } finally {
      setLoading(false);
    }
  }

  async function handleCheckStatus(orderId: string) {
    setRowActionOrderId(orderId);
    setRowActionKind("status");
    try {
      const status = await api.getOrderStatus(orderId);
      const priceText = status.filled_avg_price !== null ? ` @ $${status.filled_avg_price.toFixed(2)}` : "";
      setRowMessages((prev) => ({
        ...prev,
        [orderId]: `Status: ${status.status} — ${status.filled_quantity} filled${priceText}`,
      }));
      setRowMessageIsError((prev) => ({ ...prev, [orderId]: false }));
    } catch (err) {
      setRowMessages((prev) => ({
        ...prev, [orderId]: err instanceof Error ? err.message : "Couldn't check status",
      }));
      setRowMessageIsError((prev) => ({ ...prev, [orderId]: true }));
    } finally {
      setRowActionOrderId(null);
      setRowActionKind(null);
    }
  }

  function handleRequestCancel(orderId: string) {
    setConfirmingCancelOrderId(orderId);
  }

  function handleBackOutOfCancel() {
    setConfirmingCancelOrderId(null);
  }

  async function handleCancelOrder(orderId: string) {
    setConfirmingCancelOrderId(null);
    setRowActionOrderId(orderId);
    setRowActionKind("cancel");
    try {
      const result = await api.cancelOrder(orderId);
      if (!result.success) {
        setRowMessages((prev) => ({
          ...prev, [orderId]: result.reason || "Could not cancel — not cancelable.",
        }));
        setRowMessageIsError((prev) => ({ ...prev, [orderId]: true }));
        return;
      }
      // A real 204/success from the brokerage means the cancel REQUEST
      // was accepted -- it does not, by itself, guarantee the order
      // has already, actually finished transitioning to "canceled" at
      // this exact moment (a real, known race: the order can genuinely
      // fill in the brief window right around when a cancel is sent).
      // Re-fetch the order's own, real, live status rather than
      // trusting success:true as the final word on its actual state.
      const status = await api.getOrderStatus(orderId);
      const genuinelyCanceled = status.status === "canceled";
      setRowMessages((prev) => ({
        ...prev,
        [orderId]: genuinelyCanceled
          ? "Canceled."
          : `Cancel request accepted, but the order's real, current status is "${status.status}" -- it may have already filled before the cancel reached the brokerage.`,
      }));
      setRowMessageIsError((prev) => ({ ...prev, [orderId]: !genuinelyCanceled }));
      await loadHistory(); // reflect the real, current status in the table either way
    } catch (err) {
      setRowMessages((prev) => ({
        ...prev, [orderId]: err instanceof Error ? err.message : "Couldn't cancel this order",
      }));
      setRowMessageIsError((prev) => ({ ...prev, [orderId]: true }));
    } finally {
      setRowActionOrderId(null);
      setRowActionKind(null);
    }
  }

  async function handleSyncOrder(entry: OrderHistoryEntry) {
    setRowActionOrderId(entry.order_id);
    setRowActionKind("sync");
    try {
      const result = await api.syncOrderToPortfolio(entry.order_id, entry.ticker, entry.side);
      setRowMessages((prev) => ({
        ...prev,
        [entry.order_id]: result.position_closed
          ? `Synced — position in ${entry.ticker} fully closed.`
          : `Synced — now ${result.shares} sh of ${result.ticker} @ ${fmtUsd(result.cost_basis_per_share ?? 0)} avg.`,
      }));
      setRowMessageIsError((prev) => ({ ...prev, [entry.order_id]: false }));
      // A real, extra, client-side guard layered on top of the actual,
      // authoritative server-side one (the synced_orders table) --
      // this alone would never be sufficient by itself (a page refresh
      // would lose it), but it does stop an accidental second click
      // in this same session before it even reaches the network.
      setSyncedOrderIds((prev) => new Set(prev).add(entry.order_id));
    } catch (err) {
      setRowMessages((prev) => ({
        ...prev, [entry.order_id]: err instanceof Error ? err.message : "Couldn't sync this order",
      }));
      setRowMessageIsError((prev) => ({ ...prev, [entry.order_id]: true }));
    } finally {
      setRowActionOrderId(null);
      setRowActionKind(null);
    }
  }

  function toggleSelected(orderId: string) {
    setSelectedOrderIds((prev) => {
      const next = new Set(prev);
      if (next.has(orderId)) next.delete(orderId); else next.add(orderId);
      return next;
    });
  }

  async function handleBulkSync() {
    if (selectedOrderIds.size === 0) return;
    setBulkSyncing(true);
    setBulkSyncMessage(null);
    try {
      const result = await api.syncMultipleOrdersToPortfolio(Array.from(selectedOrderIds));
      const succeeded = result.outcomes.filter((o) => o.succeeded).length;
      const failed = result.outcomes.length - succeeded;
      setBulkSyncMessage(
        failed === 0
          ? `Synced all ${succeeded} selected order(s).`
          : `Synced ${succeeded} of ${result.outcomes.length} — ${failed} failed (see individual results below).`
      );
      const newRowMessages: Record<string, string> = {};
      const newRowMessageIsError: Record<string, boolean> = {};
      const newlySynced = new Set<string>();
      for (const o of result.outcomes) {
        newRowMessages[o.order_id] = o.succeeded
          ? (o.position_closed ? `Synced — position in ${o.ticker} fully closed.` : `Synced — now ${o.shares} sh of ${o.ticker}.`)
          : (o.error || "Sync failed.");
        newRowMessageIsError[o.order_id] = !o.succeeded;
        if (o.succeeded) newlySynced.add(o.order_id);
      }
      setRowMessages((prev) => ({ ...prev, ...newRowMessages }));
      setRowMessageIsError((prev) => ({ ...prev, ...newRowMessageIsError }));
      setSyncedOrderIds((prev) => new Set([...prev, ...newlySynced]));
      setSelectedOrderIds(new Set());
    } catch (err) {
      setBulkSyncMessage(err instanceof Error ? err.message : "Couldn't sync the selected orders");
    } finally {
      setBulkSyncing(false);
    }
  }

  const orderResult = preview?.order_result;
  // Canceled orders are filtered from the default view -- this is a
  // real, live query against the brokerage's own order history, not
  // this app's own data, so "filtering" here never deletes anything
  // real; it only changes what's shown. Scoped specifically to
  // "canceled" (not e.g. "rejected") -- what was actually asked for.
  const visibleHistory = history?.filter((entry) => entry.status !== "canceled") ?? null;
  const tickerMatches = confirmTypedTicker.trim().toUpperCase() === ticker.trim().toUpperCase();

  return (
    <AppShell>
      <main style={{ maxWidth: 720, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Trading</p>
        <h1 style={{ margin: "0.3rem 0 0.75rem" }}>Real brokerage trading</h1>
        <p style={{ color: "var(--loss)", fontWeight: 600, marginBottom: "0.5rem", fontSize: "0.9rem" }}>
          Real money is at stake here. Nothing is ever submitted to the brokerage until you
          explicitly confirm the exact order shown below.
        </p>

        {account && (
          <div className="card" style={{ marginBottom: "1.25rem" }}>
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
              {`Account ${account.account_id}`}
            </p>
            <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
              <span className="num">{`Cash: ${fmtUsd(account.cash)}`}</span>
              <span className="num">{`Buying power: ${fmtUsd(account.buying_power)}`}</span>
              <span className="num">{`Equity: ${fmtUsd(account.equity)}`}</span>
            </div>
          </div>
        )}
        {accountError && (
          <p className="num loss" style={{ fontSize: "0.85rem", marginBottom: "1.25rem" }}>{accountError}</p>
        )}

        {positions && positions.length > 0 && (
          <div className="card" style={{ marginBottom: "1.25rem" }}>
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>Current positions</p>
            {positions.map((p, i) => (
              <div key={`${p.ticker}-${i}`} style={{ display: "flex", justifyContent: "space-between", padding: "0.4rem 0" }}>
                <span className="num">{p.ticker}</span>
                <span className="num">{`${p.quantity} sh @ ${fmtUsd(p.average_cost)} avg`}</span>
              </div>
            ))}
          </div>
        )}

        <div className="card" style={{ marginBottom: "1.25rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
            <p className="eyebrow" style={{ fontSize: "0.68rem", margin: 0 }}>Order history</p>
            <button type="button" onClick={loadHistory} disabled={historyLoading} style={{ fontSize: "0.8rem" }}>
              {historyLoading ? "Loading…" : "Refresh"}
            </button>
          </div>

          {historyError && <p className="num loss" style={{ fontSize: "0.85rem" }}>{historyError}</p>}
          {visibleHistory && visibleHistory.length === 0 && (
            <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>
              {history && history.length > 0
                ? "No orders to show (canceled orders are hidden by default)."
                : "No orders yet."}
            </p>
          )}

          {visibleHistory && visibleHistory.length > 0 && (
            <>
              {visibleHistory.map((entry, i) => {
                const isRowBusy = rowActionOrderId === entry.order_id;
                const isConfirmingCancel = confirmingCancelOrderId === entry.order_id;
                const alreadySynced = syncedOrderIds.has(entry.order_id);
                const statusColor =
                  entry.status === "filled" ? "var(--gain)"
                  : (entry.status === "canceled" || entry.status === "rejected") ? "var(--text-soft)"
                  : "var(--accent)";
                return (
                  <div
                    key={entry.order_id}
                    style={{
                      borderTop: i > 0 ? "1px solid var(--rule)" : "none",
                      padding: "0.75rem 0.25rem", borderRadius: "4px",
                      background: isConfirmingCancel ? "rgba(220, 38, 38, 0.06)" : "transparent",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                      <label style={{ display: "flex", alignItems: "center", gap: "0.6rem" }} title="Select for bulk sync">
                        <input
                          type="checkbox" checked={selectedOrderIds.has(entry.order_id)}
                          onChange={() => toggleSelected(entry.order_id)}
                        />
                        <span className="num" style={{ fontWeight: 700 }}>{entry.ticker}</span>
                        <span className="num" style={{ fontSize: "0.82rem", color: "var(--text-soft)" }}>
                          {`${entry.side} ${entry.quantity} · ${entry.order_type}`}
                        </span>
                        <span
                          className="num"
                          style={{
                            fontSize: "0.72rem", color: statusColor, border: `1px solid ${statusColor}`,
                            borderRadius: "3px", padding: "0.05rem 0.4rem",
                          }}
                        >
                          {entry.status}
                        </span>
                      </label>

                      {isConfirmingCancel ? (
                        <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                          <span className="num loss" style={{ fontSize: "0.78rem" }}>Cancel this order?</span>
                          <button
                            type="button" onClick={() => handleCancelOrder(entry.order_id)}
                            style={{ fontSize: "0.78rem", background: "var(--loss)" }}
                          >
                            Confirm cancel
                          </button>
                          <button type="button" onClick={handleBackOutOfCancel} style={{ fontSize: "0.78rem" }}>
                            Never mind
                          </button>
                        </div>
                      ) : (
                        <div style={{ display: "flex", gap: "0.4rem" }}>
                          <button
                            type="button" onClick={() => handleCheckStatus(entry.order_id)}
                            disabled={isRowBusy} title="Fetch this order's real, current status from the brokerage"
                            style={{ fontSize: "0.78rem" }}
                          >
                            {isRowBusy && rowActionKind === "status" ? "Checking…" : "Check status"}
                          </button>
                          <button
                            type="button" onClick={() => handleRequestCancel(entry.order_id)}
                            disabled={isRowBusy} title="Attempt to cancel this order at the brokerage"
                            style={{ fontSize: "0.78rem" }}
                          >
                            {isRowBusy && rowActionKind === "cancel" ? "Canceling…" : "Cancel"}
                          </button>
                          <button
                            type="button" onClick={() => handleSyncOrder(entry)}
                            disabled={isRowBusy || entry.status !== "filled" || alreadySynced}
                            title={
                              alreadySynced ? "Already synced to a portfolio this session"
                              : entry.status !== "filled" ? "Only a genuinely filled order can be synced"
                              : "Add this fill to its dedicated portfolio (accumulates shares correctly)"
                            }
                            style={{ fontSize: "0.78rem" }}
                          >
                            {isRowBusy && rowActionKind === "sync" ? "Syncing…" : alreadySynced ? "Synced" : "Sync to portfolio"}
                          </button>
                        </div>
                      )}
                    </div>
                    {rowMessages[entry.order_id] && (
                      <p
                        className={`num${rowMessageIsError[entry.order_id] ? " loss" : ""}`}
                        style={{
                          fontSize: "0.78rem", marginTop: "0.4rem",
                          color: rowMessageIsError[entry.order_id] ? undefined : "var(--gain)",
                        }}
                      >
                        {rowMessages[entry.order_id]}
                      </p>
                    )}
                  </div>
                );
              })}

              <div style={{ marginTop: "0.75rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <button
                  type="button" onClick={handleBulkSync}
                  disabled={bulkSyncing || selectedOrderIds.size === 0}
                  title="Sync every checked order into its dedicated, per-broker portfolio in one request"
                  className="btn-primary" style={{ fontSize: "0.85rem" }}
                >
                  {bulkSyncing ? "Syncing…" : `Sync ${selectedOrderIds.size} selected to portfolio`}
                </button>
                {bulkSyncMessage && (
                  <span className="num" style={{ fontSize: "0.82rem", color: "var(--text-soft)" }}>{bulkSyncMessage}</span>
                )}
              </div>
            </>
          )}
        </div>

        {step === "form" && (
          <form onSubmit={handlePreview} className="card" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <input
              type="text" placeholder="Ticker, e.g. AAPL" value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              style={{ padding: "0.6rem 0.9rem", fontSize: "0.95rem" }}
            />
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <select value={side} onChange={(e) => setSide(e.target.value as "buy" | "sell")} style={{ flex: 1, padding: "0.6rem" }}>
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
              <input
                type="number" placeholder="Shares" value={quantity} min="1"
                onChange={(e) => setQuantity(e.target.value)}
                style={{ flex: 1, padding: "0.6rem 0.9rem" }}
              />
            </div>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <select value={orderType} onChange={(e) => setOrderType(e.target.value as "market" | "limit")} style={{ flex: 1, padding: "0.6rem" }}>
                <option value="market">Market</option>
                <option value="limit">Limit</option>
              </select>
              {orderType === "limit" && (
                <input
                  type="number" placeholder="Limit price" value={limitPrice} step="0.01"
                  onChange={(e) => setLimitPrice(e.target.value)}
                  style={{ flex: 1, padding: "0.6rem 0.9rem" }}
                />
              )}
            </div>
            <button type="submit" className="btn-primary" disabled={loading || !ticker.trim() || !quantity}>
              {loading ? "Loading…" : "Preview order"}
            </button>
          </form>
        )}

        {error && (
          <p className="num loss" style={{ fontSize: "0.85rem", margin: "1rem 0" }}>{error}</p>
        )}

        {step === "previewed" && preview && (
          <div className="card" style={{ marginTop: "1rem" }}>
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
              {preview.confirmed ? "Brokerage response" : "Order preview — nothing placed yet"}
            </p>
            <p style={{ margin: "0 0 0.5rem" }}>
              {`${side === "buy" ? "Buy" : "Sell"} ${quantity} shares of ${ticker.toUpperCase()} — ${orderType}${orderType === "limit" ? ` @ ${fmtUsd(parseFloat(limitPrice))}` : ""}`}
            </p>

            {!preview.confirmed && (
              <>
                <p style={{ color: "var(--text-soft)", fontSize: "0.85rem", marginBottom: "1rem" }}>
                  {`This has NOT been placed. To confirm, type the ticker (${ticker.toUpperCase()}) below, then submit.`}
                </p>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="text" placeholder={`Type "${ticker.toUpperCase()}" to confirm`}
                    value={confirmTypedTicker} onChange={(e) => setConfirmTypedTicker(e.target.value)}
                    style={{ flex: 1, padding: "0.6rem 0.9rem" }}
                  />
                  <button
                    type="button" className="btn-primary" disabled={loading || !tickerMatches}
                    onClick={handleConfirmAndPlace}
                    style={{ background: "var(--loss)" }}
                  >
                    {loading ? "Placing…" : "Confirm and place real order"}
                  </button>
                </div>
                <button type="button" onClick={resetOrderFlow} style={{ marginTop: "0.75rem", fontSize: "0.8rem" }}>
                  Cancel
                </button>
              </>
            )}

            {preview.confirmed && orderResult?.status === "needs_confirmation" && (
              <div style={{ marginTop: "0.75rem" }}>
                <p className="num" style={{ color: "var(--accent)", fontWeight: 700, fontSize: "0.85rem" }}>
                  The brokerage has a warning about this order — it has NOT been placed:
                </p>
                <ul style={{ margin: "0.5rem 0", paddingLeft: "1.25rem" }}>
                  {orderResult.warning_messages.map((m, i) => (
                    <li key={i} style={{ fontSize: "0.85rem", marginBottom: "0.25rem" }}>{m}</li>
                  ))}
                </ul>
                <label style={{ display: "flex", gap: "0.5rem", alignItems: "center", fontSize: "0.85rem", margin: "0.75rem 0" }}>
                  <input type="checkbox" checked={warningApproved} onChange={(e) => setWarningApproved(e.target.checked)} />
                  I have read this warning and want to proceed anyway
                </label>
                <button
                  type="button" className="btn-primary" disabled={loading || !warningApproved}
                  onClick={handleConfirmBrokerageWarning} style={{ background: "var(--loss)" }}
                >
                  {loading ? "Confirming…" : "Confirm warning and place real order"}
                </button>
                <button type="button" onClick={resetOrderFlow} style={{ marginTop: "0.5rem", marginLeft: "0.5rem", fontSize: "0.8rem" }}>
                  Cancel this order
                </button>
              </div>
            )}

            {preview.confirmed && orderResult?.status === "rejected" && (
              <div>
                <p className="num loss" style={{ fontSize: "0.85rem" }}>
                  {`Rejected by the brokerage: ${orderResult.rejection_reason}`}
                </p>
                <button type="button" onClick={resetOrderFlow} style={{ marginTop: "0.75rem" }}>
                  Start over
                </button>
              </div>
            )}
          </div>
        )}

        {step === "placed" && orderResult && (
          <div className="card" style={{ marginTop: "1rem" }}>
            <p className="num" style={{ color: "var(--gain)", fontWeight: 700 }}>
              {`Order submitted — brokerage order id ${orderResult.order_id}`}
            </p>
            <button type="button" onClick={resetOrderFlow} style={{ marginTop: "0.75rem" }}>
              Place another order
            </button>
          </div>
        )}
      </main>
    </AppShell>
  );
}
