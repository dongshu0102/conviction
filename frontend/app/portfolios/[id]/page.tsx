"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { AppShell } from "@/components/AppShell";
import { api, getApiKey, PortfolioRiskAnalysis, PortfolioValuation } from "@/lib/api";
import { LedgerRow } from "@/components/LedgerRow";

const usd = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

const CHART_COLORS = ["#5EB8C7", "#4FBF8B", "#8B939C", "#E0697A", "#3A424B"];

function AddHoldingForm({ portfolioId, onAdded }: { portfolioId: string; onAdded: () => void }) {
  const [ticker, setTicker] = useState("");
  const [shares, setShares] = useState("");
  const [costBasis, setCostBasis] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const sharesNum = parseFloat(shares);
    const costNum = parseFloat(costBasis);
    if (!ticker.trim() || !sharesNum || sharesNum <= 0 || isNaN(costNum) || costNum < 0) {
      setError("Enter a ticker, positive shares, and a cost basis.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.addHolding(portfolioId, ticker.trim(), sharesNum, costNum);
      setTicker("");
      setShares("");
      setCostBasis("");
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add holding");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: "1rem" }}>
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <input
          type="text"
          placeholder="Ticker"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          style={{ flex: "1 1 90px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <input
          type="number"
          placeholder="Shares"
          value={shares}
          onChange={(e) => setShares(e.target.value)}
          style={{ flex: "1 1 90px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <input
          type="number"
          placeholder="Cost / share"
          value={costBasis}
          onChange={(e) => setCostBasis(e.target.value)}
          style={{ flex: "1 1 110px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <button
          type="submit"
          className="btn-primary"
          disabled={loading}
          style={{ padding: "0.55rem 1.1rem", fontSize: "0.9rem", whiteSpace: "nowrap" }}
        >
          {loading ? "…" : "Add"}
        </button>
      </div>
      {error && (
        <p className="num loss" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}>
          {error}
        </p>
      )}
    </form>
  );
}

export default function PortfolioDetailPage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  const [valuation, setValuation] = useState<PortfolioValuation | null>(null);
  const [risk, setRisk] = useState<PortfolioRiskAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getApiKey()) {
      router.replace("/login");
      return;
    }
    loadValuation();
    // Risk is loaded separately and allowed to fail quietly — a
    // portfolio's core valuation must never be blocked by the
    // volatility panel not loading (e.g. too little price history).
    api.getPortfolioRisk(id).then(setRisk).catch(() => setRisk(null));
  }, [id, router]);

  function loadValuation() {
    return api
      .getPortfolioValuation(id)
      .then(setValuation)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }

  if (loading) {
    return (
      <AppShell>
        <main style={{ padding: "3rem", maxWidth: 720, margin: "0 auto" }}>
          <p className="num" style={{ color: "var(--text-soft)" }}>
            Loading…
          </p>
        </main>
      </AppShell>
    );
  }

  if (error || !valuation) {
    return (
      <AppShell>
        <main style={{ padding: "3rem", maxWidth: 720, margin: "0 auto" }}>
          <p className="num loss">{error || "Portfolio not found."}</p>
          <Link href="/portfolios" style={{ fontSize: "0.9rem" }}>
            ← Back to portfolios
          </Link>
        </main>
      </AppShell>
    );
  }

  const chartData = valuation.positions.map((p) => ({
    name: p.ticker,
    value: p.market_value,
  }));
  const totalGainClass = valuation.total_unrealized_gain >= 0 ? "gain" : "loss";

  return (
    <AppShell>
    <main style={{ padding: "2rem 1.5rem 4rem", maxWidth: 720, margin: "0 auto" }}>
      <Link
        href="/portfolios"
        className="num"
        style={{ fontSize: "0.85rem", color: "var(--text-soft)", textDecoration: "none" }}
      >
        ← Portfolios
      </Link>
      <h1 style={{ fontSize: "1.75rem", margin: "0.5rem 0 2rem" }}>{valuation.name}</h1>

      <section className="card" style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div>
            <p className="eyebrow">Total value</p>
            <p className="num" style={{ fontSize: "2rem", marginTop: "0.25rem" }}>
              {usd(valuation.total_market_value)}
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <p className="eyebrow">Unrealized gain</p>
            <p className={`num ${totalGainClass}`} style={{ fontSize: "1.4rem", marginTop: "0.25rem" }}>
              {usd(valuation.total_unrealized_gain)}
              {valuation.total_unrealized_gain_pct !== null && (
                <span style={{ fontSize: "0.9rem" }}>
                  {" "}
                  ({valuation.total_unrealized_gain_pct >= 0 ? "+" : ""}
                  {(valuation.total_unrealized_gain_pct * 100).toFixed(1)}%)
                </span>
              )}
            </p>
          </div>
        </div>
      </section>

      {chartData.length > 0 && (
        <section style={{ marginBottom: "2.5rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
            Allocation
          </p>
          <div className="card" style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={(entry) => entry.name}
                >
                  {chartData.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => usd(Number(value))} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      <section>
        <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
          Holdings
        </p>
        <div className="card">
          {valuation.positions.length === 0 && (
            <p style={{ color: "var(--text-soft)" }}>No holdings yet — add one below.</p>
          )}
          {valuation.positions.map((p) => (
            <LedgerRow
              key={p.ticker}
              label={p.ticker}
              sublabel={`${p.shares} shares @ ${usd(p.current_price)}`}
              value={usd(p.market_value)}
              changePct={p.unrealized_gain_pct}
            />
          ))}
          <AddHoldingForm portfolioId={id} onAdded={loadValuation} />
        </div>
      </section>

      {risk && (
        <section style={{ marginTop: "2.5rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
            Risk analysis
          </p>
          <div className="card">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "1.25rem", marginBottom: "1.25rem" }}>
              {risk.largest_position_weight !== null && (
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Largest position</p>
                  <p className="num" style={{ fontSize: "1.15rem", margin: "0.2rem 0 0" }}>{pct(risk.largest_position_weight)}</p>
                </div>
              )}
              {risk.herfindahl_index !== null && (
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Concentration (HHI)</p>
                  <p className="num" style={{ fontSize: "1.15rem", margin: "0.2rem 0 0" }}>{risk.herfindahl_index.toFixed(2)}</p>
                </div>
              )}
              {risk.portfolio_annualized_volatility !== null && (
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Annualized volatility</p>
                  <p className="num" style={{ fontSize: "1.15rem", margin: "0.2rem 0 0" }}>{pct(risk.portfolio_annualized_volatility)}</p>
                </div>
              )}
              {risk.parametric_var_95_1day_dollar !== null && (
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>95% 1-day VaR</p>
                  <p className="num loss" style={{ fontSize: "1.15rem", margin: "0.2rem 0 0" }}>
                    -{usd(risk.parametric_var_95_1day_dollar)}
                  </p>
                </div>
              )}
            </div>

            {risk.volatility_covered_weight !== null && risk.volatility_covered_weight < 0.999 && (
              <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.75rem", marginBottom: "1rem" }}>
                Volatility figures cover {pct(risk.volatility_covered_weight)} of this portfolio by
                value — {risk.excluded_from_volatility_calc.join(", ")} lacked enough price history.
              </p>
            )}

            {risk.sector_exposures.length > 0 && (
              <div style={{ marginBottom: "1.25rem" }}>
                <p className="eyebrow" style={{ fontSize: "0.65rem", marginBottom: "0.5rem" }}>Sector exposure</p>
                {risk.sector_exposures.map((s) => (
                  <div key={s.sector} className="ledger-row" style={{ padding: "0.5rem 0" }}>
                    <span style={{ fontSize: "0.85rem" }}>{s.sector}</span>
                    <span className="num" style={{ fontSize: "0.85rem" }}>{pct(s.weight)}</span>
                  </div>
                ))}
              </div>
            )}

            {risk.pairwise_correlations.length > 0 && (
              <div>
                <p className="eyebrow" style={{ fontSize: "0.65rem", marginBottom: "0.5rem" }}>Pairwise correlation</p>
                {risk.pairwise_correlations.map((c) => (
                  <div key={`${c.ticker_a}-${c.ticker_b}`} className="ledger-row" style={{ padding: "0.4rem 0" }}>
                    <span className="num" style={{ fontSize: "0.82rem" }}>{c.ticker_a} · {c.ticker_b}</span>
                    <span className="num" style={{ fontSize: "0.82rem" }}>{c.correlation.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            )}

            <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.7rem", marginTop: "1.25rem", marginBottom: 0 }}>
              Parametric estimate assuming normally-distributed returns — a standard
              approximation, not a guarantee.
            </p>
          </div>
        </section>
      )}
    </main>
    </AppShell>
  );
}
