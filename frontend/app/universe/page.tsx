"use client";

// Universe — the curated investment universe, factor rankings, thematic
// synthesis, and risk-parity construction. Everything on this page is
// deliberately organized around ONE selected theme at a time: pick a
// theme, see its members ranked by factor, synthesize a narrative
// across them, or propose a risk-parity split of new capital across
// them. That single spine is the signature device here — the same
// theme selection drives every panel below it, so the page reads as
// one coherent workflow rather than four unrelated tools bolted
// together.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  api,
  ApiError,
  getApiKey,
  RankedFactorScore,
  RiskParityConstructionResponse,
  ThemeSynthesisReport,
  UniverseThemeSummary,
} from "@/lib/api";

function fmtZ(v: number | null): string {
  return v === null || v === undefined ? "—" : v.toFixed(2);
}
function zClass(v: number | null): string {
  if (v === null || v === undefined) return "";
  return v > 0 ? "gain" : v < 0 ? "loss" : "";
}
function fmtUsd(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function CreateThemeForm({ onCreated }: { onCreated: (name: string) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Name your theme first.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.createTheme(name.trim(), description.trim() || undefined);
      onCreated(name.trim());
      setName("");
      setDescription("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create the theme");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
      <input
        type="text"
        placeholder="New theme name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        style={{ flex: "1 1 160px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
      />
      <input
        type="text"
        placeholder="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        style={{ flex: "2 1 220px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
      />
      <button type="submit" className="btn-primary" disabled={loading} style={{ padding: "0.55rem 1.1rem", fontSize: "0.9rem" }}>
        {loading ? "…" : "Create"}
      </button>
      {error && <p className="num loss" style={{ fontSize: "0.78rem", width: "100%", margin: 0 }}>{error}</p>}
    </form>
  );
}

function AddTickerForm({ theme, onAdded }: { theme: string; onAdded: () => void }) {
  const [ticker, setTicker] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ticker.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await api.addTickerToTheme(theme, ticker.trim());
      setTicker("");
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't add that ticker");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
      <input
        type="text"
        placeholder="Add ticker"
        value={ticker}
        onChange={(e) => setTicker(e.target.value.toUpperCase())}
        style={{ flex: "1 1 auto", fontSize: "0.85rem", padding: "0.45rem 0.65rem" }}
      />
      <button type="submit" className="btn-primary" disabled={loading} style={{ padding: "0.45rem 0.9rem", fontSize: "0.82rem" }}>
        {loading ? "…" : "Add"}
      </button>
      {error && <p className="num loss" style={{ fontSize: "0.75rem", margin: 0, alignSelf: "center" }}>{error}</p>}
    </form>
  );
}

export default function UniversePage() {
  const router = useRouter();

  const [themes, setThemes] = useState<UniverseThemeSummary[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [members, setMembers] = useState<string[]>([]);
  const [rankings, setRankings] = useState<RankedFactorScore[]>([]);
  const [scoringNote, setScoringNote] = useState("");

  const [synthesis, setSynthesis] = useState<ThemeSynthesisReport | null>(null);
  const [synthesizing, setSynthesizing] = useState(false);
  const [synthesisError, setSynthesisError] = useState<string | null>(null);

  const [investAmount, setInvestAmount] = useState("10000");
  const [allocation, setAllocation] = useState<RiskParityConstructionResponse | null>(null);
  const [allocating, setAllocating] = useState(false);
  const [allocationError, setAllocationError] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadThemes = useCallback(async (selectAfter?: string) => {
    try {
      const res = await api.listThemes();
      setThemes(res.themes);
      const fallback = res.themes[0]?.theme.name ?? "";
      setSelected(selectAfter || fallback);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.push("/login");
        return;
      }
      setError(err instanceof Error ? err.message : "Couldn't load themes");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    loadThemes();
  }, [loadThemes, router]);

  const loadThemeDetail = useCallback(async (theme: string) => {
    setSynthesis(null);
    setSynthesisError(null);
    setAllocation(null);
    setAllocationError(null);
    if (!theme) {
      setMembers([]);
      setRankings([]);
      return;
    }
    try {
      const [tickersRes, rankRes] = await Promise.all([
        api.getThemeTickers(theme),
        api.getFactorRankings(50),
      ]);
      setMembers(tickersRes.tickers);
      setScoringNote(rankRes.scoring_note);
      const memberSet = new Set(tickersRes.tickers);
      setRankings(rankRes.results.filter((r) => memberSet.has(r.ticker)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load theme detail");
    }
  }, []);

  useEffect(() => {
    if (selected) loadThemeDetail(selected);
  }, [selected, loadThemeDetail]);

  async function handleSynthesize() {
    if (!selected) return;
    setSynthesizing(true);
    setSynthesisError(null);
    try {
      setSynthesis(await api.generateThemeSynthesis(selected));
    } catch (err) {
      setSynthesisError(err instanceof Error ? err.message : "Synthesis failed");
    } finally {
      setSynthesizing(false);
    }
  }

  async function handleAllocate() {
    const amount = parseFloat(investAmount);
    if (!members.length || !amount || amount <= 0) {
      setAllocationError("Enter a positive dollar amount for a theme with members.");
      return;
    }
    setAllocating(true);
    setAllocationError(null);
    try {
      setAllocation(await api.constructRiskParity(members, amount));
    } catch (err) {
      setAllocationError(err instanceof Error ? err.message : "Allocation failed");
    } finally {
      setAllocating(false);
    }
  }

  if (loading) {
    return (
      <main style={{ padding: "3rem", maxWidth: "1180px", margin: "0 auto" }}>
        <p className="num" style={{ color: "var(--text-soft)" }}>Loading…</p>
      </main>
    );
  }

  return (
    <main style={{ maxWidth: "1180px", margin: "0 auto", padding: "2rem 1.25rem 4rem" }}>
      <header style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "1rem", marginBottom: "1.5rem" }}>
        <div style={{ flex: "1 1 auto" }}>
          <p className="eyebrow">FinInsight · Universe</p>
          <h1 style={{ margin: "0.2rem 0 0" }}>Investment Universe</h1>
        </div>
        <nav style={{ display: "flex", gap: "1.25rem" }} className="num">
          <Link href="/terminal" style={{ color: "var(--text-soft)" }}>Terminal</Link>
          <Link href="/dashboard" style={{ color: "var(--text-soft)" }}>Dashboard</Link>
        </nav>
      </header>

      {error && (
        <section className="card" style={{ borderLeft: "3px solid var(--loss)", marginBottom: "1.5rem" }}>
          <p style={{ margin: 0 }}>{error}</p>
        </section>
      )}

      <section className="card" style={{ marginBottom: "1.5rem" }}>
        <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>Create a theme</p>
        <CreateThemeForm onCreated={(name) => loadThemes(name)} />
      </section>

      {themes.length === 0 && !error && (
        <section className="card">
          <p style={{ margin: 0 }}>No themes yet — create one above to get started.</p>
          <p className="num" style={{ margin: "0.5rem 0 0", color: "var(--text-soft)", fontSize: "0.85rem" }}>
            Themes are shared across every user — a global taxonomy like &quot;AI Infrastructure&quot; or
            &quot;China&quot;, not a personal list.
          </p>
        </section>
      )}

      {themes.length > 0 && (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.6rem", marginBottom: "1.75rem" }}>
            {themes.map((s) => (
              <button
                key={s.theme.name}
                onClick={() => setSelected(s.theme.name)}
                className="num"
                style={{
                  padding: "0.5rem 0.9rem",
                  borderRadius: "4px",
                  border: `1px solid ${selected === s.theme.name ? "var(--accent)" : "var(--rule)"}`,
                  background: selected === s.theme.name ? "rgba(94,184,199,0.12)" : "var(--surface)",
                  color: selected === s.theme.name ? "var(--accent)" : "var(--text)",
                  fontSize: "0.85rem",
                }}
              >
                {s.theme.name} <span style={{ color: "var(--text-soft)" }}>({s.member_count})</span>
              </button>
            ))}
          </div>

          {selected && (
            <>
              <section style={{ marginBottom: "2rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
                  <p className="eyebrow" style={{ margin: 0 }}>
                    {selected} — {members.length} member{members.length === 1 ? "" : "s"}
                  </p>
                </div>
                <div className="card">
                  {members.length === 0 ? (
                    <p style={{ margin: 0, color: "var(--text-soft)" }}>No tickers tagged yet — add one below.</p>
                  ) : (
                    <table className="num" style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.85rem" }}>
                      <thead>
                        <tr style={{ textAlign: "right", color: "var(--text-soft)", fontSize: "0.68rem", letterSpacing: "0.06em" }}>
                          <th style={{ textAlign: "left", padding: "0.35rem 0.5rem" }}>TICKER</th>
                          <th style={{ padding: "0.35rem 0.5rem" }}>COMPOSITE</th>
                          <th style={{ padding: "0.35rem 0.5rem" }}>VALUE</th>
                          <th style={{ padding: "0.35rem 0.5rem" }}>QUALITY</th>
                          <th style={{ padding: "0.35rem 0.5rem" }}>GROWTH</th>
                          <th style={{ padding: "0.35rem 0.5rem" }}>MOMENTUM</th>
                          <th style={{ padding: "0.35rem 0.5rem" }}>SIZE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {members.map((ticker) => {
                          const r = rankings.find((x) => x.ticker === ticker);
                          return (
                            <tr key={ticker} style={{ borderTop: "1px solid var(--rule)" }}>
                              <td style={{ padding: "0.5rem", textAlign: "left", fontWeight: 600 }}>{ticker}</td>
                              <td className={zClass(r?.composite_score ?? null)} style={{ padding: "0.5rem", textAlign: "right" }}>
                                {fmtZ(r?.composite_score ?? null)}
                              </td>
                              <td className={zClass(r?.value_z ?? null)} style={{ padding: "0.5rem", textAlign: "right" }}>{fmtZ(r?.value_z ?? null)}</td>
                              <td className={zClass(r?.quality_z ?? null)} style={{ padding: "0.5rem", textAlign: "right" }}>{fmtZ(r?.quality_z ?? null)}</td>
                              <td className={zClass(r?.growth_z ?? null)} style={{ padding: "0.5rem", textAlign: "right" }}>{fmtZ(r?.growth_z ?? null)}</td>
                              <td className={zClass(r?.momentum_z ?? null)} style={{ padding: "0.5rem", textAlign: "right" }}>{fmtZ(r?.momentum_z ?? null)}</td>
                              <td className={zClass(r?.size_z ?? null)} style={{ padding: "0.5rem", textAlign: "right" }}>{fmtZ(r?.size_z ?? null)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                  <AddTickerForm theme={selected} onAdded={() => loadThemeDetail(selected)} />
                  {scoringNote && (
                    <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.72rem", marginTop: "0.9rem", marginBottom: 0 }}>
                      {scoringNote}
                    </p>
                  )}
                </div>
              </section>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
                <section>
                  <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>AI synthesis</p>
                  <div className="card">
                    <button
                      onClick={handleSynthesize}
                      className="btn-primary"
                      disabled={synthesizing || members.length === 0}
                      style={{ fontSize: "0.85rem", padding: "0.55rem 1rem" }}
                    >
                      {synthesizing ? "Synthesizing…" : "Synthesize theme"}
                    </button>
                    <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.72rem", margin: "0.5rem 0 0" }}>
                      Grounded in the table above — not persisted, regenerated fresh each time.
                    </p>
                    {synthesisError && <p className="num loss" style={{ fontSize: "0.8rem" }}>{synthesisError}</p>}
                    {synthesis && (
                      <div style={{ marginTop: "1rem", fontSize: "0.87rem", lineHeight: 1.55 }}>
                        <p><strong>Overview</strong><br />{synthesis.overview}</p>
                        <p><strong>Common threads</strong><br />{synthesis.common_threads}</p>
                        <p><strong>Notable divergences</strong><br />{synthesis.notable_divergences}</p>
                        <p style={{ marginBottom: 0 }}><strong>Key risks</strong><br />{synthesis.key_risks}</p>
                      </div>
                    )}
                  </div>
                </section>

                <section>
                  <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>Risk-parity allocation</p>
                  <div className="card">
                    <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }}>
                      <input
                        type="number"
                        value={investAmount}
                        onChange={(e) => setInvestAmount(e.target.value)}
                        placeholder="Amount to invest"
                        style={{ flex: 1, fontSize: "0.85rem", padding: "0.5rem 0.7rem" }}
                      />
                      <button
                        onClick={handleAllocate}
                        className="btn-primary"
                        disabled={allocating || members.length === 0}
                        style={{ fontSize: "0.85rem", padding: "0.5rem 1rem", whiteSpace: "nowrap" }}
                      >
                        {allocating ? "…" : "Allocate"}
                      </button>
                    </div>
                    <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.72rem", margin: 0 }}>
                      Sized by volatility alone — lower-volatility names get more capital. Not a
                      return forecast, not a buy signal.
                    </p>
                    {allocationError && <p className="num loss" style={{ fontSize: "0.8rem" }}>{allocationError}</p>}
                    {allocation && (
                      <div style={{ marginTop: "0.9rem" }}>
                        {allocation.allocations.map((a) => (
                          <div key={a.ticker} className="ledger-row">
                            <div>
                              <div style={{ fontWeight: 500 }}>{a.ticker}</div>
                              <div className="num" style={{ fontSize: "0.75rem", color: "var(--text-soft)" }}>
                                {(a.target_weight * 100).toFixed(1)}% · {a.suggested_shares.toFixed(2)} sh
                              </div>
                            </div>
                            <div className="num" style={{ fontSize: "0.95rem" }}>{fmtUsd(a.target_dollar_amount)}</div>
                          </div>
                        ))}
                        {allocation.excluded.length > 0 && (
                          <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.72rem", marginTop: "0.6rem" }}>
                            Excluded (insufficient price history): {allocation.excluded.join(", ")}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                </section>
              </div>
            </>
          )}
        </>
      )}
    </main>
  );
}
