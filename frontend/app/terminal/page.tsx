"use client";

// Watchlist Terminal — the densest expression of the Refined Terminal
// design system. One deliberate signature: the attention meter, which
// makes the deterministic triage score physically visible per row.
// Refresh is MANUAL by design: every refresh calls live market data
// (FMP per ticker), and silently auto-polling would burn API bandwidth
// the user pays for. The scoring note from the backend is displayed
// verbatim — the honesty contract extends to the UI.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import {
  api,
  ApiError,
  EarningsEvent,
  getApiKey,
  NewsArticle,
  TriageItem,
  TriageResponse,
  WatchlistNewsResponse,
} from "@/lib/api";

function fmtPct(v: number | null): string {
  if (v === null || v === undefined) return "—";
  const pct = v * 100;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function pctClass(v: number | null): string {
  if (v === null || v === undefined) return "";
  return v > 0 ? "gain" : v < 0 ? "loss" : "";
}

function fmtPrice(v: number | null): string {
  return v === null || v === undefined ? "—" : `$${v.toFixed(2)}`;
}

function timeAgo(iso: string | null): string {
  if (!iso) return "undated";
  const then = new Date(iso).getTime();
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export default function TerminalPage() {
  const router = useRouter();
  const [triage, setTriage] = useState<TriageResponse | null>(null);
  const [news, setNews] = useState<WatchlistNewsResponse | null>(null);
  const [earnings, setEarnings] = useState<EarningsEvent[] | null>(null);
  const [earningsUnavailable, setEarningsUnavailable] = useState(false);
  const [listFilter, setListFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [newTicker, setNewTicker] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [removingKey, setRemovingKey] = useState<string | null>(null);

  const load = useCallback(async (listName?: string) => {
    setLoading(true);
    setError(null);
    try {
      // Triage first (the core view), news and earnings after — a dead
      // news feed or an earnings-calendar-unsupported provider must not
      // blank the triage table.
      const t = await api.getTriage(listName || undefined);
      setTriage(t);
      try {
        const n = await api.getWatchlistNews(listName || undefined, 3);
        setNews(n);
      } catch {
        setNews(null); // news degraded — table still stands
      }
      try {
        const e = await api.getUpcomingEarnings(listName || undefined);
        setEarnings(e.events);
        setEarningsUnavailable(false);
      } catch {
        setEarnings(null);
        setEarningsUnavailable(true); // e.g. provider doesn't support the earnings calendar
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        router.push("/login");
        return;
      }
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const ticker = newTicker.trim().toUpperCase();
    if (!ticker) return;
    if (!/^[A-Z]{1,6}(\.[A-Z])?$/.test(ticker)) {
      setAddError(
        `"${newTicker.trim()}" doesn't look like a ticker symbol — try something like NVDA or BRK.B. ` +
        `For requests like adding with a target price or a specific list, use Chat instead.`
      );
      return;
    }
    setAdding(true);
    setAddError(null);
    try {
      await api.addToWatchlist(ticker, listFilter || undefined);
      setNewTicker("");
      await load(listFilter || undefined);
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Couldn't add that ticker.");
    } finally {
      setAdding(false);
    }
  }

  async function handleRemove(ticker: string, itemListName: string) {
    const key = `${itemListName}:${ticker}`;
    setRemovingKey(key);
    try {
      await api.removeFromWatchlist(ticker, itemListName);
      await load(listFilter || undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't remove that ticker.");
    } finally {
      setRemovingKey(null);
    }
  }

  const listNames = useMemo(() => {
    const names = new Set<string>();
    triage?.items.forEach((i) => names.add(i.list_name));
    return Array.from(names).sort();
  }, [triage]);

  const maxScore = useMemo(
    () => Math.max(1, ...(triage?.items.map((i) => i.triage_score) ?? [1])),
    [triage]
  );

  const asOf = triage ? new Date(triage.as_of) : null;

  return (
    <AppShell>
    <main style={{ maxWidth: "1180px", margin: "0 auto", padding: "2rem 1.25rem 4rem" }}>
      <header style={{ marginBottom: "0.5rem" }}>
        <p className="eyebrow">Conviction · Watchlist</p>
        <h1 style={{ margin: "0.2rem 0 0" }}>Watchlist Terminal</h1>
      </header>

      <form
        onSubmit={handleAdd}
        style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center", margin: "1rem 0" }}
      >
        <input
          type="text"
          placeholder="Add ticker, e.g. NVDA"
          value={newTicker}
          onChange={(e) => setNewTicker(e.target.value)}
          className="num"
          style={{ maxWidth: "200px", padding: "0.5rem 0.75rem", fontSize: "0.85rem", textTransform: "uppercase" }}
        />
        <button type="submit" className="btn-primary" disabled={adding || !newTicker.trim()} style={{ padding: "0.5rem 1.1rem", fontSize: "0.85rem" }}>
          {adding ? "Adding…" : "Add"}
        </button>
        {listFilter && (
          <span className="num" style={{ color: "var(--text-soft)", fontSize: "0.75rem" }}>
            → adds to &ldquo;{listFilter}&rdquo;
          </span>
        )}
      </form>
      {addError && (
        <p className="num loss" style={{ fontSize: "0.8rem", margin: "0 0 0.5rem" }}>{addError}</p>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "center", margin: "1rem 0 1.5rem" }}>
        <label className="num" htmlFor="list-filter" style={{ color: "var(--text-soft)", fontSize: "0.8rem" }}>
          List
        </label>
        <select
          id="list-filter"
          className="num"
          value={listFilter}
          onChange={(e) => {
            setListFilter(e.target.value);
            load(e.target.value || undefined);
          }}
          style={{
            background: "var(--surface)", color: "var(--text)",
            border: "1px solid var(--rule)", borderRadius: "4px", padding: "0.35rem 0.6rem",
          }}
        >
          <option value="">All lists</option>
          {listNames.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
        <button className="btn-primary" onClick={() => load(listFilter || undefined)} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
        <span className="num" style={{ color: "var(--text-soft)", fontSize: "0.75rem" }}>
          {asOf ? `as of ${asOf.toLocaleTimeString()}` : ""} · manual refresh — every refresh pulls live data
        </span>
      </div>

      {error && (
        <section className="card" style={{ borderLeft: "3px solid var(--loss)", marginBottom: "1.5rem" }}>
          <p style={{ margin: 0 }}>Couldn&apos;t load the terminal: {error}</p>
          <p className="num" style={{ margin: "0.5rem 0 0", color: "var(--text-soft)", fontSize: "0.8rem" }}>
            Check that the API is reachable and your key is valid, then refresh.
          </p>
        </section>
      )}

      {!error && triage && triage.items.length === 0 && !loading && (
        <section className="card">
          <p style={{ margin: 0 }}>Nothing on this watchlist yet.</p>
          <p className="num" style={{ margin: "0.5rem 0 0", color: "var(--text-soft)", fontSize: "0.85rem" }}>
            Type a ticker symbol above (like NVDA) and hit Add. For anything more —
            setting an entry target, picking a specific list, adding several at once —
            head to the Chat page and just describe what you want instead.
          </p>
        </section>
      )}

      {triage && triage.items.length > 0 && (
        <section style={{ overflowX: "auto", marginBottom: "2rem" }}>
          <table className="num" style={{ borderCollapse: "collapse", width: "100%", minWidth: "880px", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ textAlign: "right", color: "var(--text-soft)", fontSize: "0.7rem", letterSpacing: "0.08em" }}>
                <th style={{ textAlign: "left", padding: "0.4rem 0.6rem" }}>TICKER</th>
                <th style={{ padding: "0.4rem 0.6rem" }}>PRICE</th>
                <th style={{ padding: "0.4rem 0.6rem" }}>DAY</th>
                <th style={{ padding: "0.4rem 0.6rem" }}>SINCE ADD</th>
                <th style={{ padding: "0.4rem 0.6rem" }}>1M MOM</th>
                <th style={{ padding: "0.4rem 0.6rem" }}>P/E DRIFT</th>
                <th style={{ padding: "0.4rem 0.6rem" }}>TARGET</th>
                <th style={{ textAlign: "left", padding: "0.4rem 0.6rem", width: "180px" }}>ATTENTION</th>
                <th style={{ padding: "0.4rem 0.6rem", width: "40px" }}></th>
              </tr>
            </thead>
            <tbody>
              {triage.items.map((item: TriageItem) => (
                <tr
                  key={`${item.list_name}:${item.ticker}`}
                  style={{
                    borderTop: "1px solid var(--rule)",
                    borderLeft: item.signals.target_crossed ? "3px solid var(--accent)" : "3px solid transparent",
                  }}
                >
                  <td style={{ padding: "0.55rem 0.6rem", textAlign: "left" }}>
                    <span style={{ fontWeight: 600 }}>{item.ticker}</span>
                    <span style={{ color: "var(--text-soft)", marginLeft: "0.5rem", fontSize: "0.7rem" }}>
                      {item.list_name}
                    </span>
                    {item.notes && (
                      <div style={{ color: "var(--text-soft)", fontSize: "0.72rem", maxWidth: "220px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={item.notes}>
                        {item.notes}
                      </div>
                    )}
                  </td>
                  <td style={{ padding: "0.55rem 0.6rem", textAlign: "right" }}>{fmtPrice(item.signals.current_price)}</td>
                  <td className={pctClass(item.signals.day_move_pct)} style={{ padding: "0.55rem 0.6rem", textAlign: "right" }} title={item.signals.day_move_pct === null ? "No prior monitoring snapshot yet" : undefined}>
                    {fmtPct(item.signals.day_move_pct)}
                  </td>
                  <td className={pctClass(item.signals.move_since_added_pct)} style={{ padding: "0.55rem 0.6rem", textAlign: "right" }} title={item.signals.move_since_added_pct === null ? "No add-time price baseline" : undefined}>
                    {fmtPct(item.signals.move_since_added_pct)}
                  </td>
                  <td className={pctClass(item.signals.momentum_1m_pct)} style={{ padding: "0.55rem 0.6rem", textAlign: "right" }} title={item.signals.momentum_1m_pct === null ? "Not enough price history" : undefined}>
                    {fmtPct(item.signals.momentum_1m_pct)}
                  </td>
                  <td className={pctClass(item.signals.pe_drift_pct)} style={{ padding: "0.55rem 0.6rem", textAlign: "right" }} title={item.signals.pe_drift_pct === null ? "No add-time P/E baseline" : undefined}>
                    {fmtPct(item.signals.pe_drift_pct)}
                  </td>
                  <td style={{ padding: "0.55rem 0.6rem", textAlign: "right" }}>
                    {item.signals.target_crossed && (
                      <span style={{ color: "var(--accent)", fontSize: "0.68rem", marginRight: "0.4rem", letterSpacing: "0.06em" }}>
                        TARGET
                      </span>
                    )}
                  </td>
                  <td style={{ padding: "0.55rem 0.6rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ minWidth: "2.6rem", textAlign: "right" }}>{item.triage_score.toFixed(1)}</span>
                      <div aria-hidden style={{ flex: 1, height: "6px", background: "var(--surface)", borderRadius: "3px", overflow: "hidden" }}>
                        <div
                          style={{
                            width: `${Math.max(2, (item.triage_score / maxScore) * 100)}%`,
                            height: "100%",
                            background: "var(--accent)",
                            transition: "width 300ms ease",
                          }}
                        />
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: "0.55rem 0.6rem", textAlign: "center" }}>
                    <button
                      onClick={() => handleRemove(item.ticker, item.list_name)}
                      disabled={removingKey === `${item.list_name}:${item.ticker}`}
                      title={`Remove ${item.ticker} from ${item.list_name}`}
                      aria-label={`Remove ${item.ticker} from watchlist`}
                      style={{
                        background: "none", border: "none", cursor: "pointer",
                        color: "var(--text-soft)", fontSize: "0.9rem", padding: "0.2rem 0.4rem",
                        lineHeight: 1,
                      }}
                    >
                      {removingKey === `${item.list_name}:${item.ticker}` ? "…" : "×"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {triage && triage.tickers_excluded.length > 0 && (
        <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.78rem" }}>
          No quote available right now: {triage.tickers_excluded.join(", ")} — excluded from the table, not scored as zero.
        </p>
      )}

      {earnings && earnings.length > 0 && (
        <section style={{ marginTop: "2.5rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>Upcoming earnings</p>
          <div className="card">
            {earnings.map((e) => (
              <div key={`${e.ticker}-${e.report_date}`} className="ledger-row">
                <div>
                  <span style={{ fontWeight: 600 }}>{e.ticker}</span>
                  <span className="num" style={{ color: "var(--text-soft)", marginLeft: "0.6rem", fontSize: "0.8rem" }}>
                    {new Date(e.report_date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                  </span>
                </div>
                <span className="num" style={{ fontSize: "0.85rem", color: "var(--text-soft)" }}>
                  {e.eps_estimated !== null ? `est. EPS $${e.eps_estimated.toFixed(2)}` : "—"}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
      {earnings !== null && earnings.length === 0 && (
        <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.75rem", marginTop: "1rem" }}>
          No earnings coming up on your watchlist in the next 14 days.
        </p>
      )}
      {earningsUnavailable && (
        <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.75rem", marginTop: "1rem" }}>
          Earnings calendar unavailable right now.
        </p>
      )}

      {news && Object.keys(news.news).length > 0 && (
        <section style={{ marginTop: "2.5rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>Headlines</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1rem" }}>
            {Object.entries(news.news).map(([ticker, articles]) => (
              <article key={ticker} className="card">
                <p className="num" style={{ margin: "0 0 0.5rem", fontWeight: 600 }}>{ticker}</p>
                {articles.length === 0 && (
                  <p className="num" style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.8rem" }}>
                    No recent headlines.
                  </p>
                )}
                {articles.map((a: NewsArticle, i: number) => (
                  <div key={i} style={{ marginBottom: i < articles.length - 1 ? "0.75rem" : 0 }}>
                    {a.url ? (
                      <a href={a.url} target="_blank" rel="noreferrer" style={{ fontSize: "0.85rem" }}>
                        {a.title}
                      </a>
                    ) : (
                      <span style={{ fontSize: "0.85rem" }}>{a.title}</span>
                    )}
                    <div className="num" style={{ color: "var(--text-soft)", fontSize: "0.72rem", marginTop: "0.15rem" }}>
                      {a.source ?? "unknown source"} · {timeAgo(a.published_at)}
                    </div>
                  </div>
                ))}
              </article>
            ))}
          </div>
          {news.tickers_failed.length > 0 && (
            <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.78rem", marginTop: "0.75rem" }}>
              News unavailable for: {news.tickers_failed.join(", ")}
            </p>
          )}
        </section>
      )}

      {triage && (
        <footer style={{ marginTop: "3rem", borderTop: "1px solid var(--rule)", paddingTop: "1rem" }}>
          <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.75rem", margin: 0 }}>
            {triage.scoring_note}
          </p>
        </footer>
      )}
    </main>
    </AppShell>
  );
}
