"use client";

// Schedule 13D/13G beneficial ownership disclosures — genuinely
// different from Form 13F: security-level, not manager-level, and
// within days of a 5%-ownership-crossing event (5 business days for
// the initial filing, 2 business days for a material amendment, per
// the SEC's 2023 amendments) rather than up to 45 days late. Always
// live from FMP; no free SEC bulk data set exists for these schedules
// the way it does for 13F, so there's no local database behind this
// page at all.
//
// form_type is the single most important field: "13D" means the
// filer stated a purpose that could include influencing management or
// control (Item 4) — real, possible activist intent. "13G" is the
// shorter form for passive investors, index funds, and qualified
// institutions with no such stated intent — most large index
// managers' routine stakes (Vanguard, BlackRock) file as 13G, not
// 13D. Confirmed directly against real data: Vanguard Capital
// Management's routine, passive Apple stake files as 13G; Temasek
// Capital's real stake in e2open (a real, reported Elliott Management
// activist situation) files as 13D.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { TickerAutocomplete } from "@/components/TickerAutocomplete";
import { api, getApiKey, ApiError, BeneficialOwnershipDisclosuresResponse } from "@/lib/api";

function fmtPct(v: number): string {
  return `${(v * 100).toFixed(2)}%`;
}

function fmtShares(v: number): string {
  return v.toLocaleString();
}

export default function BeneficialOwnershipPage() {
  const router = useRouter();
  const [ticker, setTicker] = useState("AAPL");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BeneficialOwnershipDisclosuresResponse | null>(null);

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
      setResult(await api.getBeneficialOwnershipDisclosures(t));
    } catch (err) {
      setResult(null); // don't leave a stale, previous result showing alongside a new error
      if (err instanceof ApiError && err.status === 404) {
        setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Couldn't load 13D/13G disclosures");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell>
      <main style={{ maxWidth: 720, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Beneficial Ownership</p>
        <h1 style={{ margin: "0.3rem 0 0.75rem" }}>Schedule 13D/13G disclosures</h1>
        <p style={{ color: "var(--text-soft)", lineHeight: 1.6, marginBottom: "1.75rem", fontSize: "0.95rem" }}>
          Who has crossed 5% beneficial ownership of a security, and whether they stated
          activist intent (13D) or not (13G). Always live from FMP — no free SEC bulk data
          set exists for these schedules the way it does for Form 13F, so this is never
          stale. Search by ticker.
        </p>

        <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
          <TickerAutocomplete
            value={ticker}
            onChange={setTicker}
            placeholder="e.g. AAPL, ETWO, DIS"
          />
          <button type="submit" className="btn-primary" disabled={loading || !ticker.trim()}>
            {loading ? "Searching…" : "Search"}
          </button>
        </form>

        {error && (
          <p className="num loss" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>{error}</p>
        )}

        {loading && (
          <p style={{ color: "var(--text-soft)", fontSize: "0.9rem" }}>Loading 13D/13G disclosures…</p>
        )}

        {!loading && result && (
          <div className="card">
            <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
              {`${result.ticker} · ${result.disclosures.length} disclosure${result.disclosures.length === 1 ? "" : "s"}`}
            </p>
            {result.disclosures.length === 0 ? (
              <p style={{ margin: 0, color: "var(--text-soft)" }}>No 13D/13G disclosures found.</p>
            ) : (
              result.disclosures.map((d, i) => (
                <div
                  key={`${d.cik}-${d.filing_date}-${i}`}
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
                          color: d.form_type === "13D" ? "var(--accent)" : "var(--text-soft)",
                        }}
                      >
                        {d.form_type}
                      </span>
                      {d.name_of_reporting_person}
                    </p>
                    <p className="num" style={{ margin: "0.25rem 0 0", fontSize: "0.78rem", color: "var(--text-soft)" }}>
                      {`Filed ${d.filing_date} · ${fmtShares(d.amount_beneficially_owned)} shares`}
                    </p>
                  </div>
                  <span className="num" style={{ fontSize: "0.95rem" }}>{fmtPct(d.percent_of_class)}</span>
                </div>
              ))
            )}
          </div>
        )}
      </main>
    </AppShell>
  );
}
