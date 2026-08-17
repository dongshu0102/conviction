"use client";

// Market-wide Conviction Summary screener — browses the stored
// results from the most recent full S&P 500 background scan (see
// GET /conviction-summary/screen-results). Never computes live; the
// "Run new scan" action triggers a genuinely expensive (~4,000 live
// API calls, tens of minutes) background job on the server, admin-only.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { api, getApiKey, ConvictionScreenerResult } from "@/lib/api";

const RESULTS_PER_PAGE = 25;
const CATEGORY_OPTIONS = ["All", "S&P 500", "Nasdaq-100", "Dow Jones"];

function fmtAsOf(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function ConvictionScreenerPage() {
  const router = useRouter();
  const [minSignalCount, setMinSignalCount] = useState(1);
  const [category, setCategory] = useState("All");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<ConvictionScreenerResult[] | null>(null);
  const [triggerMessage, setTriggerMessage] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    loadResults(minSignalCount);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  async function loadResults(threshold: number) {
    setLoading(true);
    setError(null);
    try {
      const r = await api.getConvictionScreenResults(threshold);
      setResults(r.results);
      setPage(1); // a fresh load always starts back at page 1
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load the screener results");
    } finally {
      setLoading(false);
    }
  }

  async function handleTriggerScan() {
    setTriggering(true);
    setTriggerMessage(null);
    try {
      const r = await api.triggerConvictionScreen();
      setTriggerMessage(r.message);
    } catch (err) {
      setTriggerMessage(err instanceof Error ? err.message : "Couldn't start the scan");
    } finally {
      setTriggering(false);
    }
  }

  // Category filtering happens client-side, same as pagination — the
  // full result set is already fetched in one call, and re-fetching
  // from the server for a filter this cheap would just be slower.
  const filteredResults = results?.filter(
    (r) => category === "All" || r.index_memberships.includes(category)
  ) ?? null;
  const totalPages = filteredResults ? Math.max(1, Math.ceil(filteredResults.length / RESULTS_PER_PAGE)) : 1;
  const pageResults = filteredResults?.slice((page - 1) * RESULTS_PER_PAGE, page * RESULTS_PER_PAGE) ?? null;

  return (
    <AppShell>
      <main style={{ maxWidth: 760, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Screener</p>
        <h1 style={{ margin: "0.3rem 0 0.75rem" }}>Conviction Screener</h1>
        <p style={{ color: "var(--text-soft)", fontSize: "0.9rem", marginBottom: "1.25rem" }}>
          Stored results from the most recent full S&P 500 scan — never computed live. Each row
          is a lightweight summary; click a ticker for its full detail.
        </p>

        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "1.25rem", flexWrap: "wrap" }}>
          <label style={{ fontSize: "0.85rem", color: "var(--text-soft)" }}>Minimum signals:</label>
          <select
            value={minSignalCount}
            onChange={(e) => {
              const v = Number(e.target.value);
              setMinSignalCount(v);
              loadResults(v);
            }}
            style={{ padding: "0.4rem 0.6rem" }}
          >
            <option value={0}>0 (show all)</option>
            <option value={1}>1+</option>
            <option value={2}>2+</option>
            <option value={3}>3 (all signals)</option>
          </select>

          <label style={{ fontSize: "0.85rem", color: "var(--text-soft)", marginLeft: "0.5rem" }}>Category:</label>
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setPage(1); // a new filter always starts back at page 1
            }}
            style={{ padding: "0.4rem 0.6rem" }}
          >
            {CATEGORY_OPTIONS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>

          <button type="button" onClick={handleTriggerScan} disabled={triggering} style={{ marginLeft: "auto" }}>
            {triggering ? "Starting…" : "Run new scan"}
          </button>
        </div>

        {triggerMessage && (
          <p className="num" style={{ fontSize: "0.8rem", color: "var(--text-soft)", marginBottom: "1.25rem" }}>
            {triggerMessage}
          </p>
        )}

        {loading && <p style={{ fontSize: "0.9rem" }}>Loading…</p>}
        {error && <p className="num loss" style={{ fontSize: "0.85rem" }}>{error}</p>}

        {filteredResults && filteredResults.length === 0 && !loading && (
          <p style={{ color: "var(--text-soft)", fontSize: "0.9rem" }}>
            {results && results.length > 0
              ? `No results in "${category}" at this signal threshold.`
              : "No stored results yet at this threshold. Trigger a scan above, then check back — a full scan takes a while to complete."}
          </p>
        )}

        {pageResults && pageResults.length > 0 && (
          <div className="card">
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
              {`${filteredResults!.length} tickers — as of ${fmtAsOf(pageResults[0].as_of)} — page ${page} of ${totalPages}`}
            </p>
            {pageResults.map((r, i) => (
              <Link
                key={r.ticker}
                href={`/conviction-summary?ticker=${r.ticker}`}
                style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "0.6rem 0", borderTop: i > 0 ? "1px solid var(--border)" : "none",
                  textDecoration: "none", color: "inherit",
                }}
              >
                <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span className="num" style={{ fontWeight: 700 }}>{r.ticker}</span>
                  {r.index_memberships.map((idx) => (
                    <span
                      key={idx}
                      className="num"
                      style={{
                        fontSize: "0.68rem", color: "var(--text-soft)", border: "1px solid var(--border)",
                        borderRadius: "3px", padding: "0.05rem 0.35rem",
                      }}
                    >
                      {idx}
                    </span>
                  ))}
                </span>
                <span style={{ display: "flex", gap: "0.35rem" }}>
                  <span style={{ color: r.institutional_signal ? "var(--gain)" : "var(--border)" }}>●</span>
                  <span style={{ color: r.activist_signal ? "var(--gain)" : "var(--border)" }}>●</span>
                  <span style={{ color: r.insider_signal ? "var(--gain)" : "var(--border)" }}>●</span>
                  <span className="num" style={{ marginLeft: "0.5rem", fontSize: "0.85rem" }}>{`${r.signal_count}/3`}</span>
                </span>
              </Link>
            ))}

            {totalPages > 1 && (
              <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "1rem", marginTop: "1rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border)" }}>
                <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
                  ← Prev
                </button>
                <span className="num" style={{ fontSize: "0.85rem", color: "var(--text-soft)" }}>{`${page} / ${totalPages}`}</span>
                <button type="button" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>
                  Next →
                </button>
              </div>
            )}
          </div>
        )}
      </main>
    </AppShell>
  );
}
