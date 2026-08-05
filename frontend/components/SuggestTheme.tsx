"use client";

// AI-suggested themes — this backend capability (suggest_theme) has
// existed since earlier this session, fully built and tested, with
// zero UI exposure until now. A user could only create a theme by
// already knowing exactly which name and tickers they wanted.
//
// Deliberately a proposal, never an autonomous action: the AI names a
// theme, explains its reasoning per ticker, and flags which
// candidates are already in the system — but nothing gets created
// until the person explicitly reviews and confirms. Individual
// tickers can be deselected before creating, since "the AI grouped
// these" is a suggestion, not a verdict.

import { useState } from "react";
import { api, SuggestedTicker, ThemeSuggestion } from "@/lib/api";

export function SuggestTheme({ onCreated }: { onCreated: (name: string) => void }) {
  const [hint, setHint] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestion, setSuggestion] = useState<ThemeSuggestion | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [createProgress, setCreateProgress] = useState<string | null>(null);

  async function handleSuggest() {
    setLoading(true);
    setError(null);
    setSuggestion(null);
    try {
      const result = await api.suggestTheme(hint.trim() || undefined);
      setSuggestion(result);
      setSelected(new Set(result.candidate_tickers.map((t) => t.ticker)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't generate a suggestion right now.");
    } finally {
      setLoading(false);
    }
  }

  function toggle(ticker: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }

  async function handleCreate() {
    if (!suggestion || selected.size === 0) return;
    setCreating(true);
    setError(null);
    try {
      await api.createTheme(suggestion.theme_name, suggestion.rationale);
      const chosen = suggestion.candidate_tickers.filter((t) => selected.has(t.ticker));
      let done = 0;
      for (const t of chosen) {
        setCreateProgress(`Adding ${t.ticker} (${done + 1}/${chosen.length})…`);
        try {
          if (!t.already_ingested) await api.ingestCompany(t.ticker);
          await api.addTickerToTheme(suggestion.theme_name, t.ticker);
        } catch {
          // One ticker failing (e.g. a genuinely delisted symbol)
          // shouldn't abort the whole theme — keep going, the person
          // can retry that one individually from the theme detail
          // view afterward.
        }
        done += 1;
      }
      setSuggestion(null);
      setCreateProgress(null);
      onCreated(suggestion.theme_name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create the theme.");
    } finally {
      setCreating(false);
      setCreateProgress(null);
    }
  }

  return (
    <section className="card" style={{ marginBottom: "1.5rem" }}>
      <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>Suggest a theme</p>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <input
          type="text"
          placeholder="Optional hint, e.g. 'semiconductor supply chain'"
          value={hint}
          onChange={(e) => setHint(e.target.value)}
          style={{ flex: "1 1 260px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <button onClick={handleSuggest} className="btn-primary" disabled={loading} style={{ padding: "0.55rem 1.1rem", fontSize: "0.9rem" }}>
          {loading ? "Thinking…" : "Suggest"}
        </button>
      </div>
      <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.72rem", margin: "0.5rem 0 0" }}>
        Grounded in real recent news headlines — a proposal to review, not something created automatically.
      </p>
      {error && <p className="num loss" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }}>{error}</p>}

      {suggestion && (
        <div style={{ marginTop: "1.25rem", borderTop: "1px solid var(--rule)", paddingTop: "1.1rem" }}>
          <p style={{ margin: "0 0 0.4rem", fontSize: "1.05rem", fontWeight: 600 }}>{suggestion.theme_name}</p>
          <p style={{ margin: "0 0 1rem", fontSize: "0.88rem", color: "var(--text-soft)", lineHeight: 1.5 }}>
            {suggestion.rationale}
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "1rem" }}>
            {suggestion.candidate_tickers.map((t: SuggestedTicker) => (
              <label
                key={t.ticker}
                style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", cursor: "pointer" }}
              >
                <input
                  type="checkbox"
                  checked={selected.has(t.ticker)}
                  onChange={() => toggle(t.ticker)}
                  style={{ marginTop: "0.25rem" }}
                />
                <span>
                  <span style={{ fontWeight: 600 }}>{t.ticker}</span>
                  <span style={{ color: "var(--text-soft)" }}> — {t.company_name}</span>
                  {!t.already_ingested && (
                    <span className="num" style={{ color: "var(--text-soft)", fontSize: "0.72rem" }}> · will be ingested</span>
                  )}
                  <br />
                  <span style={{ fontSize: "0.82rem", color: "var(--text-soft)" }}>{t.reasoning}</span>
                </span>
              </label>
            ))}
          </div>

          {suggestion.sourced_headlines.length > 0 && (
            <details style={{ marginBottom: "1rem" }}>
              <summary style={{ cursor: "pointer", fontSize: "0.78rem", color: "var(--text-soft)" }}>
                Sourced from {suggestion.sourced_headlines.length} real headline(s)
              </summary>
              <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.2rem" }}>
                {suggestion.sourced_headlines.map((h) => (
                  <li key={h} style={{ fontSize: "0.78rem", color: "var(--text-soft)", marginBottom: "0.25rem" }}>{h}</li>
                ))}
              </ul>
            </details>
          )}

          <button
            onClick={handleCreate}
            className="btn-primary"
            disabled={creating || selected.size === 0}
            style={{ fontSize: "0.88rem", padding: "0.55rem 1.1rem" }}
          >
            {createProgress ?? (creating ? "Creating…" : `Create theme with ${selected.size} ticker${selected.size === 1 ? "" : "s"}`)}
          </button>
        </div>
      )}
    </section>
  );
}
