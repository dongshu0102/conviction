"use client";

// Growth Leaders — Path A: the "common feature." Reuses the existing
// factor-rankings endpoint (already supports arbitrary per-factor
// weights) with growth weighted at 1.0 and everything else at 0, so
// this needed zero new backend work — just a focused view onto data
// that already existed. Universe-wide, not theme-scoped, unlike the
// rest of the Universe page below it.
//
// Deliberately labeled with a realistic ceiling, not hype — this is
// the strongest growth names already inside the S&P 500 (established,
// liquid, profitable-by-index-membership-rules companies), not a
// hunt for 100x candidates. That's Path B, a genuinely different tool.

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, RankedFactorScore } from "@/lib/api";

function fmtPct(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
}

export function GrowthLeaders() {
  const [rankings, setRankings] = useState<RankedFactorScore[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getFactorRankings(10, {
        weight_growth: 1, weight_value: 0, weight_quality: 0, weight_momentum: 0, weight_size: 0,
      })
      .then((res) => setRankings(res.results))
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load growth leaders"));
  }, []);

  return (
    <section className="card" style={{ marginBottom: "1.75rem" }}>
      <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Growth Leaders</p>
      <p style={{ margin: "0 0 1rem", color: "var(--text-soft)", fontSize: "0.85rem", lineHeight: 1.5 }}>
        The strongest revenue-growth names already in the S&amp;P 500, ranked purely on
        growth — not the blended composite score used elsewhere. Realistic ceiling here
        is a great multi-year run, not a moonshot; for that,{" "}
        <Link href="/chat" style={{ color: "var(--accent)" }}>ask Chat about speculative growth</Link> instead.
      </p>

      {error && <p className="num loss" style={{ fontSize: "0.85rem" }}>{error}</p>}
      {!error && rankings === null && (
        <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>Loading…</p>
      )}
      {rankings && rankings.length === 0 && (
        <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>No ranked data available right now.</p>
      )}
      {rankings && rankings.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {rankings.map((r, i) => (
            <div
              key={r.ticker}
              style={{
                display: "flex", alignItems: "center", gap: "0.75rem",
                padding: "0.5rem 0.25rem", borderBottom: i < rankings.length - 1 ? "1px solid var(--rule)" : "none",
              }}
            >
              <span className="num" style={{ width: "1.5rem", color: "var(--text-soft)", fontSize: "0.8rem" }}>
                {i + 1}
              </span>
              <span className="num" style={{ fontWeight: 600, width: "4.5rem" }}>{r.ticker}</span>
              <span className="num gain" style={{ fontSize: "0.9rem" }}>
                {fmtPct(r.raw.revenue_growth_yoy)} rev growth
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
