"use client";

// Form 3/4/5 insider transactions — every reported transaction by a
// company's officers, directors, and 10%+ owners in their own
// company's stock, most recent first. Genuinely different from
// 13D/13G: this is an insider's own trading activity, not a separate
// party crossing 5% ownership, and Form 4 is filed within 2 business
// days of the transaction — the fastest of the SEC filings this
// platform covers. Always live from FMP; no free, structured SEC
// bulk data set exists for these forms.
//
// price can be genuinely 0 — this is NOT missing data. Confirmed
// directly against real data: option-exercise and RSU-vesting events
// ("M-Exempt") report price=0 because they're routine, scheduled
// compensation events, not discretionary trades. A real purchase
// ("P-Purchase") or sale ("S-Sale") at a genuine, non-zero price is a
// materially stronger, different signal, and this page never presents
// a price=0 row as if it were a discretionary buy or sell decision.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, getApiKey, ApiError, InsiderTransactionsResponse } from "@/lib/api";

function fmtShares(v: number): string {
  return v.toLocaleString();
}

function fmtPrice(v: number): string {
  return v > 0 ? `$${v.toFixed(2)}` : "—";
}

export default function InsiderTransactionsPage() {
  const router = useRouter();
  const [ticker, setTicker] = useState("AAPL");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InsiderTransactionsResponse | null>(null);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
    }
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const t = ticker.trim();
    if (!t) return;

    setLoading(true);
    setError(null);
    try {
      setResult(await api.getInsiderTransactions(t));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Couldn't load insider transactions");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell>
      <main style={{ maxWidth: 720, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Insider Transactions</p>
        <h1 style={{ margin: "0.3rem 0 0.75rem" }}>Form 3/4/5 insider transactions</h1>
        <p style={{ color: "var(--text-soft)", lineHeight: 1.6, marginBottom: "1.75rem", fontSize: "0.95rem" }}>
          Officers, directors, and 10%+ owners buying, selling, or otherwise changing their
          reported holdings in their own company&apos;s stock. Always live from FMP — no free,
          structured SEC bulk data set exists for these forms. A dash (—) means price=0 — a
          real, honest reflection of option exercises or RSU vesting, not missing data, and not
          the same as a real, discretionary purchase or sale. Search by ticker.
        </p>

        <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
          <input
            type="text"
            placeholder="e.g. AAPL, TSLA, MSFT"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            style={{ flex: 1, padding: "0.6rem 0.9rem", fontSize: "0.95rem" }}
          />
          <button type="submit" className="btn-primary" disabled={loading || !ticker.trim()}>
            {loading ? "Searching…" : "Search"}
          </button>
        </form>

        {error && (
          <p className="num loss" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>{error}</p>
        )}

        {result && (
          <div className="card">
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
              {`${result.ticker} · ${result.transactions.length} transaction${result.transactions.length === 1 ? "" : "s"}`}
            </p>
            {result.transactions.length === 0 ? (
              <p style={{ margin: 0, color: "var(--text-soft)" }}>No insider transactions found.</p>
            ) : (
              result.transactions.map((t, i) => (
                <div
                  key={`${t.reporting_cik}-${t.filing_date}-${i}`}
                  style={{
                    display: "flex", justifyContent: "space-between", alignItems: "baseline",
                    padding: "0.85rem 0", borderBottom: "1px solid var(--rule)",
                  }}
                >
                  <div>
                    <p style={{ margin: 0, fontSize: "0.95rem" }}>
                      <span
                        className="num"
                        style={{
                          fontSize: "0.7rem", fontWeight: 700, marginRight: "0.5rem",
                          color:
                            t.price === 0
                              ? "var(--text-soft)"
                              : t.acquisition_or_disposition === "A"
                              ? "var(--gain)"
                              : "var(--loss)",
                        }}
                      >
                        {t.transaction_type}
                      </span>
                      {t.reporting_name}
                    </p>
                    <p className="num" style={{ margin: "0.25rem 0 0", fontSize: "0.78rem", color: "var(--text-soft)" }}>
                      {`${t.type_of_owner} · Filed ${t.filing_date} · ${fmtShares(t.securities_transacted)} shares`}
                    </p>
                  </div>
                  <span className="num" style={{ fontSize: "0.95rem" }}>{fmtPrice(t.price)}</span>
                </div>
              ))
            )}
          </div>
        )}
      </main>
    </AppShell>
  );
}
