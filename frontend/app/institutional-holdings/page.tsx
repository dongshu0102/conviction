"use client";

// Institutional Holdings — real Form 13F data, sourced directly from
// SEC EDGAR's own free, official bulk data sets (not a paid vendor).
// Three real capabilities behind one page, tab-switched rather than
// three separate routes, matching how someone actually uses this: "who
// holds Apple," "what does Berkshire hold," "what changed for
// Berkshire last quarter."
//
// Change-detection is deliberately based on SHARE COUNT, not dollar
// value — confirmed against real production data that a position's
// value can move purely from price with zero actual trading (a real
// filer's stake in a real security held an identical share count
// across two real quarters while its dollar value changed by
// billions). The backend already encodes this; this page just relays
// it honestly via LedgerRow's changePct.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { LedgerRow } from "@/components/LedgerRow";
import {
  api,
  getApiKey,
  ApiError,
  InstitutionalHoldersResponse,
  InstitutionalPortfolioResponse,
  PositionChangesResponse,
  PositionChange,
} from "@/lib/api";

type Mode = "changes" | "holders" | "portfolio";

function fmtUsd(v: number): string {
  if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

// Most people recognize a ticker far more readily than a raw CUSIP,
// but the ticker is a real, separate backfill (not every CUSIP has
// one resolved yet) -- shown alongside the CUSIP, never in place of
// it, so the underlying identifier is always still visible.
function fmtCusipSublabel(cusip: string, ticker: string | null): string {
  return ticker ? `${ticker} · CUSIP ${cusip}` : `CUSIP ${cusip}`;
}

const CHANGE_ORDER = ["new", "increased", "decreased", "closed"] as const;

const CHANGE_LABEL: Record<string, string> = {
  new: "New positions",
  increased: "Increased",
  decreased: "Trimmed",
  closed: "Fully exited",
};

const MODE_LABEL: Record<Mode, string> = {
  changes: "What changed",
  holders: "Who holds this",
  portfolio: "What they hold",
};

const MODE_PLACEHOLDER: Record<Mode, string> = {
  changes: "e.g. Berkshire, FMR, Vanguard",
  holders: "e.g. Apple, Microsoft, Nvidia",
  portfolio: "e.g. Berkshire, Vanguard, FMR",
};

// Sorts by whichever of current/prior value is larger — the row's
// own "size" — rather than by the dollar change itself, which is
// simpler and more predictable to scan.
function rowSize(c: PositionChange): number {
  return Math.max(c.current_value_usd, c.prior_value_usd);
}

export default function InstitutionalHoldingsPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("changes");
  const [query, setQuery] = useState("Berkshire");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [changes, setChanges] = useState<PositionChangesResponse | null>(null);
  const [holders, setHolders] = useState<InstitutionalHoldersResponse | null>(null);
  const [portfolio, setPortfolio] = useState<InstitutionalPortfolioResponse | null>(null);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
    }
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;

    setLoading(true);
    setError(null);
    try {
      if (mode === "changes") {
        setChanges(await api.getPositionChanges(q));
      } else if (mode === "holders") {
        setHolders(await api.getInstitutionalHolders(q));
      } else {
        setPortfolio(await api.getInstitutionalPortfolio(q));
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Couldn't load 13F data");
      }
    } finally {
      setLoading(false);
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
  }

  return (
    <AppShell>
      <main style={{ maxWidth: 720, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Institutional Holdings</p>
        <h1 style={{ margin: "0.3rem 0 0.75rem" }}>Form 13F holdings</h1>
        <p style={{ color: "var(--text-soft)", lineHeight: 1.6, marginBottom: "1.75rem", fontSize: "0.95rem" }}>
          Real institutional holdings, sourced directly from SEC EDGAR&apos;s own free, official
          Form 13F bulk data sets — not a paid vendor. Search by issuer or filer name, not
          ticker: the raw SEC data has no ticker symbol at all. Equity-only, size-thresholded,
          and reported ~45 days after quarter-end, so this is never real-time.
        </p>

        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
          {(Object.keys(MODE_LABEL) as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => switchMode(m)}
              className="num"
              style={{
                padding: "0.5rem 0.9rem",
                fontSize: "0.78rem",
                border: "1px solid var(--rule)",
                borderRadius: "4px",
                background: mode === m ? "var(--accent)" : "transparent",
                color: mode === m ? "#16120e" : "var(--text)",
                fontWeight: mode === m ? 600 : 400,
              }}
            >
              {MODE_LABEL[m]}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
          <input
            type="text"
            placeholder={MODE_PLACEHOLDER[mode]}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ flex: 1, padding: "0.6rem 0.9rem", fontSize: "0.95rem" }}
          />
          <button type="submit" className="btn-primary" disabled={loading || !query.trim()}>
            {loading ? "Searching…" : "Search"}
          </button>
        </form>

        {error && (
          <p className="num loss" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>{error}</p>
        )}

        {mode === "changes" && changes && (
          <>
            <div className="card" style={{ marginBottom: "1.25rem", padding: "0.85rem 1rem" }}>
              <p style={{ margin: 0, fontSize: "0.95rem", fontWeight: 600 }}>
                {changes.filer_name}
              </p>
              <p className="num" style={{ margin: "0.25rem 0 0", fontSize: "0.78rem", color: "var(--text-soft)" }}>
                {changes.prior_period} → {changes.current_period}
              </p>
              {changes.filer_had_no_prior_period_data && (
                <p style={{ margin: "0.6rem 0 0", fontSize: "0.82rem", lineHeight: 1.5, fontWeight: 600 }}>
                  This filer has no 13F on record for the prior quarter — every position below
                  shows as &ldquo;new&rdquo; only because there&apos;s nothing to compare against,
                  most likely because this manager only recently started filing. This is not
                  evidence of a real buying spree.
                </p>
              )}
            </div>

            {changes.changes.length === 0 && (
              <p style={{ color: "var(--text-soft)" }}>No position changes detected.</p>
            )}

            {CHANGE_ORDER.map((changeType) => {
              const rows = changes.changes
                .filter((c) => c.change_type === changeType)
                .sort((a, b) => rowSize(b) - rowSize(a));
              if (rows.length === 0) return null;
              return (
                <div key={changeType} className="card" style={{ marginBottom: "1.25rem" }}>
                  <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
                    {CHANGE_LABEL[changeType]} ({rows.length})
                  </p>
                  {rows.map((c) => (
                    <LedgerRow
                      key={c.cusip}
                      label={c.issuer_name}
                      sublabel={fmtCusipSublabel(c.cusip, c.ticker)}
                      value={fmtUsd(c.current_value_usd || c.prior_value_usd)}
                      changePct={c.pct_change}
                    />
                  ))}
                </div>
              );
            })}
          </>
        )}

        {mode === "holders" && holders && (
          <div className="card">
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
              {`${holders.issuer_name}${holders.holders[0]?.ticker ? ` (${holders.holders[0].ticker})` : ""} · ${holders.period_of_report}`}
            </p>
            {holders.holders.length === 0 ? (
              <p style={{ margin: 0, color: "var(--text-soft)" }}>No holders found.</p>
            ) : (
              holders.holders.map((h, i) => (
                <LedgerRow key={`${h.filer_name}-${i}`} label={h.filer_name} value={fmtUsd(h.value_usd)} />
              ))
            )}
          </div>
        )}

        {mode === "portfolio" && portfolio && (
          <div className="card">
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
              {portfolio.filer_name} · {portfolio.period_of_report}
            </p>
            {portfolio.holdings.length === 0 ? (
              <p style={{ margin: 0, color: "var(--text-soft)" }}>No holdings found.</p>
            ) : (
              portfolio.holdings.map((h, i) => (
                <LedgerRow
                  key={`${h.cusip}-${i}`}
                  label={h.issuer_name}
                  sublabel={fmtCusipSublabel(h.cusip, h.ticker)}
                  value={fmtUsd(h.value_usd)}
                />
              ))
            )}
          </div>
        )}
      </main>
    </AppShell>
  );
}
