"use client";

// Market Workflow — ties together the real, full 4-step pipeline this
// app's own backend already supports end to end: screen the whole,
// real market (FMP), rank finalists with real fundamentals and
// analyst ratings, validate real price trends, then add to the
// watchlist to monitor going forward.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { AppShell } from "@/components/AppShell";
import {
  api, getApiKey, ApiError, MarketScreenCandidate, AnalystRatings, StockCandle, EconomicCycleState,
  DemandSignals,
} from "@/lib/api";

const usd = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function fmtMarketCap(n: number): string {
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  return usd(n);
}

type Step = 1 | 2 | 3 | 4;

export default function MarketWorkflowPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);

  // Economic cycle context — real, macro-level, applies to the whole
  // session regardless of which step is active.
  const [cycle, setCycle] = useState<EconomicCycleState | null>(null);
  const [cycleError, setCycleError] = useState<string | null>(null);

  useEffect(() => {
    if (!getApiKey()) return;
    api.getEconomicCycle()
      .then(setCycle)
      .catch((err) => setCycleError(err instanceof Error ? err.message : "Couldn't load economic cycle"));
  }, []);

  // Step 1: Screen
  const [sector, setSector] = useState("Technology");
  const [country, setCountry] = useState("US");
  const [marketCapMoreThan, setMarketCapMoreThan] = useState("10000000000");
  const [screening, setScreening] = useState(false);
  const [screenError, setScreenError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<MarketScreenCandidate[] | null>(null);

  // Step 2: Rank
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [ratings, setRatings] = useState<AnalystRatings | null>(null);
  const [ratingsLoading, setRatingsLoading] = useState(false);
  const [ratingsError, setRatingsError] = useState<string | null>(null);
  const [demandSignals, setDemandSignals] = useState<DemandSignals | null>(null);
  const [demandSignalsError, setDemandSignalsError] = useState<string | null>(null);

  // Step 3: Validate
  const [candles, setCandles] = useState<StockCandle[] | null>(null);
  const [candlesLoading, setCandlesLoading] = useState(false);
  const [candlesError, setCandlesError] = useState<string | null>(null);

  // Step 4: Monitor
  const [addingToWatchlist, setAddingToWatchlist] = useState(false);
  const [watchlistMessage, setWatchlistMessage] = useState<string | null>(null);

  function requireAuth(): boolean {
    if (!getApiKey()) {
      router.push("/login");
      return false;
    }
    return true;
  }

  async function handleScreen(e: React.FormEvent) {
    e.preventDefault();
    if (!requireAuth()) return;
    setScreening(true);
    setScreenError(null);
    try {
      const result = await api.screenMarket({
        sector: sector || undefined,
        country: country || undefined,
        market_cap_more_than: marketCapMoreThan ? Number(marketCapMoreThan) : undefined,
        limit: 20,
      });
      setCandidates(result.candidates);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.push("/login");
        return;
      }
      setScreenError(err instanceof Error ? err.message : "Couldn't screen the market");
    } finally {
      setScreening(false);
    }
  }

  async function handleSelectForRanking(ticker: string) {
    if (!requireAuth()) return;
    setSelectedTicker(ticker);
    setStep(2);
    setRatingsLoading(true);
    setRatingsError(null);
    setRatings(null);
    setDemandSignals(null);
    setDemandSignalsError(null);

    const [ratingsResult, demandResult] = await Promise.allSettled([
      api.getAnalystRatings(ticker),
      api.getDemandSignals(ticker),
    ]);

    if (ratingsResult.status === "fulfilled") {
      setRatings(ratingsResult.value);
    } else {
      setRatingsError(
        ratingsResult.reason instanceof Error ? ratingsResult.reason.message : `Couldn't load ratings for ${ticker}`
      );
    }
    setRatingsLoading(false);

    if (demandResult.status === "fulfilled") {
      setDemandSignals(demandResult.value);
    } else {
      setDemandSignalsError(
        demandResult.reason instanceof Error ? demandResult.reason.message : `Couldn't load demand signals for ${ticker}`
      );
    }
  }

  async function handleValidate() {
    if (!selectedTicker || !requireAuth()) return;
    setStep(3);
    setCandlesLoading(true);
    setCandlesError(null);
    try {
      const to = new Date();
      const from = new Date();
      from.setDate(from.getDate() - 60);
      const toStr = to.toISOString().slice(0, 10);
      const fromStr = from.toISOString().slice(0, 10);
      const result = await api.getStockCandles(selectedTicker, fromStr, toStr);
      setCandles(result);
    } catch (err) {
      setCandlesError(err instanceof Error ? err.message : `Couldn't load price history for ${selectedTicker}`);
    } finally {
      setCandlesLoading(false);
    }
  }

  async function handleAddToWatchlist() {
    if (!selectedTicker || !requireAuth()) return;
    setAddingToWatchlist(true);
    setWatchlistMessage(null);
    try {
      await api.addToWatchlist(selectedTicker);
      setWatchlistMessage(`${selectedTicker} added to your watchlist — use Watchlist's Refresh Quotes to monitor it going forward.`);
      setStep(4);
    } catch (err) {
      setWatchlistMessage(err instanceof Error ? err.message : `Couldn't add ${selectedTicker} to the watchlist`);
    } finally {
      setAddingToWatchlist(false);
    }
  }

  const chartData = (candles || []).map((c) => ({
    date: c.timestamp.slice(5, 10),
    close: c.close,
  }));

  return (
    <AppShell>
      <main style={{ maxWidth: "1000px", margin: "0 auto", padding: "2rem 1.5rem" }}>
        <h1 style={{ margin: "0 0 0.25rem", fontSize: "1.4rem" }}>Market Workflow</h1>
        <p style={{ color: "var(--text-soft)", fontSize: "0.85rem", marginBottom: "1.5rem" }}>
          Screen the real market, rank finalists with real analyst ratings, validate real price trends, then monitor on your watchlist — the full pipeline, in one place.
        </p>

        {cycleError && (
          <p className="num loss" style={{ fontSize: "0.78rem", marginBottom: "1rem" }}>{cycleError}</p>
        )}

        {cycle && (
          <div
            className="card"
            style={{
              display: "flex", justifyContent: "space-between", alignItems: "baseline",
              marginBottom: "1.5rem", padding: "0.75rem 1rem",
            }}
          >
            <div>
              <span className="eyebrow" style={{ fontSize: "0.65rem", marginRight: "0.6rem" }}>
                Economic cycle
              </span>
              <span
                className={
                  "num " + (
                    cycle.state === "Contraction" ? "loss"
                    : cycle.state === "Expansion" ? "gain"
                    : ""
                  )
                }
                style={{
                  fontSize: "0.88rem", fontWeight: 600,
                  color: cycle.state === "Late-cycle warning" ? "var(--accent)" : undefined,
                }}
              >
                {cycle.state}
              </span>
            </div>
            <span style={{ color: "var(--text-soft)", fontSize: "0.75rem" }}>
              {cycle.reasoning[0]}
            </span>
          </div>
        )}

        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
          {(["Screen", "Rank", "Validate", "Monitor"] as const).map((label, i) => {
            const s = (i + 1) as Step;
            const active = step === s;
            const reachable = s === 1 || (s === 2 && candidates) || (s === 3 && selectedTicker) || (s === 4 && selectedTicker);
            return (
              <button
                key={label}
                onClick={() => reachable && setStep(s)}
                disabled={!reachable}
                style={{
                  flex: 1, padding: "0.5rem", fontSize: "0.82rem", borderRadius: "4px",
                  border: active ? "1px solid var(--accent)" : "1px solid var(--rule)",
                  background: active ? "rgba(94, 184, 199, 0.1)" : "transparent",
                  color: active ? "var(--accent)" : reachable ? "var(--text)" : "var(--text-soft)",
                  cursor: reachable ? "pointer" : "not-allowed",
                  fontWeight: active ? 600 : 400,
                }}
              >
                {i + 1}. {label}
              </button>
            );
          })}
        </div>

        {step === 1 && (
          <div className="card">
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.75rem" }}>Step 1 — Screen the real market</p>
            <form onSubmit={handleScreen} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1rem" }}>
              <input
                type="text" placeholder="Sector" value={sector} onChange={(e) => setSector(e.target.value)}
                style={{ flex: "1 1 140px", fontSize: "0.85rem", padding: "0.5rem 0.7rem" }}
              />
              <input
                type="text" placeholder="Country" value={country} onChange={(e) => setCountry(e.target.value)}
                style={{ flex: "1 1 100px", fontSize: "0.85rem", padding: "0.5rem 0.7rem" }}
              />
              <input
                type="number" placeholder="Min market cap ($)" value={marketCapMoreThan}
                onChange={(e) => setMarketCapMoreThan(e.target.value)}
                style={{ flex: "1 1 160px", fontSize: "0.85rem", padding: "0.5rem 0.7rem" }}
              />
              <button type="submit" className="btn-primary" disabled={screening} style={{ padding: "0.5rem 1.1rem", fontSize: "0.85rem" }}>
                {screening ? "Screening…" : "Screen"}
              </button>
            </form>

            {screenError && <p className="num loss" style={{ fontSize: "0.82rem" }}>{screenError}</p>}

            {candidates && candidates.length === 0 && (
              <p style={{ color: "var(--text-soft)" }}>No companies matched these criteria.</p>
            )}

            {candidates && candidates.length > 0 && (
              <table className="num" style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.82rem" }}>
                <thead>
                  <tr style={{ textAlign: "right", color: "var(--text-soft)", fontSize: "0.66rem" }}>
                    <th style={{ textAlign: "left", padding: "0.3rem" }}>TICKER</th>
                    <th style={{ textAlign: "left", padding: "0.3rem" }}>COMPANY</th>
                    <th style={{ padding: "0.3rem" }}>MKT CAP</th>
                    <th style={{ padding: "0.3rem" }}>PRICE</th>
                    <th style={{ padding: "0.3rem" }}>BETA</th>
                    <th style={{ padding: "0.3rem" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((c) => (
                    <tr key={c.ticker} style={{ borderTop: "1px solid var(--rule)" }}>
                      <td style={{ padding: "0.4rem", textAlign: "left", fontWeight: 600 }}>{c.ticker}</td>
                      <td style={{ padding: "0.4rem", textAlign: "left", color: "var(--text-soft)" }}>{c.company_name}</td>
                      <td style={{ padding: "0.4rem", textAlign: "right" }}>{fmtMarketCap(c.market_cap)}</td>
                      <td style={{ padding: "0.4rem", textAlign: "right" }}>{usd(c.price)}</td>
                      <td style={{ padding: "0.4rem", textAlign: "right" }}>{c.beta?.toFixed(2) ?? "—"}</td>
                      <td style={{ padding: "0.4rem", textAlign: "right" }}>
                        <button
                          onClick={() => handleSelectForRanking(c.ticker)}
                          style={{ fontSize: "0.78rem", padding: "0.3rem 0.6rem", cursor: "pointer" }}
                        >
                          Rank →
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {step === 2 && selectedTicker && (
          <div className="card">
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.75rem" }}>
              Step 2 — Rank {selectedTicker} with real analyst ratings
            </p>
            {ratingsLoading && <p style={{ color: "var(--text-soft)" }}>Loading…</p>}
            {ratingsError && <p className="num loss" style={{ fontSize: "0.82rem" }}>{ratingsError}</p>}
            {!ratingsLoading && ratings === null && !ratingsError && (
              <p style={{ color: "var(--text-soft)" }}>No real analyst coverage found for {selectedTicker}.</p>
            )}
            {ratings && (
              <>
                <p className="num" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>
                  Avg price target (last quarter, {ratings.last_quarter_count} analysts): {" "}
                  <strong>{ratings.last_quarter_avg_price_target ? usd(ratings.last_quarter_avg_price_target) : "—"}</strong>
                </p>
                <p className="eyebrow" style={{ fontSize: "0.65rem", marginBottom: "0.5rem" }}>Recent grade actions</p>
                {ratings.recent_grades.slice(0, 8).map((g, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "0.35rem 0", borderTop: i > 0 ? "1px solid var(--rule)" : "none", fontSize: "0.82rem" }}>
                    <span>{g.grading_company}</span>
                    <span className="num" style={{ color: "var(--text-soft)" }}>{g.date}</span>
                    <span className="num">{g.previous_grade} → {g.new_grade} ({g.action})</span>
                  </div>
                ))}
              </>
            )}

            {demandSignalsError && (
              <p className="num loss" style={{ fontSize: "0.82rem", marginTop: "1rem" }}>{demandSignalsError}</p>
            )}
            {demandSignals && (
              <div style={{ marginTop: "1.25rem", paddingTop: "1rem", borderTop: "1px solid var(--rule)" }}>
                <p className="eyebrow" style={{ fontSize: "0.65rem", marginBottom: "0.6rem" }}>
                  Demand signals — real revenue growth, analyst activity, and the economic backdrop
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", fontSize: "0.82rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-soft)" }}>Revenue growth (YoY)</span>
                    <span className="num">
                      {demandSignals.latest_revenue_growth_yoy !== null
                        ? `${(demandSignals.latest_revenue_growth_yoy * 100).toFixed(1)}%`
                        : "—"}
                      {demandSignals.revenue_growth_accelerating !== null && (
                        <span
                          className={demandSignals.revenue_growth_accelerating ? "gain" : "loss"}
                          style={{ marginLeft: "0.4rem" }}
                        >
                          ({demandSignals.revenue_growth_accelerating ? "accelerating" : "decelerating"})
                        </span>
                      )}
                    </span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-soft)" }}>Analyst activity</span>
                    <span className="num">
                      {demandSignals.recent_upgrades} upgrades, {demandSignals.recent_downgrades} downgrades —{" "}
                      <span
                        className={
                          demandSignals.analyst_consensus_direction === "More bullish" ? "gain"
                          : demandSignals.analyst_consensus_direction === "More bearish" ? "loss"
                          : ""
                        }
                      >
                        {demandSignals.analyst_consensus_direction}
                      </span>
                    </span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-soft)" }}>Economic backdrop</span>
                    <span className="num">{demandSignals.economic_cycle_state}</span>
                  </div>
                </div>
              </div>
            )}

            <button onClick={handleValidate} className="btn-primary" style={{ marginTop: "1rem", padding: "0.5rem 1.1rem", fontSize: "0.85rem" }}>
              Validate price trend →
            </button>
          </div>
        )}

        {step === 3 && selectedTicker && (
          <div className="card">
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.75rem" }}>
              Step 3 — Validate {selectedTicker}&rsquo;s real price trend (last 60 days)
            </p>
            {candlesLoading && <p style={{ color: "var(--text-soft)" }}>Loading…</p>}
            {candlesError && <p className="num loss" style={{ fontSize: "0.82rem" }}>{candlesError}</p>}
            {chartData.length > 0 && (
              <div style={{ height: "260px", marginBottom: "1rem" }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--rule)" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="var(--text-soft)" />
                    <YAxis tick={{ fontSize: 10 }} stroke="var(--text-soft)" domain={["auto", "auto"]} />
                    <Tooltip
                      formatter={(v) => [typeof v === "number" ? usd(v) : "—", "Close"]}
                      contentStyle={{ fontSize: "0.8rem" }}
                    />
                    <Line type="monotone" dataKey="close" stroke="var(--accent)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
            <button onClick={handleAddToWatchlist} className="btn-primary" disabled={addingToWatchlist} style={{ padding: "0.5rem 1.1rem", fontSize: "0.85rem" }}>
              {addingToWatchlist ? "Adding…" : "Add to watchlist →"}
            </button>
          </div>
        )}

        {step === 4 && (
          <div className="card">
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.75rem" }}>Step 4 — Monitor</p>
            {watchlistMessage && <p className="num" style={{ fontSize: "0.85rem" }}>{watchlistMessage}</p>}
            <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>
              Visit the Watchlist page and use Refresh Quotes to cheaply track {selectedTicker} and everything else on your list going forward.
            </p>
          </div>
        )}
      </main>
    </AppShell>
  );
}
