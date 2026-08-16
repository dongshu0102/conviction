"use client";

// Conviction Summary — combines three genuinely independent SEC
// disclosure regimes into one, honest view for a single ticker:
// institutional accumulation (top 5 13F holders' own
// quarter-over-quarter change), activist intent (13D filings), and
// insider buying (genuine Form 4 purchases at a real, non-zero
// price). signal_count is a deliberately coarse, honest tally (0-3),
// never presented here as a fabricated, precise composite score.

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, getApiKey, ConvictionSummary } from "@/lib/api";

function fmtUsd(v: number): string {
  if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

function SignalBadge({ label, active }: { label: string; active: boolean }) {
  return (
    <span
      className="num"
      style={{
        padding: "0.3rem 0.7rem", borderRadius: "999px", fontSize: "0.8rem", fontWeight: 700,
        color: active ? "var(--gain)" : "var(--text-soft)",
        border: `1px solid ${active ? "var(--gain)" : "var(--border)"}`,
      }}
    >
      {`${active ? "●" : "○"} ${label}`}
    </span>
  );
}

function ConvictionSummaryForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [ticker, setTicker] = useState(searchParams.get("ticker") || "AAPL");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ConvictionSummary | null>(null);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    // A ticker in the URL (e.g. arriving from the screener's own
    // "click a ticker" links) is auto-searched on load, rather than
    // just pre-filling the box and requiring a second, manual submit.
    const fromUrl = searchParams.get("ticker");
    if (fromUrl) {
      fetchSummary(fromUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  async function fetchSummary(t: string) {
    setLoading(true);
    setError(null);
    try {
      setResult(await api.getConvictionSummary(t));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load the conviction summary");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const t = ticker.trim();
    if (!t) return;
    fetchSummary(t);
  }

  return (
    <AppShell>
      <main style={{ maxWidth: 760, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Signal Summary</p>
        <h1 style={{ margin: "0.3rem 0 0.75rem" }}>Conviction Summary</h1>
        <p style={{ color: "var(--text-soft)", fontSize: "0.9rem", marginBottom: "1.25rem" }}>
          Institutional accumulation, activist intent, and insider buying — three genuinely
          independent SEC disclosure regimes, combined into one honest view.
        </p>

        <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
          <input
            type="text" placeholder="Ticker, e.g. AAPL" value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            style={{ flex: 1, padding: "0.6rem 0.9rem", fontSize: "0.95rem" }}
          />
          <button type="submit" className="btn-primary" disabled={loading || !ticker.trim()}>
            {loading ? "Loading…" : "Search"}
          </button>
        </form>

        {error && (
          <p className="num loss" style={{ fontSize: "0.85rem", marginBottom: "1.25rem" }}>{error}</p>
        )}

        {result && (
          <>
            <div className="card" style={{ marginBottom: "1.25rem" }}>
              <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
                {`${result.ticker} — ${result.signal_count} of 3 signals`}
              </p>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <SignalBadge label="Institutional" active={result.institutional_signal} />
                <SignalBadge label="Activist (13D)" active={result.activist_signal} />
                <SignalBadge label="Insider buying" active={result.insider_signal} />
              </div>
              <p style={{ color: "var(--text-soft)", fontSize: "0.8rem", marginTop: "0.75rem" }}>
                A coarse, honest tally — not a precise composite score. Institutional only
                reflects the top 5 holders, who are often passive index funds; an inactive
                institutional signal doesn&apos;t mean no institution holds this stock.
              </p>
            </div>

            {result.institutional_holders.length > 0 && (
              <div className="card" style={{ marginBottom: "1.25rem" }}>
                <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>Top holders</p>
                {result.institutional_holders.map((h, i) => (
                  <div key={`${h.filer_name}-${i}`} style={{ display: "flex", justifyContent: "space-between", padding: "0.4rem 0", borderTop: i > 0 ? "1px solid var(--border)" : "none" }}>
                    <span className="num">{h.filer_name}</span>
                    <span className="num" style={{ color: h.is_increasing ? "var(--gain)" : "var(--text-soft)" }}>
                      {`${fmtUsd(h.current_value_usd)}${h.is_increasing === true ? " ↑" : h.is_increasing === false ? "" : " (unknown)"}`}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {result.activist_disclosures_13d.length > 0 && (
              <div className="card" style={{ marginBottom: "1.25rem" }}>
                <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>Recent 13D filings</p>
                {result.activist_disclosures_13d.map((d, i) => (
                  <div key={`${d.name_of_reporting_person}-${i}`} style={{ padding: "0.4rem 0", borderTop: i > 0 ? "1px solid var(--border)" : "none" }}>
                    <span className="num">{`${d.name_of_reporting_person} — ${d.filing_date} — ${(d.percent_of_class * 100).toFixed(1)}%`}</span>
                  </div>
                ))}
              </div>
            )}

            {result.insider_purchases.length > 0 && (
              <div className="card">
                <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>Recent insider purchases</p>
                {result.insider_purchases.map((t, i) => (
                  <div key={`${t.reporting_name}-${i}`} style={{ padding: "0.4rem 0", borderTop: i > 0 ? "1px solid var(--border)" : "none" }}>
                    <span className="num">{`${t.reporting_name} — ${t.transaction_date} — ${t.securities_transacted.toLocaleString()} sh @ $${t.price.toFixed(2)}`}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </AppShell>
  );
}

export default function ConvictionSummaryPage() {
  // useSearchParams needs a Suspense boundary in the App Router —
  // without it, the page fails to build/render correctly, same
  // established requirement as reset-password/page.tsx.
  return (
    <Suspense fallback={<p className="num" style={{ color: "var(--text-soft)" }}>Loading…</p>}>
      <ConvictionSummaryForm />
    </Suspense>
  );
}
