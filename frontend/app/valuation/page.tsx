"use client";

// Valuation — 5 genuinely distinct models under one ticker input.
// Multiples was already computed by the backend but never surfaced on
// the web at all; DCF, reverse DCF, IRR, and Comps are new. Each
// section is click-to-compute, not auto-loaded, since every one of
// these is a real financial-data fetch (and Comps fans out to
// multiple peers) — matching the same pattern as Growth Hunter's
// tracked-candidate checks and the portfolio Greeks/hedging sections.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import {
  api, getApiKey, ApiError,
  ValuationSnapshot, DcfResponse, ReverseDcfResponse, IrrResponse, CompsResponse, CompsMetric,
  TreasuryRates,
} from "@/lib/api";

function usd(v: number | null): string {
  if (v === null) return "—";
  return v.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
}

function pct(v: number | null): string {
  if (v === null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function mult(v: number | null): string {
  if (v === null) return "—";
  return `${v.toFixed(1)}x`;
}

export default function ValuationPage() {
  const router = useRouter();
  const [ticker, setTicker] = useState("");
  const [globalError, setGlobalError] = useState<string | null>(null);

  // Treasury yields
  const [treasury, setTreasury] = useState<TreasuryRates | null>(null);
  const [treasuryLoading, setTreasuryLoading] = useState(false);
  const [treasuryError, setTreasuryError] = useState<string | null>(null);

  // Multiples
  const [multiples, setMultiples] = useState<ValuationSnapshot | null>(null);
  const [multiplesLoading, setMultiplesLoading] = useState(false);
  const [multiplesError, setMultiplesError] = useState<string | null>(null);

  // DCF
  const [dcfGrowthRate, setDcfGrowthRate] = useState("");
  const [dcfDiscountRate, setDcfDiscountRate] = useState("0.10");
  const [dcfTerminalGrowth, setDcfTerminalGrowth] = useState("0.025");
  const [dcfYears, setDcfYears] = useState("5");
  const [dcf, setDcf] = useState<DcfResponse | null>(null);
  const [dcfLoading, setDcfLoading] = useState(false);
  const [dcfError, setDcfError] = useState<string | null>(null);

  // Reverse DCF
  const [reverseDcf, setReverseDcf] = useState<ReverseDcfResponse | null>(null);
  const [reverseDcfLoading, setReverseDcfLoading] = useState(false);
  const [reverseDcfError, setReverseDcfError] = useState<string | null>(null);

  // IRR
  const [irrEntryPrice, setIrrEntryPrice] = useState("");
  const [irrExitPrice, setIrrExitPrice] = useState("");
  const [irrYears, setIrrYears] = useState("5");
  const [irrDividend, setIrrDividend] = useState("0");
  const [irr, setIrr] = useState<IrrResponse | null>(null);
  const [irrLoading, setIrrLoading] = useState(false);
  const [irrError, setIrrError] = useState<string | null>(null);

  // Comps
  const [compsMetric, setCompsMetric] = useState<CompsMetric>("pe");
  const [comps, setComps] = useState<CompsResponse | null>(null);
  const [compsLoading, setCompsLoading] = useState(false);
  const [compsError, setCompsError] = useState<string | null>(null);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    handleTreasury();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  function currentTicker(): string | null {
    const t = ticker.trim().toUpperCase();
    if (!t) {
      setGlobalError("Enter a ticker first.");
      return null;
    }
    setGlobalError(null);
    return t;
  }

  async function handleMultiples() {
    const t = currentTicker();
    if (!t) return;
    setMultiplesLoading(true);
    setMultiplesError(null);
    try {
      setMultiples(await api.getValuation(t));
    } catch (err) {
      setMultiplesError(err instanceof Error ? err.message : "Couldn't load valuation multiples");
    } finally {
      setMultiplesLoading(false);
    }
  }

  async function handleTreasury() {
    setTreasuryLoading(true);
    setTreasuryError(null);
    try {
      setTreasury(await api.getTreasuryRates());
    } catch (err) {
      setTreasuryError(err instanceof Error ? err.message : "Couldn't load Treasury rates");
    } finally {
      setTreasuryLoading(false);
    }
  }

  function useAsDiscountRate() {
    if (treasury?.suggested_discount_rate != null) {
      setDcfDiscountRate(String(treasury.suggested_discount_rate));
    }
  }

  async function handleDcf() {
    const t = currentTicker();
    if (!t) return;
    setDcfLoading(true);
    setDcfError(null);
    try {
      setDcf(
        await api.getDcf(t, {
          growth_rate: dcfGrowthRate ? parseFloat(dcfGrowthRate) : undefined,
          discount_rate: parseFloat(dcfDiscountRate),
          terminal_growth_rate: parseFloat(dcfTerminalGrowth),
          years: parseInt(dcfYears, 10),
        })
      );
    } catch (err) {
      setDcfError(err instanceof Error ? err.message : "Couldn't compute DCF");
    } finally {
      setDcfLoading(false);
    }
  }

  async function handleReverseDcf() {
    const t = currentTicker();
    if (!t) return;
    setReverseDcfLoading(true);
    setReverseDcfError(null);
    try {
      setReverseDcf(await api.getReverseDcf(t));
    } catch (err) {
      setReverseDcfError(err instanceof Error ? err.message : "Couldn't compute reverse DCF");
    } finally {
      setReverseDcfLoading(false);
    }
  }

  async function handleIrr() {
    const t = currentTicker();
    if (!t) return;
    const exitPrice = parseFloat(irrExitPrice);
    const years = parseInt(irrYears, 10);
    if (!exitPrice || exitPrice <= 0 || !years || years < 1) {
      setIrrError("Enter a positive exit price and at least 1 year.");
      return;
    }
    setIrrLoading(true);
    setIrrError(null);
    try {
      setIrr(
        await api.getIrr(t, exitPrice, years, {
          entry_price: irrEntryPrice ? parseFloat(irrEntryPrice) : undefined,
          annual_dividend_per_share: irrDividend ? parseFloat(irrDividend) : 0,
        })
      );
    } catch (err) {
      setIrrError(err instanceof Error ? err.message : "Couldn't compute IRR");
    } finally {
      setIrrLoading(false);
    }
  }

  async function handleComps() {
    const t = currentTicker();
    if (!t) return;
    setCompsLoading(true);
    setCompsError(null);
    try {
      setComps(await api.getComps(t, compsMetric));
    } catch (err) {
      setCompsError(err instanceof Error ? err.message : "Couldn't compute comps");
    } finally {
      setCompsLoading(false);
    }
  }

  return (
    <AppShell>
      <main style={{ maxWidth: 760, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Valuation</p>
        <h1 style={{ margin: "0.3rem 0 0.75rem" }}>Valuation</h1>
        <p style={{ color: "var(--text-soft)", lineHeight: 1.6, marginBottom: "1.5rem", fontSize: "0.95rem" }}>
          Four genuinely different ways to ask what a company is worth — a DCF builds value up
          from projected cash flows, a reverse DCF asks what growth rate the current price
          already assumes, IRR is a return calculator for a specific buy-hold-sell scenario, and
          comps applies real peer multiples to the target's own financials. Every assumption is
          shown, never hidden — small changes in growth or discount rate can swing a DCF
          substantially, which is a real property of the model, not a flaw in this tool.
        </p>

        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
          <input
            type="text"
            placeholder="Ticker, e.g. NVDA"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            className="num"
            style={{ flex: 1, padding: "0.6rem 0.9rem", fontSize: "0.95rem", textTransform: "uppercase" }}
          />
        </div>
        {globalError && (
          <p className="num loss" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>{globalError}</p>
        )}

        <section style={{ marginTop: "2rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Multiples</p>
            <button className="btn-primary" onClick={handleMultiples} disabled={multiplesLoading} style={{ padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}>
              {multiplesLoading ? "Loading…" : "Compute"}
            </button>
          </div>
          <div className="card">
            {multiplesError && <p className="num loss" style={{ margin: 0, fontSize: "0.85rem" }}>{multiplesError}</p>}
            {!multiples && !multiplesError && (
              <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
                Live price against most recent annual fundamentals: P/E, P/S, P/B, P/FCF, EV/EBITDA.
              </p>
            )}
            {multiples && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(90px, 1fr))", gap: "1rem" }}>
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>P/E</p>
                  <p className="num" style={{ fontSize: "1.05rem", margin: "0.2rem 0 0" }}>{mult(multiples.price_to_earnings)}</p>
                </div>
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>P/S</p>
                  <p className="num" style={{ fontSize: "1.05rem", margin: "0.2rem 0 0" }}>{mult(multiples.price_to_sales)}</p>
                </div>
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>P/B</p>
                  <p className="num" style={{ fontSize: "1.05rem", margin: "0.2rem 0 0" }}>{mult(multiples.price_to_book)}</p>
                </div>
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>P/FCF</p>
                  <p className="num" style={{ fontSize: "1.05rem", margin: "0.2rem 0 0" }}>{mult(multiples.price_to_free_cash_flow)}</p>
                </div>
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>EV/EBITDA</p>
                  <p className="num" style={{ fontSize: "1.05rem", margin: "0.2rem 0 0" }}>{mult(multiples.ev_to_ebitda)}</p>
                </div>
              </div>
            )}
          </div>
        </section>

        <section style={{ marginTop: "2rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Treasury Yields</p>
            <button className="btn-primary" onClick={handleTreasury} disabled={treasuryLoading} style={{ padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}>
              {treasuryLoading ? "…" : "Refresh"}
            </button>
          </div>
          <div className="card">
            {treasuryError && <p className="num loss" style={{ margin: 0, fontSize: "0.85rem" }}>{treasuryError}</p>}
            {!treasury && !treasuryError && !treasuryLoading && (
              <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
                The real, current Treasury yield curve — the market&apos;s own live proxy for the
                risk-free rate, and the most direct macro signal this platform has.
              </p>
            )}
            {treasury && (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(70px, 1fr))", gap: "0.85rem", marginBottom: "1rem" }}>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.6rem" }}>1mo</p>
                    <p className="num" style={{ fontSize: "0.95rem", margin: "0.15rem 0 0" }}>{pct(treasury.month1)}</p>
                  </div>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.6rem" }}>3mo</p>
                    <p className="num" style={{ fontSize: "0.95rem", margin: "0.15rem 0 0" }}>{pct(treasury.month3)}</p>
                  </div>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.6rem" }}>1yr</p>
                    <p className="num" style={{ fontSize: "0.95rem", margin: "0.15rem 0 0" }}>{pct(treasury.year1)}</p>
                  </div>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.6rem" }}>2yr</p>
                    <p className="num" style={{ fontSize: "0.95rem", margin: "0.15rem 0 0" }}>{pct(treasury.year2)}</p>
                  </div>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.6rem" }}>5yr</p>
                    <p className="num" style={{ fontSize: "0.95rem", margin: "0.15rem 0 0" }}>{pct(treasury.year5)}</p>
                  </div>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.6rem" }}>10yr</p>
                    <p className="num" style={{ fontSize: "0.95rem", margin: "0.15rem 0 0" }}>{pct(treasury.year10)}</p>
                  </div>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.6rem" }}>30yr</p>
                    <p className="num" style={{ fontSize: "0.95rem", margin: "0.15rem 0 0" }}>{pct(treasury.year30)}</p>
                  </div>
                </div>
                {treasury.suggested_discount_rate !== null && (
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <p className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)", margin: 0 }}>
                      Suggested DCF discount rate (10yr + 5% equity risk premium):{" "}
                      <span style={{ color: "var(--text)" }}>{pct(treasury.suggested_discount_rate)}</span>
                    </p>
                    <button
                      onClick={useAsDiscountRate}
                      style={{ background: "none", border: "none", color: "var(--accent)", fontSize: "0.78rem", cursor: "pointer", whiteSpace: "nowrap" }}
                    >
                      Use in DCF below
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        <section style={{ marginTop: "2rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>Discounted Cash Flow</p>
          <div className="card">
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1rem" }}>
              <input
                type="number" placeholder="Growth rate (blank = historical CAGR)"
                value={dcfGrowthRate} onChange={(e) => setDcfGrowthRate(e.target.value)}
                style={{ flex: "1 1 180px", fontSize: "0.85rem", padding: "0.5rem 0.7rem" }}
              />
              <input
                type="number" placeholder="Discount rate" value={dcfDiscountRate}
                onChange={(e) => setDcfDiscountRate(e.target.value)}
                style={{ flex: "1 1 110px", fontSize: "0.85rem", padding: "0.5rem 0.7rem" }}
              />
              <input
                type="number" placeholder="Terminal growth" value={dcfTerminalGrowth}
                onChange={(e) => setDcfTerminalGrowth(e.target.value)}
                style={{ flex: "1 1 110px", fontSize: "0.85rem", padding: "0.5rem 0.7rem" }}
              />
              <input
                type="number" placeholder="Years" value={dcfYears}
                onChange={(e) => setDcfYears(e.target.value)}
                style={{ flex: "1 1 70px", fontSize: "0.85rem", padding: "0.5rem 0.7rem" }}
              />
              <button className="btn-primary" onClick={handleDcf} disabled={dcfLoading} style={{ padding: "0.5rem 1rem", fontSize: "0.85rem" }}>
                {dcfLoading ? "…" : "Compute"}
              </button>
            </div>
            {dcfError && <p className="num loss" style={{ margin: 0, fontSize: "0.85rem" }}>{dcfError}</p>}
            {!dcf && !dcfError && (
              <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
                Projects free cash flow forward, discounts it back to present value, adds a
                terminal value. Growth rate defaults to the company&apos;s own historical revenue
                CAGR if left blank — never an arbitrary constant.
              </p>
            )}
            {dcf && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1rem" }}>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Per-share value</p>
                    <p className="num" style={{ fontSize: "1.4rem", margin: "0.2rem 0 0" }}>{usd(dcf.per_share_value)}</p>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Enterprise value</p>
                    <p className="num" style={{ fontSize: "1.1rem", margin: "0.2rem 0 0" }}>{usd(dcf.enterprise_value)}</p>
                  </div>
                </div>
                <p className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)", marginBottom: "0.75rem" }}>
                  base FCF {usd(dcf.assumptions.base_fcf)} · growth {pct(dcf.assumptions.growth_rate)}
                  {dcf.assumptions.growth_rate_was_default && " (historical CAGR, no override supplied)"}
                  {" "}· discount {pct(dcf.assumptions.discount_rate)} · terminal growth {pct(dcf.assumptions.terminal_growth_rate)}
                </p>
                {dcf.projections.map((p) => (
                  <div key={p.year} className="ledger-row" style={{ padding: "0.35rem 0" }}>
                    <span className="num" style={{ fontSize: "0.8rem" }}>Year {p.year}</span>
                    <span className="num" style={{ fontSize: "0.8rem" }}>
                      {usd(p.projected_fcf)} → PV {usd(p.present_value)}
                    </span>
                  </div>
                ))}
              </>
            )}
          </div>
        </section>

        <section style={{ marginTop: "2rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Reverse DCF</p>
            <button className="btn-primary" onClick={handleReverseDcf} disabled={reverseDcfLoading} style={{ padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}>
              {reverseDcfLoading ? "…" : "Compute"}
            </button>
          </div>
          <div className="card">
            {reverseDcfError && <p className="num loss" style={{ margin: 0, fontSize: "0.85rem" }}>{reverseDcfError}</p>}
            {!reverseDcf && !reverseDcfError && (
              <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
                Solves backward from the real, current market price to find what growth rate the
                market is already pricing in — often easier to sanity-check than picking a growth
                assumption from scratch. Uses the same 10% discount / 2.5% terminal growth
                defaults as the DCF above.
              </p>
            )}
            {reverseDcf && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Implied growth rate</p>
                    <p className="num" style={{ fontSize: "1.4rem", margin: "0.2rem 0 0" }}>
                      {reverseDcf.implied_growth_rate === null ? "No solution" : pct(reverseDcf.implied_growth_rate)}
                    </p>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Current price</p>
                    <p className="num" style={{ fontSize: "1.1rem", margin: "0.2rem 0 0" }}>{usd(reverseDcf.current_price)}</p>
                  </div>
                </div>
                {reverseDcf.implied_growth_rate === null && (
                  <p className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)", marginTop: "0.5rem" }}>
                    No growth rate between -50% and +200% annually reproduces this price — an
                    honest &quot;no solution in a sane range,&quot; not a computation failure.
                  </p>
                )}
              </>
            )}
          </div>
        </section>

        <section style={{ marginTop: "2rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>IRR</p>
          <div className="card">
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1rem" }}>
              <input
                type="number" placeholder="Entry price (blank = live quote)"
                value={irrEntryPrice} onChange={(e) => setIrrEntryPrice(e.target.value)}
                style={{ flex: "1 1 170px", fontSize: "0.85rem", padding: "0.5rem 0.7rem" }}
              />
              <input
                type="number" placeholder="Exit price" value={irrExitPrice}
                onChange={(e) => setIrrExitPrice(e.target.value)}
                style={{ flex: "1 1 100px", fontSize: "0.85rem", padding: "0.5rem 0.7rem" }}
              />
              <input
                type="number" placeholder="Years" value={irrYears}
                onChange={(e) => setIrrYears(e.target.value)}
                style={{ flex: "1 1 70px", fontSize: "0.85rem", padding: "0.5rem 0.7rem" }}
              />
              <input
                type="number" placeholder="Annual dividend/share" value={irrDividend}
                onChange={(e) => setIrrDividend(e.target.value)}
                style={{ flex: "1 1 140px", fontSize: "0.85rem", padding: "0.5rem 0.7rem" }}
              />
              <button className="btn-primary" onClick={handleIrr} disabled={irrLoading} style={{ padding: "0.5rem 1rem", fontSize: "0.85rem" }}>
                {irrLoading ? "…" : "Compute"}
              </button>
            </div>
            {irrError && <p className="num loss" style={{ margin: 0, fontSize: "0.85rem" }}>{irrError}</p>}
            {!irr && !irrError && (
              <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
                A return calculator for a specific buy-hold-sell scenario — not a company
                assessment. Entry price defaults to the ticker&apos;s live quote if left blank.
                Exit price and years are never defaulted; there&apos;s no way to derive an exit
                assumption without assuming the conclusion.
              </p>
            )}
            {irr && (
              <>
                <p className="eyebrow" style={{ fontSize: "0.65rem" }}>IRR</p>
                <p className="num" style={{ fontSize: "1.4rem", margin: "0.2rem 0 0.75rem" }}>
                  {irr.irr === null ? "No solution" : pct(irr.irr)}
                </p>
                <p className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}>
                  buy {usd(irr.scenario.entry_price)} → sell {usd(irr.scenario.exit_price)} over {irr.scenario.years} yr
                  {irr.scenario.annual_dividend_per_share > 0 && ` · ${usd(irr.scenario.annual_dividend_per_share)}/yr dividend`}
                </p>
                {irr.irr === null && (
                  <p className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)", marginTop: "0.5rem" }}>
                    No discount rate in a sane range zeroes the NPV of this cash flow sequence —
                    check the scenario is realistic.
                  </p>
                )}
              </>
            )}
          </div>
        </section>

        <section style={{ marginTop: "2rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Comps</p>
            <select
              value={compsMetric}
              onChange={(e) => setCompsMetric(e.target.value as typeof compsMetric)}
              style={{ fontSize: "0.8rem", padding: "0.3rem 0.5rem" }}
            >
              <option value="pe">P/E</option>
              <option value="ev_ebitda">EV/EBITDA</option>
              <option value="ps">P/S</option>
              <option value="pfcf">P/FCF</option>
            </select>
            <button className="btn-primary" onClick={handleComps} disabled={compsLoading} style={{ padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}>
              {compsLoading ? "…" : "Compute"}
            </button>
          </div>
          <div className="card">
            {compsError && <p className="num loss" style={{ margin: 0, fontSize: "0.85rem" }}>{compsError}</p>}
            {!comps && !compsError && (
              <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
                Finds real, same-sector peers already in the universe, takes the median of their
                own multiples (not the mean, so one outlier peer can&apos;t dominate), and applies
                it to the target&apos;s own financials.
              </p>
            )}
            {comps && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.75rem" }}>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Implied per-share value</p>
                    <p className="num" style={{ fontSize: "1.4rem", margin: "0.2rem 0 0" }}>{usd(comps.implied_per_share_value)}</p>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Median peer multiple</p>
                    <p className="num" style={{ fontSize: "1.1rem", margin: "0.2rem 0 0" }}>{mult(comps.median_multiple)}</p>
                  </div>
                </div>
                <p className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}>
                  {comps.peers_used.length} peer{comps.peers_used.length === 1 ? "" : "s"} used ({comps.peers_used.join(", ")})
                  {comps.peers_skipped.length > 0 && ` · ${comps.peers_skipped.length} skipped (${comps.peers_skipped.join(", ")})`}
                </p>
              </>
            )}
          </div>
        </section>
      </main>
    </AppShell>
  );
}
