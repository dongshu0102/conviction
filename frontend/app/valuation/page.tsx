"use client";

// Valuation — a real macro context (Treasury yields, GDP/CPI/inflation/
// unemployment/equity risk premium, yield curve inversion, the Taylor
// Rule), then 5 genuinely distinct company-level models under one
// ticker input. Every section is click-to-compute, not auto-loaded
// (Treasury Yields is the one exception, since it's needed to seed the
// DCF discount-rate suggestion) — matching the same pattern as Growth
// Hunter's tracked-candidate checks and the portfolio Greeks/hedging
// sections.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import {
  api, getApiKey, ApiError,
  ValuationSnapshot, DcfResponse, ReverseDcfResponse, IrrResponse, CompsResponse, CompsMetric,
  TreasuryRates, MacroSnapshot, RateSignals,
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

function asOf(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function peerMatchLabel(level: string): string {
  if (level === "industry") return "same industry";
  if (level === "industry+sector") return "industry + sector";
  if (level === "sector") return "same sector";
  return level;
}

function pctDiffFromPrice(estimate: number, price: number): string {
  const diff = ((estimate - price) / price) * 100;
  const sign = diff >= 0 ? "+" : "";
  return `${sign}${diff.toFixed(1)}%`;
}

export default function ValuationPage() {
  const router = useRouter();
  const [ticker, setTicker] = useState("");
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [runAllLoading, setRunAllLoading] = useState(false);

  // Treasury yields
  const [treasury, setTreasury] = useState<TreasuryRates | null>(null);
  const [treasuryLoading, setTreasuryLoading] = useState(false);
  const [treasuryError, setTreasuryError] = useState<string | null>(null);

  // Macro snapshot
  const [macro, setMacro] = useState<MacroSnapshot | null>(null);
  const [macroLoading, setMacroLoading] = useState(false);
  const [macroError, setMacroError] = useState<string | null>(null);

  // Rate signals
  const [rateSignals, setRateSignals] = useState<RateSignals | null>(null);
  const [rateSignalsLoading, setRateSignalsLoading] = useState(false);
  const [rateSignalsError, setRateSignalsError] = useState<string | null>(null);

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

  async function handleMacro() {
    setMacroLoading(true);
    setMacroError(null);
    try {
      setMacro(await api.getMacroSnapshot());
    } catch (err) {
      setMacroError(err instanceof Error ? err.message : "Couldn't load macro snapshot");
    } finally {
      setMacroLoading(false);
    }
  }

  async function handleRateSignals() {
    setRateSignalsLoading(true);
    setRateSignalsError(null);
    try {
      setRateSignals(await api.getRateSignals());
    } catch (err) {
      setRateSignalsError(err instanceof Error ? err.message : "Couldn't load rate signals");
    } finally {
      setRateSignalsLoading(false);
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

  async function handleRunAll() {
    const t = currentTicker();
    if (!t) return;
    setRunAllLoading(true);
    try {
      const tasks = [handleMultiples(), handleDcf(), handleReverseDcf(), handleComps()];
      // IRR's exit price is deliberately never defaulted — there's no
      // way to derive an exit assumption without assuming the
      // conclusion — so Run All only includes it if the user has
      // already specified a real scenario themselves.
      if (irrExitPrice.trim() !== "") {
        tasks.push(handleIrr());
      }
      await Promise.all(tasks);
    } finally {
      setRunAllLoading(false);
    }
  }

  return (
    <AppShell>
      <main style={{ maxWidth: 760, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Valuation</p>
        <h1 style={{ margin: "0.3rem 0 0.75rem" }}>Valuation</h1>
        <p style={{ color: "var(--text-soft)", lineHeight: 1.6, marginBottom: "1.5rem", fontSize: "0.95rem" }}>
          The real macro environment first, then four genuinely different ways to ask what a
          specific company is worth. Every assumption is shown, never hidden — small changes in
          growth or discount rate can swing a DCF substantially, which is a real property of the
          model, not a flaw in this tool.
        </p>

        <h2 style={{ fontSize: "1.05rem", fontWeight: 600, margin: "0 0 0.25rem" }}>Macro Context</h2>
        <p style={{ color: "var(--text-soft)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>
          Ticker-independent — the real, current environment every valuation below sits inside.
        </p>
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
                <p className="num" style={{ fontSize: "0.7rem", color: "var(--text-soft)", margin: "0 0 0.75rem" }}>
                  As of {asOf(treasury.as_of)}
                </p>
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
                      Suggested DCF discount rate (10yr + the real current equity risk premium):{" "}
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
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Macro Snapshot</p>
            <button className="btn-primary" onClick={handleMacro} disabled={macroLoading} style={{ padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}>
              {macroLoading ? "…" : "Compute"}
            </button>
          </div>
          <div className="card">
            {macroError && <p className="num loss" style={{ margin: 0, fontSize: "0.85rem" }}>{macroError}</p>}
            {!macro && !macroError && (
              <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
                GDP, inflation, unemployment, the real current US equity risk premium, and recent
                macro news, all in one place. The structured, quantifiable half of macro analysis —
                real numbers and real headlines, not an attempt to model geopolitical risk,
                regulatory change, or foreign central bank policy, none of which have a clean
                numeric API to pull from.
              </p>
            )}
            {macro && (
              <>
                <p className="num" style={{ fontSize: "0.7rem", color: "var(--text-soft)", margin: "0 0 0.75rem" }}>
                  As of {asOf(macro.as_of)}
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))", gap: "1rem", marginBottom: "1rem" }}>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.65rem" }}>GDP</p>
                    <p className="num" style={{ fontSize: "1rem", margin: "0.2rem 0 0" }}>
                      {macro.gdp ? `$${macro.gdp.value.toLocaleString()}B` : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Inflation</p>
                    <p className="num" style={{ fontSize: "1rem", margin: "0.2rem 0 0" }}>
                      {macro.inflation_rate ? `${macro.inflation_rate.value.toFixed(2)}%` : "—"}
                    </p>
                    {macro.cpi && (
                      <p className="num" style={{ fontSize: "0.68rem", color: "var(--text-soft)", margin: "0.1rem 0 0" }}>
                        CPI {macro.cpi.value.toFixed(1)}
                      </p>
                    )}
                  </div>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Unemployment</p>
                    <p className="num" style={{ fontSize: "1rem", margin: "0.2rem 0 0" }}>
                      {macro.unemployment_rate ? `${macro.unemployment_rate.value.toFixed(1)}%` : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Equity Risk Premium</p>
                    <p className="num" style={{ fontSize: "1rem", margin: "0.2rem 0 0" }}>
                      {macro.risk_premium
                        ? `${(macro.risk_premium.total_equity_risk_premium * 100).toFixed(2)}%`
                        : "—"}
                    </p>
                  </div>
                </div>
                {macro.recent_news.length > 0 && (
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.65rem", marginBottom: "0.5rem" }}>Recent Macro News</p>
                    {macro.recent_news.map((headline, i) => (
                      <div key={i} style={{ padding: "0.35rem 0", borderTop: i > 0 ? "1px solid var(--rule)" : "none" }}>
                        {headline.url ? (
                          <a href={headline.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: "0.85rem", color: "var(--text)" }}>
                            {headline.title}
                          </a>
                        ) : (
                          <span style={{ fontSize: "0.85rem" }}>{headline.title}</span>
                        )}
                        {headline.publisher && (
                          <span style={{ fontSize: "0.75rem", color: "var(--text-soft)" }}> — {headline.publisher}</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        <section style={{ marginTop: "2rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Rate Signals</p>
            <button className="btn-primary" onClick={handleRateSignals} disabled={rateSignalsLoading} style={{ padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}>
              {rateSignalsLoading ? "…" : "Compute"}
            </button>
          </div>
          <div className="card">
            {rateSignalsError && <p className="num loss" style={{ margin: 0, fontSize: "0.85rem" }}>{rateSignalsError}</p>}
            {!rateSignals && !rateSignalsError && (
              <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
                Three real, standard rate-direction/recession signals: yield curve inversion (a
                real, widely-cited historical recession signal, not a guarantee), the Taylor Rule
                (where rates arguably &quot;should&quot; be, given real inflation and output gap,
                versus the real current fed funds rate), and the Sahm Rule (a real, historically
                fairly reliable recession indicator based on the recent trend in unemployment).
                None of these predict anything — all are tools economists and the Fed itself weigh
                alongside others, not a forecast.
              </p>
            )}
            {rateSignals && (
              <>
                <p className="num" style={{ fontSize: "0.7rem", color: "var(--text-soft)", margin: "0 0 0.75rem" }}>
                  As of {asOf(rateSignals.as_of)}
                </p>
                <div style={{ marginBottom: "1rem" }}>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Yield Curve</p>
                  <p className="num" style={{ fontSize: "1.1rem", margin: "0.2rem 0 0.4rem", color: rateSignals.yield_curve.is_inverted ? "var(--loss)" : "var(--text)" }}>
                    {rateSignals.yield_curve.is_inverted ? "Inverted" : "Not inverted"}
                  </p>
                  <p className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}>
                    10yr-2yr: {rateSignals.yield_curve.spread_10y_2y !== null ? `${rateSignals.yield_curve.spread_10y_2y.toFixed(2)}pp` : "—"}
                    {" · "}
                    10yr-3mo: {rateSignals.yield_curve.spread_10y_3m !== null ? `${rateSignals.yield_curve.spread_10y_3m.toFixed(2)}pp` : "—"}
                  </p>
                  <p style={{ fontSize: "0.82rem", color: "var(--text-soft)", marginTop: "0.4rem", lineHeight: 1.5 }}>
                    {rateSignals.yield_curve.interpretation}
                  </p>
                </div>
                <div style={{ marginBottom: "1rem" }}>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Taylor Rule</p>
                  {rateSignals.taylor_rule ? (
                    <>
                      <div style={{ display: "flex", justifyContent: "space-between", margin: "0.2rem 0 0.4rem" }}>
                        <p className="num" style={{ fontSize: "1.1rem", margin: 0 }}>
                          {rateSignals.taylor_rule.target_rate.toFixed(2)}%
                          <span style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}> implied target</span>
                        </p>
                        {rateSignals.taylor_rule.current_rate !== null && (
                          <p className="num" style={{ fontSize: "0.85rem", color: "var(--text-soft)", margin: 0 }}>
                            {rateSignals.taylor_rule.current_rate.toFixed(2)}% current
                          </p>
                        )}
                      </div>
                      <p style={{ fontSize: "0.82rem", color: "var(--text-soft)", lineHeight: 1.5 }}>
                        {rateSignals.taylor_rule.interpretation}
                      </p>
                    </>
                  ) : (
                    <p style={{ margin: "0.2rem 0 0", color: "var(--text-soft)", fontSize: "0.85rem" }}>
                      {rateSignals.taylor_rule_unavailable_reason || "Unavailable."}
                    </p>
                  )}
                </div>
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Sahm Rule</p>
                  {rateSignals.sahm_rule ? (
                    <>
                      <p className="num" style={{ fontSize: "1.1rem", margin: "0.2rem 0 0.4rem", color: rateSignals.sahm_rule.is_triggered ? "var(--loss)" : "var(--text)" }}>
                        {rateSignals.sahm_rule.is_triggered ? "Triggered" : "Not triggered"}
                      </p>
                      <p className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}>
                        3-mo avg: {rateSignals.sahm_rule.current_3mo_avg.toFixed(2)}%
                        {" · "}
                        12-mo low: {rateSignals.sahm_rule.trailing_12mo_min_3mo_avg.toFixed(2)}%
                        {" · "}
                        gap: {rateSignals.sahm_rule.gap.toFixed(2)}pp
                      </p>
                      <p style={{ fontSize: "0.82rem", color: "var(--text-soft)", marginTop: "0.4rem", lineHeight: 1.5 }}>
                        {rateSignals.sahm_rule.interpretation}
                      </p>
                    </>
                  ) : (
                    <p style={{ margin: "0.2rem 0 0", color: "var(--text-soft)", fontSize: "0.85rem" }}>
                      {rateSignals.sahm_rule_unavailable_reason || "Unavailable."}
                    </p>
                  )}
                </div>
              </>
            )}
          </div>
        </section>

        <h2 style={{ fontSize: "1.05rem", fontWeight: 600, margin: "2.5rem 0 0.25rem" }}>Company Valuation</h2>
        <p style={{ color: "var(--text-soft)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>
          Four genuinely different ways to ask what a company is worth — a DCF builds value up
          from projected cash flows, a reverse DCF asks what growth rate the current price
          already assumes, IRR is a return calculator for a specific buy-hold-sell scenario, and
          comps applies real peer multiples to the target&apos;s own financials.
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
          <button
            className="btn-primary" onClick={handleRunAll} disabled={runAllLoading}
            style={{ padding: "0.6rem 1.1rem", fontSize: "0.9rem", whiteSpace: "nowrap" }}
          >
            {runAllLoading ? "Running…" : "Run All"}
          </button>
        </div>
        {globalError && (
          <p className="num loss" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>{globalError}</p>
        )}

        <section style={{ marginTop: "2rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Multiples</p>
            <button className="btn-primary" onClick={handleMultiples} disabled={multiplesLoading} style={{ padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}>
              {multiplesLoading ? "…" : "Compute"}
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
              <>
                <p className="num" style={{ fontSize: "0.7rem", color: "var(--text-soft)", margin: "0 0 0.75rem" }}>
                  Price as of {asOf(multiples.as_of)} · fundamentals from FY{multiples.fundamentals_fiscal_year}
                </p>
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
                <p className="num" style={{ fontSize: "0.7rem", color: "var(--text-soft)", margin: "0 0 0.75rem" }}>
                  As of {asOf(dcf.as_of)}
                </p>
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
                <p className="num" style={{ fontSize: "0.7rem", color: "var(--text-soft)", margin: "0 0 0.75rem" }}>
                  As of {asOf(reverseDcf.as_of)}
                </p>
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
                <p className="num" style={{ fontSize: "0.7rem", color: "var(--text-soft)", margin: "0 0 0.75rem" }}>
                  As of {asOf(irr.as_of)}
                </p>
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
                Prefers real same-industry peers already in the universe (e.g. Semiconductors),
                only falling back to the broader same-sector match (e.g. Technology, which can mix
                in software companies with very different multiple profiles) when the industry
                pool is too small. Takes the median of peer multiples (not the mean, so one
                outlier can&apos;t dominate), and applies it to the target&apos;s own financials.
              </p>
            )}
            {comps && (
              <>
                <p className="num" style={{ fontSize: "0.7rem", color: "var(--text-soft)", margin: "0 0 0.75rem" }}>
                  As of {asOf(comps.as_of)} · peer match: {peerMatchLabel(comps.peer_match_level)}
                </p>
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
                {comps.peer_match_level !== "industry" && (
                  <p className="num" style={{ fontSize: "0.75rem", color: "var(--accent)", marginTop: "0.4rem" }}>
                    Note: too few same-industry peers were available, so this includes broader
                    same-sector peers, which can carry meaningfully different multiples.
                  </p>
                )}
              </>
            )}
          </div>
        </section>

        {multiples && (dcf || comps) && (
          <section style={{ marginTop: "2rem" }}>
            <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>Synthesis</p>
            <div className="card">
              <p className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)", marginBottom: "0.75rem" }}>
                Every real estimate computed so far for {multiples.ticker}, side by side against
                the real current price — no single number here is the answer, each one tests the
                others.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "1rem", marginBottom: dcf && reverseDcf ? "1rem" : 0 }}>
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Current price</p>
                  <p className="num" style={{ fontSize: "1.1rem", margin: "0.2rem 0 0" }}>{usd(multiples.price)}</p>
                </div>
                {dcf && dcf.per_share_value !== null && (
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.65rem" }}>DCF</p>
                    <p className="num" style={{ fontSize: "1.1rem", margin: "0.2rem 0 0" }}>
                      {usd(dcf.per_share_value)}
                      <span style={{ fontSize: "0.72rem", color: "var(--text-soft)" }}> ({pctDiffFromPrice(dcf.per_share_value, multiples.price)})</span>
                    </p>
                  </div>
                )}
                {comps && comps.implied_per_share_value !== null && (
                  <div>
                    <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Comps</p>
                    <p className="num" style={{ fontSize: "1.1rem", margin: "0.2rem 0 0" }}>
                      {usd(comps.implied_per_share_value)}
                      <span style={{ fontSize: "0.72rem", color: "var(--text-soft)" }}> ({pctDiffFromPrice(comps.implied_per_share_value, multiples.price)})</span>
                    </p>
                  </div>
                )}
              </div>
              {dcf && reverseDcf && reverseDcf.implied_growth_rate !== null && (
                <p style={{ fontSize: "0.82rem", color: "var(--text-soft)", lineHeight: 1.5, margin: 0 }}>
                  DCF assumes {pct(dcf.assumptions.growth_rate)} growth
                  {dcf.assumptions.growth_rate_was_default && " (the company's own historical CAGR)"}
                  , while the market is currently pricing in {pct(reverseDcf.implied_growth_rate)} — {
                    dcf.assumptions.growth_rate > reverseDcf.implied_growth_rate
                      ? "the DCF's higher growth assumption is consistent with its above-market implied value."
                      : dcf.assumptions.growth_rate < reverseDcf.implied_growth_rate
                        ? "the DCF's lower growth assumption is consistent with its below-market implied value."
                        : "the two happen to agree almost exactly on the growth assumption."
                  }
                </p>
              )}
              {comps && comps.peer_match_level !== "industry" && (
                <p className="num" style={{ fontSize: "0.75rem", color: "var(--accent)", marginTop: "0.5rem" }}>
                  Treat the Comps figure with extra caution here — it relied on {peerMatchLabel(comps.peer_match_level)}{" "}
                  peers, not a pure same-industry match.
                </p>
              )}
            </div>
          </section>
        )}
      </main>
    </AppShell>
  );
}
