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
  BrokerageAccountSummary, BrokeragePosition,
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
  }, [router]);

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

  const orderResult = preview?.order_result;
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
