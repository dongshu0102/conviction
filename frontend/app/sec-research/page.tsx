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
  InstitutionalHolding, BeneficialOwnershipDisclosure, InsiderTransaction, ConvictionSummary,
} from "@/lib/api";

function fmtUsd(v: number): string {
  if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

// The largest, broadest index managers show up as top holders of
// nearly every stock — their "position" is often just index inflows,
// not a deliberate bet. Flagged here so that's obvious at a glance,
// not something a reader has to already know.
const LIKELY_PASSIVE_MANAGERS = ["VANGUARD", "BLACKROCK", "STATE STREET", "GEODE"];
function isLikelyPassiveManager(filerName: string): boolean {
  const upper = filerName.toUpperCase();
  return LIKELY_PASSIVE_MANAGERS.some((name) => upper.includes(name));
}

// Plain-English translations of raw, as-filed SEC transaction codes —
// see InsiderTransaction's own transaction_type field docs for why
// this is never a fixed enum (real data has shown codes not
// previously seen). Falls back to the raw code itself for anything
// not in this list, rather than hiding or guessing at an unfamiliar one.
const TRANSACTION_TYPE_LABELS: Record<string, string> = {
  "P-Purchase": "Purchase — real, discretionary signal",
  "S-Sale": "Sale",
  "G-Gift": "Gift — not a market transaction",
  "A-Award": "Award — compensation, not open-market",
  "M-Exempt": "Option exercise / RSU vesting — routine",
  "F-InKind": "Tax withholding — routine",
  "D-Return": "Return to issuer",
  "C-Conversion": "Conversion of a derivative security",
};
function translateTransactionType(code: string): string {
  return TRANSACTION_TYPE_LABELS[code] ?? code;
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
  const [summary, setSummary] = useState<{ loading: boolean; error: string | null; data: ConvictionSummary | null }>(
    { loading: false, error: null, data: null },
  );

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

    // Conviction Summary tally — the fast, quick answer, fetched
    // first and independently of the three detailed sections below.
    setSummary({ loading: true, error: null, data: null });
    api.getConvictionSummary(t)
      .then((r) => setSummary({ loading: false, error: null, data: r }))
      .catch((err) => setSummary({ loading: false, error: err instanceof Error ? err.message : "Couldn't load the conviction summary", data: null }));

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
            <section className="card" style={{ marginBottom: "1.25rem", borderLeft: "3px solid var(--accent)" }}>
              <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
                {`Conviction Summary — ${searchedTicker}`}
              </p>
              {summary.loading && <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>Loading…</p>}
              {summary.error && <p className="num loss" style={{ fontSize: "0.85rem" }}>{summary.error}</p>}
              {summary.data && (
                <>
                  <p style={{ margin: "0 0 0.5rem" }}>{`${summary.data.signal_count} of 3 signals`}</p>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <span className="num" style={{ color: summary.data.institutional_signal ? "var(--gain)" : "var(--text-soft)" }}>
                      {`${summary.data.institutional_signal ? "●" : "○"} Institutional`}
                    </span>
                    <span className="num" style={{ color: summary.data.activist_signal ? "var(--gain)" : "var(--text-soft)" }}>
                      {`${summary.data.activist_signal ? "●" : "○"} Activist (13D)`}
                    </span>
                    <span className="num" style={{ color: summary.data.insider_signal ? "var(--gain)" : "var(--text-soft)" }}>
                      {`${summary.data.insider_signal ? "●" : "○"} Insider buying`}
                    </span>
                  </div>
                  <p style={{ color: "var(--text-soft)", fontSize: "0.8rem", marginTop: "0.5rem" }}>
                    A coarse, honest tally, not a precise composite score — full detail in the three sections below.
                  </p>
                </>
              )}
            </section>

            <section className="card" style={{ marginBottom: "1.25rem" }}>
              <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.15rem" }}>
                {`13F — top holders of ${searchedTicker}`}
              </p>
              <p style={{ color: "var(--text-soft)", fontSize: "0.75rem", marginBottom: "0.5rem" }}>
                Quarterly, can be up to 45 days late
              </p>
              {holders.loading && <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>Loading…</p>}
              {holders.error && <p className="num loss" style={{ fontSize: "0.85rem" }}>{holders.error}</p>}
              {holders.data && holders.data.length === 0 && (
                <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>No 13F holdings found.</p>
              )}
              {holders.data && holders.data.map((h, i) => (
                <div key={`${h.filer_name}-${i}`} style={{ display: "flex", justifyContent: "space-between", padding: "0.4rem 0", borderTop: i > 0 ? "1px solid var(--border)" : "none" }}>
                  <span className="num" style={{ color: h.filer_name ? "inherit" : "var(--text-soft)" }}>
                    {h.filer_name || "(filer name not provided by source)"}
                    {h.filer_name && isLikelyPassiveManager(h.filer_name) && (
                      <span style={{ color: "var(--text-soft)", fontSize: "0.78rem" }}> (often passive)</span>
                    )}
                  </span>
                  <span className="num">{fmtUsd(h.value_usd)}</span>
                </div>
              ))}
            </section>

            <section className="card" style={{ marginBottom: "1.25rem" }}>
              <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.15rem" }}>
                {`13D / 13G — beneficial ownership of ${searchedTicker}`}
              </p>
              <p style={{ color: "var(--text-soft)", fontSize: "0.75rem", marginBottom: "0.5rem" }}>
                Filed within 5 business days of crossing 5% or a material change
              </p>
              {disclosures.loading && <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>Loading…</p>}
              {disclosures.error && <p className="num loss" style={{ fontSize: "0.85rem" }}>{disclosures.error}</p>}
              {disclosures.data && disclosures.data.length === 0 && (
                <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>No 13D/13G disclosures found.</p>
              )}
              {disclosures.data && disclosures.data.slice(0, 15).map((d, i) => {
                const isActivist = d.form_type === "13D";
                return (
                  <div key={`${d.name_of_reporting_person}-${i}`} style={{ padding: "0.4rem 0", borderTop: i > 0 ? "1px solid var(--border)" : "none" }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span className="num">{d.name_of_reporting_person}</span>
                      <span className="num">{`${(d.percent_of_class * 100).toFixed(1)}% — ${d.filing_date}`}</span>
                    </div>
                    <span className="num" style={{ fontSize: "0.78rem", color: isActivist ? "var(--gain)" : "var(--text-soft)" }}>
                      {isActivist ? "13D · activist intent" : "13G · passive"}
                    </span>
                  </div>
                );
              })}
            </section>

            <section className="card">
              <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.15rem" }}>
                {`Insider trades — ${searchedTicker}`}
              </p>
              <p style={{ color: "var(--text-soft)", fontSize: "0.75rem", marginBottom: "0.5rem" }}>
                Filed within 2 business days of the transaction
              </p>
              {transactions.loading && <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>Loading…</p>}
              {transactions.error && <p className="num loss" style={{ fontSize: "0.85rem" }}>{transactions.error}</p>}
              {transactions.data && transactions.data.length === 0 && (
                <p style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>No insider transactions found.</p>
              )}
              {transactions.data && transactions.data.slice(0, 15).map((t, i) => {
                const isRealPurchase = t.transaction_type === "P-Purchase" && t.price > 0;
                return (
                  <div
                    key={`${t.reporting_name}-${i}`}
                    style={{
                      padding: "0.4rem 0", borderTop: i > 0 ? "1px solid var(--border)" : "none",
                      background: isRealPurchase ? "var(--bg-success, rgba(34,197,94,0.08))" : "transparent",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span className="num" style={{ fontWeight: isRealPurchase ? 700 : 400 }}>{t.reporting_name}</span>
                      <span className="num" style={{ color: t.price === 0 ? "var(--text-soft)" : isRealPurchase ? "var(--gain)" : "var(--text-soft)", fontWeight: isRealPurchase ? 700 : 400 }}>
                        {t.price === 0 ? t.transaction_date : `$${t.price.toFixed(2)} — ${t.transaction_date}`}
                      </span>
                    </div>
                    <span className="num" style={{ fontSize: "0.78rem", color: isRealPurchase ? "var(--gain)" : "var(--text-soft)" }}>
                      {translateTransactionType(t.transaction_type)}
                    </span>
                  </div>
                );
              })}
            </section>
          </>
        )}
      </main>
    </AppShell>
  );
}
