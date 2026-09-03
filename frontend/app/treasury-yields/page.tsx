"use client";

// Treasury Yields — the real, current U.S. Treasury yield curve this
// app already fetches and uses internally as a discount-rate input
// for Valuation, now surfaced as its own, dedicated page rather than
// only living inside another page's calculation.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { AppShell } from "@/components/AppShell";
import { api, getApiKey, ApiError, TreasuryRates } from "@/lib/api";

// Ordered short-to-long, matching how a real yield curve is read.
const MATURITIES: { key: keyof TreasuryRates; label: string }[] = [
  { key: "month1", label: "1M" },
  { key: "month2", label: "2M" },
  { key: "month3", label: "3M" },
  { key: "month6", label: "6M" },
  { key: "year1", label: "1Y" },
  { key: "year2", label: "2Y" },
  { key: "year3", label: "3Y" },
  { key: "year5", label: "5Y" },
  { key: "year7", label: "7Y" },
  { key: "year10", label: "10Y" },
  { key: "year20", label: "20Y" },
  { key: "year30", label: "30Y" },
];

function fmtPct(n: number | null): string {
  return n === null ? "—" : `${(n * 100).toFixed(2)}%`;
}

export default function TreasuryYieldsPage() {
  const router = useRouter();
  const [rates, setRates] = useState<TreasuryRates | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    api.getTreasuryRates()
      .then(setRates)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        setError(err instanceof Error ? err.message : "Couldn't load Treasury rates");
      })
      .finally(() => setLoading(false));
  }, [router]);

  const chartData = rates
    ? MATURITIES.map((m) => ({
        maturity: m.label,
        // recharts plots raw numbers on its own axis, so this is
        // converted to a plain percentage (4.69, not 0.0469) here —
        // the rest of the page still shows the real, decimal
        // convention this codebase uses everywhere else.
        yield: rates[m.key] !== null ? (rates[m.key] as number) * 100 : null,
      }))
    : [];

  // A genuine, real 10Y-minus-2Y inversion is a well-known recession
  // signal -- flagged here directly since it's the single most
  // commonly watched point on the real curve.
  const isInverted =
    rates?.year10 !== null && rates?.year10 !== undefined &&
    rates?.year2 !== null && rates?.year2 !== undefined &&
    rates.year10 < rates.year2;

  return (
    <AppShell>
      <main style={{ maxWidth: "900px", margin: "0 auto", padding: "2rem 1.5rem" }}>
        <h1 style={{ margin: "0 0 0.25rem", fontSize: "1.4rem" }}>Treasury Yields</h1>
        <p style={{ color: "var(--text-soft)", fontSize: "0.85rem", marginBottom: "1.25rem" }}>
          The real, current U.S. Treasury yield curve — the market&rsquo;s own real-time
          proxy for the risk-free rate, already used internally as a discount-rate
          input for Valuation.
        </p>

        {loading && <p style={{ color: "var(--text-soft)" }}>Loading…</p>}
        {error && <p className="num loss" style={{ fontSize: "0.85rem" }}>{error}</p>}

        {rates && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
              <p className="eyebrow" style={{ fontSize: "0.68rem", margin: 0 }}>
                As of {rates.as_of}
              </p>
              {isInverted && (
                <span className="num loss" style={{ fontSize: "0.78rem" }}>
                  10Y &lt; 2Y — inverted (a real, commonly watched recession signal)
                </span>
              )}
            </div>

            <div className="card" style={{ marginBottom: "1.25rem", height: "320px" }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 16, right: 24, bottom: 8, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--rule)" />
                  <XAxis dataKey="maturity" tick={{ fontSize: 11 }} stroke="var(--text-soft)" />
                  <YAxis
                    tick={{ fontSize: 11 }} stroke="var(--text-soft)"
                    tickFormatter={(v) => `${v.toFixed(1)}%`}
                    domain={["auto", "auto"]}
                  />
                  <Tooltip
                    formatter={(value) => [
                      typeof value === "number" ? `${value.toFixed(2)}%` : "—", "Yield",
                    ]}
                    contentStyle={{ fontSize: "0.8rem" }}
                  />
                  <Line
                    type="monotone" dataKey="yield" stroke="var(--accent)"
                    strokeWidth={2} dot={{ r: 3 }} connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="card">
              <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>By maturity</p>
              <table className="num" style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.85rem" }}>
                <thead>
                  <tr style={{ textAlign: "right", color: "var(--text-soft)", fontSize: "0.68rem", letterSpacing: "0.05em" }}>
                    <th style={{ textAlign: "left", padding: "0.3rem 0.4rem" }}>MATURITY</th>
                    <th style={{ padding: "0.3rem 0.4rem" }}>YIELD</th>
                  </tr>
                </thead>
                <tbody>
                  {MATURITIES.map((m) => (
                    <tr key={m.key} style={{ borderTop: "1px solid var(--rule)" }}>
                      <td style={{ padding: "0.4rem", textAlign: "left" }}>{m.label}</td>
                      <td style={{ padding: "0.4rem", textAlign: "right", fontWeight: 600 }}>
                        {fmtPct(rates[m.key] as number | null)}
                      </td>
                    </tr>
                  ))}
                  <tr style={{ borderTop: "1px solid var(--rule)" }}>
                    <td style={{ padding: "0.4rem", textAlign: "left", color: "var(--text-soft)" }}>
                      Suggested discount rate
                    </td>
                    <td style={{ padding: "0.4rem", textAlign: "right", fontWeight: 600 }}>
                      {fmtPct(rates.suggested_discount_rate)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </>
        )}
      </main>
    </AppShell>
  );
}
