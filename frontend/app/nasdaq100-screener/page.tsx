"use client";

// Nasdaq-100 Screener — filters the real Nasdaq-100 across all six
// dimensions discussed directly: GICS industry, market concentration
// (HHI), value chain position, business model, market cap tier, and
// maturity stage. Results come from a pre-computed, cached table
// (this app's own batch job, not a live, on-demand call per filter
// change) -- filtering itself is fast and free of further live calls.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, getApiKey, ApiError, Nasdaq100ClassificationRow } from "@/lib/api";

function fmtUsd(n: number | null): string {
  if (n === null) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}
function fmtPct(n: number | null): string {
  return n === null ? "—" : `${(n * 100).toFixed(1)}%`;
}
function fmtHhi(n: number | null, category: string | null): { text: string; title?: string } {
  if (n === null) return { text: "—" };
  if (category?.startsWith("Unclassifiable")) {
    // A genuinely valid HHI number (mathematically correct even for a
    // single-company group) is deliberately not shown here -- showing
    // e.g. "HHI: 10000" next to "Unclassifiable" would look
    // contradictory, since HHI=10000 normally signals a real,
    // single-firm monopoly, not "too little real data to classify."
    // The real, underlying number is still preserved via the API for
    // anyone inspecting the raw data directly -- only the display is
    // suppressed here, not the data itself.
    return {
      text: "—",
      title: `HHI computed as ${n.toFixed(0)}, but not shown here -- too few real, ingested peer companies to treat this as a meaningful market.`,
    };
  }
  return { text: n.toFixed(0) };
}

type FilterKey =
  | "industry" | "market_structure_category" | "value_chain_position"
  | "business_model" | "market_cap_tier" | "maturity_stage";

const FILTER_LABELS: Record<FilterKey, string> = {
  industry: "Industry",
  market_structure_category: "Market Structure",
  value_chain_position: "Value Chain Position",
  business_model: "Business Model",
  market_cap_tier: "Market Cap Tier",
  maturity_stage: "Maturity Stage",
};

export default function Nasdaq100ScreenerPage() {
  const router = useRouter();

  const [allResults, setAllResults] = useState<Nasdaq100ClassificationRow[] | null>(null);
  const [filteredResults, setFilteredResults] = useState<Nasdaq100ClassificationRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filters, setFilters] = useState<Partial<Record<FilterKey, string>>>({});
  const [filtering, setFiltering] = useState(false);

  const [running, setRunning] = useState(false);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getNasdaq100ScreenerResults();
      setAllResults(res.results);
      setFilteredResults(res.results);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.push("/login");
        return;
      }
      setError(err instanceof Error ? err.message : "Couldn't load screener results");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    loadAll();
  }, [loadAll, router]);

  // Real, actual values present in the loaded data -- never a
  // hardcoded list that could drift out of sync with the backend's
  // own enumerated categories, and never an option that would
  // genuinely return zero results.
  const filterOptions = useMemo(() => {
    const options: Record<FilterKey, string[]> = {
      industry: [], market_structure_category: [], value_chain_position: [],
      business_model: [], market_cap_tier: [], maturity_stage: [],
    };
    if (!allResults) return options;
    for (const key of Object.keys(options) as FilterKey[]) {
      const values = new Set<string>();
      for (const r of allResults) {
        const v = r[key];
        if (v) values.add(v);
      }
      options[key] = Array.from(values).sort();
    }
    return options;
  }, [allResults]);

  async function applyFilters(next: Partial<Record<FilterKey, string>>) {
    setFilters(next);
    setFiltering(true);
    try {
      const res = await api.getNasdaq100ScreenerResults(next);
      setFilteredResults(res.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't apply filters");
    } finally {
      setFiltering(false);
    }
  }

  function handleFilterChange(key: FilterKey, value: string) {
    const next = { ...filters };
    if (value) next[key] = value; else delete next[key];
    applyFilters(next);
  }

  function clearFilters() {
    applyFilters({});
  }

  async function handleRunBatch() {
    setRunning(true);
    setRunMessage(null);
    try {
      const result = await api.runNasdaq100Batch();
      setRunMessage(result.message);
    } catch (err) {
      setRunMessage(err instanceof Error ? err.message : "Couldn't start the batch");
    } finally {
      setRunning(false);
    }
  }

  const activeFilterCount = Object.keys(filters).length;

  return (
    <AppShell>
      <main style={{ maxWidth: "1100px", margin: "0 auto", padding: "2rem 1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.5rem" }}>
          <h1 style={{ margin: 0, fontSize: "1.4rem" }}>Nasdaq-100 Screener</h1>
          <button
            onClick={handleRunBatch}
            disabled={running}
            className="btn-primary"
            style={{ fontSize: "0.82rem", padding: "0.45rem 0.9rem" }}
          >
            {running ? "Starting…" : "Run classification batch"}
          </button>
        </div>
        <p style={{ color: "var(--text-soft)", fontSize: "0.85rem", marginBottom: "1.25rem" }}>
          Filters across six real dimensions: GICS industry, market concentration (HHI),
          value chain position, business model, market cap tier, and maturity stage.
          Results come from a pre-computed batch — this app&rsquo;s own real, ingested
          data and a real HHI calculation, plus two LLM-classified dimensions constrained
          to a fixed category list.
        </p>

        {runMessage && (
          <p className="num" style={{ fontSize: "0.8rem", color: "var(--text-soft)", marginBottom: "1rem" }}>
            {runMessage}
          </p>
        )}

        {error && <p className="num loss" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>{error}</p>}

        {!loading && (
          <div className="card" style={{ marginBottom: "1.25rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
              <p className="eyebrow" style={{ fontSize: "0.68rem", margin: 0 }}>Filters</p>
              {activeFilterCount > 0 && (
                <button onClick={clearFilters} style={{ fontSize: "0.75rem", color: "var(--text-soft)", background: "none", border: "none", cursor: "pointer" }}>
                  Clear all ({activeFilterCount})
                </button>
              )}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "0.6rem" }}>
              {(Object.keys(FILTER_LABELS) as FilterKey[]).map((key) => (
                <div key={key}>
                  <label style={{ display: "block", fontSize: "0.7rem", color: "var(--text-soft)", marginBottom: "0.25rem" }}>
                    {FILTER_LABELS[key]}
                  </label>
                  <select
                    value={filters[key] || ""}
                    onChange={(e) => handleFilterChange(key, e.target.value)}
                    style={{ width: "100%", fontSize: "0.82rem", padding: "0.4rem 0.5rem" }}
                  >
                    <option value="">All</option>
                    {filterOptions[key].map((opt) => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </div>
        )}

        {loading && <p style={{ color: "var(--text-soft)" }}>Loading…</p>}

        {!loading && filteredResults && filteredResults.length === 0 && (
          <p style={{ color: "var(--text-soft)", fontSize: "0.9rem" }}>
            {allResults && allResults.length === 0
              ? "No classification data yet — run the batch above, or the standalone script for a full, reliable run."
              : "No companies match the current filters."}
          </p>
        )}

        {!loading && filteredResults && filteredResults.length > 0 && (
          <div className="card">
            <p className="num" style={{ fontSize: "0.75rem", color: "var(--text-soft)", marginBottom: "0.75rem" }}>
              {filtering ? "Filtering…" : `${filteredResults.length} of ${allResults?.length ?? 0} companies`}
            </p>
            <table className="num" style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.82rem" }}>
              <thead>
                <tr style={{ textAlign: "right", color: "var(--text-soft)", fontSize: "0.66rem", letterSpacing: "0.05em" }}>
                  <th style={{ textAlign: "left", padding: "0.3rem 0.4rem" }}>TICKER</th>
                  <th style={{ textAlign: "left", padding: "0.3rem 0.4rem" }}>INDUSTRY</th>
                  <th style={{ padding: "0.3rem 0.4rem" }}>STRUCTURE</th>
                  <th style={{ padding: "0.3rem 0.4rem" }}>HHI</th>
                  <th style={{ textAlign: "left", padding: "0.3rem 0.4rem" }}>VALUE CHAIN</th>
                  <th style={{ textAlign: "left", padding: "0.3rem 0.4rem" }}>BUSINESS MODEL</th>
                  <th style={{ padding: "0.3rem 0.4rem" }}>CAP TIER</th>
                  <th style={{ padding: "0.3rem 0.4rem" }}>MATURITY</th>
                  <th style={{ padding: "0.3rem 0.4rem" }}>MKT CAP</th>
                  <th style={{ padding: "0.3rem 0.4rem" }}>REV GROWTH</th>
                </tr>
              </thead>
              <tbody>
                {filteredResults.map((r) => (
                  <tr key={r.ticker} style={{ borderTop: "1px solid var(--rule)" }}>
                    <td style={{ padding: "0.45rem 0.4rem", textAlign: "left", fontWeight: 600 }}>{r.ticker}</td>
                    <td style={{ padding: "0.45rem 0.4rem", textAlign: "left", color: "var(--text-soft)" }}>{r.industry}</td>
                    <td style={{ padding: "0.45rem 0.4rem", textAlign: "right" }}>{r.market_structure_category || "—"}</td>
                    <td style={{ padding: "0.45rem 0.4rem", textAlign: "right" }}>
                      <span title={fmtHhi(r.hhi, r.market_structure_category).title}>
                        {fmtHhi(r.hhi, r.market_structure_category).text}
                      </span>
                    </td>
                    <td style={{ padding: "0.45rem 0.4rem", textAlign: "left" }}>{r.value_chain_position || "—"}</td>
                    <td style={{ padding: "0.45rem 0.4rem", textAlign: "left" }}>{r.business_model || "—"}</td>
                    <td style={{ padding: "0.45rem 0.4rem", textAlign: "right" }}>{r.market_cap_tier || "—"}</td>
                    <td style={{ padding: "0.45rem 0.4rem", textAlign: "right" }}>{r.maturity_stage || "—"}</td>
                    <td style={{ padding: "0.45rem 0.4rem", textAlign: "right" }}>{fmtUsd(r.market_cap)}</td>
                    <td style={{ padding: "0.45rem 0.4rem", textAlign: "right" }}>{fmtPct(r.revenue_growth)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </AppShell>
  );
}
