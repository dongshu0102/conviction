"use client";

// SEC Research — combines 13F institutional holders, 13D/13G
// beneficial ownership disclosures, and Form 3/4/5 insider
// transactions for a single ticker into one page, so researching a
// stock across all three SEC disclosure regimes doesn't require
// navigating between three separate pages. The full-detail companion
// to Conviction Summary's own, coarser 0-3 signal tally.
//
// Each of the three sections fetches and fails independently — a
// ticker with no 13F coverage still shows its 13D/13G and insider
// data, matching the same "never let one source's failure hide the
// others" principle already established for GetConvictionSummaryUseCase
// on the backend.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { TickerAutocomplete } from "@/components/TickerAutocomplete";
import {
  api, getApiKey, CompanyListItem,
  InstitutionalHolding, BeneficialOwnershipDisclosure, InsiderTransaction,
} from "@/lib/api";

function fmtUsd(v: number): string {
  if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

interface SectionState<T> {
  loading: boolean;
  error: string | null;
  data: T[] | null;
}

const EMPTY_SECTION = { loading: false, error: null, data: null };

export default function SecResearchPage() {
  const router = useRouter();
  const [ticker, setTicker] = useState("");
  const [companies, setCompanies] = useState<CompanyListItem[]>([]);
  const [searchedTicker, setSearchedTicker] = useState<string | null>(null);

  const [holders, setHolders] = useState<SectionState<InstitutionalHolding>>(EMPTY_SECTION);
  const [disclosures, setDisclosures] = useState<SectionState<BeneficialOwnershipDisclosure>>(EMPTY_SECTION);
  const [transactions, setTransactions] = useState<SectionState<InsiderTransaction>>(EMPTY_SECTION);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    api.getCompanyList().then((r) => setCompanies(r.companies)).catch(() => {});
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setSearchedTicker(t);

    const company = companies.find((c) => c.ticker === t);

    // 13F holders — a real, ground-truth CUSIP for this ticker comes
    // out of this call (every holding of the same issuer shares one
    // CUSIP), reused below to validate the 13D/13G results, same
    // real, confirmed fix already shipped for Conviction Summary.
    setHolders({ loading: true, error: null, data: null });
    let groundTruthCusip: string | null = null;
    try {
      if (!company) {
        throw new Error(`${t} isn't in this app's own, ingested company list yet — try the exact company name search on the 13F Holdings page instead.`);
      }
      const r = await api.getInstitutionalHolders(company.name, 10);
      setHolders({ loading: false, error: null, data: r.holders });
      groundTruthCusip = r.holders[0]?.cusip ?? null;
    } catch (err) {
      setHolders({ loading: false, error: err instanceof Error ? err.message : "Couldn't load 13F holders", data: null });
    }

    // 13D/13G disclosures
    setDisclosures({ loading: true, error: null, data: null });
    try {
      const r = await api.getBeneficialOwnershipDisclosures(t);
      // Real, confirmed bug fix, same as Conviction Summary: large
      // institutions that are themselves active 13D/13G filers (e.g.
      // JPMorgan Chase) can show up as filer on disclosures about a
      // completely different company. A disclosure whose own CUSIP
      // doesn't match this ticker's real, ground-truth CUSIP is
      // filtered out — see get_conviction_summary.py's own,
      // identical fix for the full, real-world confirmation.
      const filtered = groundTruthCusip
        ? r.disclosures.filter((d) => d.cusip === groundTruthCusip)
        : r.disclosures;
      setDisclosures({ loading: false, error: null, data: filtered });
    } catch (err) {
      setDisclosures({ loading: false, error: err instanceof Error ? err.message : "Couldn't load 13D/13G disclosures", data: null });
    }

    // Insider transactions
    setTransactions({ loading: true, error: null, data: null });
    try {
      const r = await api.getInsiderTransactions(t);
      setTransactions({ loading: false, error: null, data: r.transactions });
    } catch (err) {
      setTransactions({ loading: false, error: err instanceof Error ? err.message : "Couldn't load insider transactions", data: null });
    }
  }

  return (
    <AppShell>
      <main style={{ maxWidth: 780, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>SEC Research</p>
        <h1 style={{ margin: "0.3rem 0 0.75rem" }}>13F, 13D/13G &amp; insider trades</h1>
        <p style={{ color: "var(--text-soft)", fontSize: "0.9rem", marginBottom: "1.25rem" }}>
          Full detail from all three SEC disclosure sources for one ticker, side by side —
          the detailed companion to Conviction Summary's own, coarser 0-3 signal tally.
        </p>

        <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
          <TickerAutocomplete value={ticker} onChange={setTicker} placeholder="e.g. AAPL, JPM, RBLX" />
          <button type="submit" className="btn-primary" disabled={!ticker.trim()}>Search</button>
        </form>

        {searchedTicker && (
          <>
            <section className="card" style={{ marginBottom: "1.25rem" }}>
              <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
                {`13F — top holders of ${searchedTicker}`}
              </p>
              {holders.loading && <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>Loading…</p>}
              {holders.error && <p className="num loss" style={{ fontSize: "0.85rem" }}>{holders.error}</p>}
              {holders.data && holders.data.length === 0 && (
                <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>No 13F holdings found.</p>
              )}
              {holders.data && holders.data.map((h, i) => (
                <div key={`${h.filer_name}-${i}`} style={{ display: "flex", justifyContent: "space-between", padding: "0.4rem 0", borderTop: i > 0 ? "1px solid var(--border)" : "none" }}>
                  <span className="num">{h.filer_name}</span>
                  <span className="num">{fmtUsd(h.value_usd)}</span>
                </div>
              ))}
            </section>

            <section className="card" style={{ marginBottom: "1.25rem" }}>
              <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
                {`13D / 13G — beneficial ownership of ${searchedTicker}`}
              </p>
              {disclosures.loading && <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>Loading…</p>}
              {disclosures.error && <p className="num loss" style={{ fontSize: "0.85rem" }}>{disclosures.error}</p>}
              {disclosures.data && disclosures.data.length === 0 && (
                <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>No 13D/13G disclosures found.</p>
              )}
              {disclosures.data && disclosures.data.slice(0, 15).map((d, i) => (
                <div key={`${d.name_of_reporting_person}-${i}`} style={{ display: "flex", justifyContent: "space-between", padding: "0.4rem 0", borderTop: i > 0 ? "1px solid var(--border)" : "none" }}>
                  <span className="num">{d.name_of_reporting_person}</span>
                  <span className="num" style={{ color: d.type_of_reporting_person === "13D" ? "var(--gain)" : "var(--text-soft)" }}>
                    {`${(d.percent_of_class * 100).toFixed(1)}% — ${d.filing_date}`}
                  </span>
                </div>
              ))}
            </section>

            <section className="card">
              <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
                {`Insider trades — ${searchedTicker}`}
              </p>
              {transactions.loading && <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>Loading…</p>}
              {transactions.error && <p className="num loss" style={{ fontSize: "0.85rem" }}>{transactions.error}</p>}
              {transactions.data && transactions.data.length === 0 && (
                <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>No insider transactions found.</p>
              )}
              {transactions.data && transactions.data.slice(0, 15).map((t, i) => (
                <div key={`${t.reporting_name}-${i}`} style={{ display: "flex", justifyContent: "space-between", padding: "0.4rem 0", borderTop: i > 0 ? "1px solid var(--border)" : "none" }}>
                  <span className="num">{t.reporting_name}</span>
                  <span className="num" style={{ color: t.price === 0 ? "var(--text-soft)" : t.transaction_type === "P-Purchase" ? "var(--gain)" : "var(--text-soft)" }}>
                    {t.price === 0
                      ? `${t.transaction_type} — ${t.transaction_date}`
                      : `${t.transaction_type} $${t.price.toFixed(2)} — ${t.transaction_date}`}
                  </span>
                </div>
              ))}
            </section>
          </>
        )}
      </main>
    </AppShell>
  );
}
