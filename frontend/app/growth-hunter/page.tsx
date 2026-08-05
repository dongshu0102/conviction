"use client";

// Growth Hunter — Path B, the actual differentiator. Deliberately
// NOT the same UI language as factor scores or valuation: no single
// number, no implied confidence. Every section is a plain fact or an
// explicit "unknown," and risk_flags get equal visual weight to the
// growth story, not buried below it. See AssessSpeculativeGrowthUseCase's
// own docstring for why this needed a genuinely different analysis,
// not just a re-weighted factor score.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, getApiKey, ApiError, SpeculativeGrowthAssessment } from "@/lib/api";

function fmtPct(v: number | null): string {
  if (v === null || v === undefined) return "unknown";
  return `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
}

function fmtMarketCap(v: number | null): string {
  if (v === null || v === undefined) return "unknown";
  if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}

const TREND_COLOR: Record<string, string> = {
  accelerating: "var(--gain)",
  decelerating: "var(--loss)",
  insufficient_data: "var(--text-soft)",
};

const TREND_LABEL: Record<string, string> = {
  accelerating: "Accelerating",
  decelerating: "Decelerating",
  insufficient_data: "Not enough data yet",
};

export default function GrowthHunterPage() {
  const router = useRouter();
  const [ticker, setTicker] = useState("");
  const [assessment, setAssessment] = useState<SpeculativeGrowthAssessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notIngested, setNotIngested] = useState(false);
  const [ingesting, setIngesting] = useState(false);

  useEffect(() => {
    if (!getApiKey()) router.push("/login");
  }, [router]);

  async function runAssessment(t: string) {
    setLoading(true);
    setError(null);
    setNotIngested(false);
    try {
      const result = await api.getSpeculativeGrowth(t);
      setAssessment(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setNotIngested(true);
      } else {
        setError(err instanceof Error ? err.message : "Couldn't assess that ticker.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setAssessment(null);
    await runAssessment(t);
  }

  async function handleIngestAndAssess() {
    const t = ticker.trim().toUpperCase();
    setIngesting(true);
    setError(null);
    try {
      await api.ingestCompany(t);
      setNotIngested(false);
      await runAssessment(t);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't ingest that ticker — check it's a real, listed symbol.");
    } finally {
      setIngesting(false);
    }
  }

  return (
    <AppShell>
      <main style={{ maxWidth: "720px", margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Growth Hunter</p>
        <h1 style={{ margin: "0.3rem 0 0.75rem" }}>Speculative growth assessment</h1>
        <p style={{ color: "var(--text-soft)", lineHeight: 1.6, marginBottom: "1.75rem", fontSize: "0.95rem" }}>
          A genuinely different kind of analysis from the rest of this platform — built for
          early-stage companies, where standard factor scoring would penalize exactly the
          traits a real growth story starts with. This is a structured breakdown, never a
          score, never a recommendation.
        </p>

        <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
          <input
            type="text"
            placeholder="Ticker, e.g. RXRX"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className="num"
            style={{ flex: 1, padding: "0.6rem 0.9rem", fontSize: "0.95rem", textTransform: "uppercase" }}
          />
          <button type="submit" className="btn-primary" disabled={loading || !ticker.trim()}>
            {loading ? "Assessing…" : "Assess"}
          </button>
        </form>

        {error && (
          <p className="num loss" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>{error}</p>
        )}

        {notIngested && (
          <section className="card" style={{ marginBottom: "1.5rem" }}>
            <p style={{ margin: "0 0 0.75rem" }}>
              {`"${ticker.trim().toUpperCase()}" hasn't been ingested yet — no data to assess. Pull its real financials first?`}
            </p>
            <button className="btn-primary" onClick={handleIngestAndAssess} disabled={ingesting}>
              {ingesting ? "Ingesting…" : "Ingest & assess"}
            </button>
          </section>
        )}

        {assessment && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <section
              className="card"
              style={{
                borderLeft: assessment.growth_trend !== "insufficient_data"
                  ? "3px solid var(--accent)" : "3px dashed var(--rule)",
              }}
            >
              <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Revenue growth trend</p>
              <p style={{ margin: "0 0 0.5rem", fontSize: "1.15rem", fontWeight: 600, color: TREND_COLOR[assessment.growth_trend] }}>
                {TREND_LABEL[assessment.growth_trend]}
              </p>
              <p className="num" style={{ margin: 0, fontSize: "0.9rem", color: "var(--text-soft)" }}>
                Latest year: {fmtPct(assessment.revenue_growth_latest_yoy)} · Prior year: {fmtPct(assessment.revenue_growth_prior_yoy)}
              </p>
              <p className="num" style={{ margin: "0.5rem 0 0", fontSize: "0.78rem", color: "var(--text-soft)" }}>
                Based on {assessment.years_of_data_available} year(s) of available financials
              </p>
            </section>

            <section
              className="card"
              style={{
                borderLeft: assessment.is_profitable !== null
                  ? "3px solid var(--accent)" : "3px dashed var(--rule)",
              }}
            >
              <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Profitability</p>
              <p style={{ margin: 0, fontSize: "1.05rem", fontWeight: 600 }}>
                {assessment.is_profitable === null
                  ? "Unknown — no net income data available"
                  : assessment.is_profitable
                  ? "Profitable"
                  : "Currently unprofitable"}
              </p>
              {assessment.net_income_latest !== null && (
                <p className="num" style={{ margin: "0.4rem 0 0", fontSize: "0.85rem", color: "var(--text-soft)" }}>
                  Latest net income: {fmtMarketCap(assessment.net_income_latest)}
                </p>
              )}
            </section>

            <section
              className="card"
              style={{
                borderLeft: assessment.cash_runway_months !== null
                  ? "3px solid var(--accent)" : "3px dashed var(--rule)",
              }}
            >
              <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Cash runway</p>
              <p style={{ margin: 0, fontSize: "1.05rem", fontWeight: 600 }}>
                {assessment.cash_runway_months === null
                  ? "Not burning cash, or not enough data to tell"
                  : `~${assessment.cash_runway_months.toFixed(0)} months at current burn rate`}
              </p>
            </section>

            <section
              className="card"
              style={{
                borderLeft: assessment.market_cap !== null
                  ? "3px solid var(--accent)" : "3px dashed var(--rule)",
              }}
            >
              <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Market cap</p>
              <p style={{ margin: 0, fontSize: "1.05rem", fontWeight: 600 }}>
                {fmtMarketCap(assessment.market_cap)}
              </p>
            </section>

            <section
              className="card"
              style={{ borderLeft: assessment.risk_flags.length > 0 ? "3px solid var(--loss)" : "3px solid var(--rule)" }}
            >
              <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Risk flags</p>
              {assessment.risk_flags.length === 0 ? (
                <p style={{ margin: 0, fontSize: "0.9rem", color: "var(--text-soft)" }}>
                  None of the specific risks this tool checks for were detected — that is not
                  the same thing as this being safe.
                </p>
              ) : (
                <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
                  {assessment.risk_flags.map((flag) => (
                    <li key={flag} style={{ marginBottom: "0.4rem", fontSize: "0.9rem" }}>{flag}</li>
                  ))}
                </ul>
              )}
            </section>

            <p style={{ fontSize: "0.82rem", color: "var(--text-soft)", lineHeight: 1.6, margin: "0.5rem 0 0" }}>
              This is a structured risk/growth breakdown, not a prediction or a recommendation.
              Genuine large-multiple outcomes are rare; the same traits behind big winners are
              behind total losses too.
            </p>
          </div>
        )}
      </main>
    </AppShell>
  );
}
