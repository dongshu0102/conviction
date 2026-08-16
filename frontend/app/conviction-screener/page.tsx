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

function fmtAsOf(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function ConvictionScreenerPage() {
  const router = useRouter();
  const [minSignalCount, setMinSignalCount] = useState(1);
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

        {results && results.length === 0 && !loading && (
          <p style={{ color: "var(--text-soft)", fontSize: "0.9rem" }}>
            No stored results yet at this threshold. Trigger a scan above, then check back —
            a full S&P 500 scan takes a while to complete.
          </p>
        )}

        {results && results.length > 0 && (
          <div className="card">
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
              {`${results.length} tickers — as of ${fmtAsOf(results[0].as_of)}`}
            </p>
            {results.map((r, i) => (
              <Link
                key={r.ticker}
                href={`/conviction-summary?ticker=${r.ticker}`}
                style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "0.6rem 0", borderTop: i > 0 ? "1px solid var(--border)" : "none",
                  textDecoration: "none", color: "inherit",
                }}
              >
                <span className="num" style={{ fontWeight: 700 }}>{r.ticker}</span>
                <span style={{ display: "flex", gap: "0.35rem" }}>
                  <span style={{ color: r.institutional_signal ? "var(--gain)" : "var(--border)" }}>●</span>
                  <span style={{ color: r.activist_signal ? "var(--gain)" : "var(--border)" }}>●</span>
                  <span style={{ color: r.insider_signal ? "var(--gain)" : "var(--border)" }}>●</span>
                  <span className="num" style={{ marginLeft: "0.5rem", fontSize: "0.85rem" }}>{`${r.signal_count}/3`}</span>
                </span>
              </Link>
            ))}
          </div>
        )}
      </main>
    </AppShell>
  );
}
