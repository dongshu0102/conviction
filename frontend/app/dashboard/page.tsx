"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, clearApiKey, getApiKey, DailyBrief, Portfolio, WatchlistItem } from "@/lib/api";
import { LedgerRow } from "@/components/LedgerRow";
import { InlineAddForm } from "@/components/InlineAddForm";
import { ChatPanel } from "@/components/ChatPanel";

const usd = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export default function DashboardPage() {
  const router = useRouter();
  const [brief, setBrief] = useState<DailyBrief | null>(null);
  const [portfolios, setPortfolios] = useState<Portfolio[] | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[] | null>(null);
  const [prices, setPrices] = useState<Record<string, number | "unavailable">>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [briefLoading, setBriefLoading] = useState(false);

  useEffect(() => {
    if (!getApiKey()) {
      router.replace("/login");
      return;
    }
    Promise.all([api.listPortfolios(), api.getWatchlist()])
      .then(async ([p, w]) => {
        setPortfolios(p);
        setWatchlist(w);
        // Fetch each ticker's live price independently — one bad/unpriced
        // ticker must not block the rest from showing, same "isolate
        // failures" principle as the backend's monitoring use case.
        const results = await Promise.allSettled(
          w.map((item) => api.getCompanyValuation(item.ticker))
        );
        const priceMap: Record<string, number | "unavailable"> = {};
        w.forEach((item, i) => {
          const r = results[i];
          priceMap[item.ticker] = r.status === "fulfilled" ? r.value.price : "unavailable";
        });
        setPrices(priceMap);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [router]);

  async function loadBrief() {
    setBriefLoading(true);
    try {
      const result = await api.getDailyBrief();
      setBrief(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load brief");
    } finally {
      setBriefLoading(false);
    }
  }

  function logout() {
    clearApiKey();
    router.push("/login");
  }

  async function handleAddToWatchlist(ticker: string) {
    const item = await api.addToWatchlist(ticker);
    setWatchlist((prev) => (prev ? [...prev, item] : [item]));
    // Fetch this one ticker's price immediately rather than waiting for a
    // full page reload — keeps the list accurate right away.
    try {
      const valuation = await api.getCompanyValuation(item.ticker);
      setPrices((prev) => ({ ...prev, [item.ticker]: valuation.price }));
    } catch {
      setPrices((prev) => ({ ...prev, [item.ticker]: "unavailable" }));
    }
  }

  async function handleCreatePortfolio(name: string) {
    const portfolio = await api.createPortfolio(name);
    setPortfolios((prev) => (prev ? [...prev, portfolio] : [portfolio]));
    router.push(`/portfolios/${portfolio.portfolio_id}`);
  }

  if (loading) {
    return (
      <main style={{ padding: "3rem", maxWidth: 720, margin: "0 auto" }}>
        <p className="num" style={{ color: "var(--text-soft)" }}>
          Opening ledger…
        </p>
      </main>
    );
  }

  return (
    <main style={{ padding: "2rem 1.5rem 4rem", maxWidth: 720, margin: "0 auto" }}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: "2.5rem",
        }}
      >
        <div>
          <p className="eyebrow">FinInsight</p>
          <h1 style={{ fontSize: "1.6rem" }}>Today&rsquo;s ledger</h1>
        </div>
        <button
          onClick={logout}
          className="num"
          style={{ background: "none", border: "none", color: "var(--text-soft)", fontSize: "0.85rem" }}
        >
          Sign out
        </button>
      </header>

      {error && (
        <p className="num loss" style={{ marginBottom: "1.5rem" }}>
          {error}
        </p>
      )}

      {/* Daily Brief — the hero */}
      <section className="card" style={{ marginBottom: "2rem" }}>
        <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
          Daily Brief
        </p>
        {!brief && (
          <div>
            <p style={{ color: "var(--text-soft)", marginBottom: "1rem", lineHeight: 1.6 }}>
              Generate a short AI summary of your watchlist and portfolios. This
              makes a real model call — worth generating once per session, not
              on every visit.
            </p>
            <button className="btn-primary" onClick={loadBrief} disabled={briefLoading}>
              {briefLoading ? "Writing…" : "Get today's brief"}
            </button>
          </div>
        )}
        {brief && (
          <div>
            <p style={{ fontFamily: "var(--font-display)", fontSize: "1.15rem", lineHeight: 1.6 }}>
              {brief.narrative}
            </p>
            <p className="num" style={{ fontSize: "0.75rem", color: "var(--text-soft)", marginTop: "1rem" }}>
              Generated {new Date(brief.generated_at).toLocaleTimeString()}
            </p>
          </div>
        )}
      </section>

      <div style={{ marginBottom: "2.5rem" }}>
        <ChatPanel />
      </div>

      {/* Portfolios */}
      <section style={{ marginBottom: "2.5rem" }}>
        <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
          Portfolios
        </p>
        <div className="card">
          {portfolios && portfolios.length === 0 && (
            <p style={{ color: "var(--text-soft)" }}>No portfolios yet.</p>
          )}
          {portfolios?.map((p) => (
            <Link key={p.portfolio_id} href={`/portfolios/${p.portfolio_id}`} style={{ textDecoration: "none" }}>
              <LedgerRow
                label={p.name}
                sublabel={`${p.holdings.length} holding${p.holdings.length === 1 ? "" : "s"}`}
                value="View →"
              />
            </Link>
          ))}
        </div>
        <InlineAddForm
          placeholder="New portfolio name"
          buttonLabel="Create"
          onSubmit={handleCreatePortfolio}
        />
      </section>

      {/* Watchlist */}
      <section>
        <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
          Watchlist
        </p>
        <div className="card">
          {watchlist && watchlist.length === 0 && (
            <p style={{ color: "var(--text-soft)" }}>Nothing on your watchlist yet.</p>
          )}
          {watchlist?.map((w) => {
            const price = prices[w.ticker];
            return (
              <LedgerRow
                key={w.ticker}
                label={w.ticker}
                value={
                  price === undefined
                    ? "loading…"
                    : price === "unavailable"
                    ? "price unavailable"
                    : usd(price)
                }
              />
            );
          })}
        </div>
        <InlineAddForm
          placeholder="Ticker, e.g. AAPL"
          buttonLabel="Add"
          uppercase
          onSubmit={handleAddToWatchlist}
        />
      </section>
    </main>
  );
}
