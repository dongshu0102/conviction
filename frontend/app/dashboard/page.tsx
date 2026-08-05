"use client";

// Dashboard — redesigned as a true OVERVIEW rather than a page that
// duplicates full functionality other pages now own. Previously this
// page showed the full watchlist table (also shown, with more detail,
// on Terminal) and embedded the full chat panel (now more prominently
// homed at /chat) — the exact "no clear distinction between pages"
// problem this redesign set out to fix. Now: Daily Brief (genuinely
// dashboard-native), and snapshot cards for Portfolios/Watchlist/Chat
// that link into their dedicated, fuller homes rather than re-showing
// the same data twice.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { api, getApiKey, ApiError, DailyBrief, Portfolio, WatchlistItem } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [brief, setBrief] = useState<DailyBrief | null>(null);
  const [portfolios, setPortfolios] = useState<Portfolio[] | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [briefLoading, setBriefLoading] = useState(false);

  useEffect(() => {
    if (!getApiKey()) {
      router.replace("/login");
      return;
    }
    Promise.all([api.listPortfolios(), api.getWatchlist()])
      .then(([p, w]) => {
        setPortfolios(p);
        setWatchlist(w);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to load");
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function loadBrief() {
    setBriefLoading(true);
    try {
      setBrief(await api.getDailyBrief());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load brief");
    } finally {
      setBriefLoading(false);
    }
  }

  if (loading) {
    return (
      <AppShell>
        <main style={{ padding: "3rem", maxWidth: 720, margin: "0 auto" }}>
          <p className="num" style={{ color: "var(--text-soft)" }}>Opening ledger…</p>
        </main>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <main style={{ padding: "2rem 1.5rem 4rem", maxWidth: 780, margin: "0 auto" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction</p>
        <h1 style={{ fontSize: "1.6rem", margin: "0.3rem 0 2rem" }}>Overview</h1>

        {error && (
          <p className="num loss" style={{ marginBottom: "1.5rem" }}>{error}</p>
        )}

        <section className="card" style={{ marginBottom: "1.75rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>Daily Brief</p>
          {!brief && (
            <div>
              <p style={{ color: "var(--text-soft)", marginBottom: "1rem", lineHeight: 1.6 }}>
                A short AI summary of your watchlist and portfolios. Real model
                call, worth generating once per session, not on every visit.
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

        <Link
          href="/growth-hunter"
          className="card"
          style={{ textDecoration: "none", color: "var(--text)", display: "block", marginBottom: "1.25rem", borderLeft: "3px solid var(--accent)" }}
        >
          <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Growth Hunter</p>
          <p style={{ margin: "0 0 0.5rem", fontFamily: "var(--font-display)", fontSize: "1.1rem", fontWeight: 600 }}>
            Find the case, not the hype
          </p>
          <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem", lineHeight: 1.6 }}>
            A different kind of analysis for early-stage companies — revenue
            trajectory, real risk flags, cash runway. Never a bare score,
            never a recommendation, always the honest breakdown.
          </p>
          <p style={{ margin: "0.75rem 0 0", fontSize: "0.85rem", color: "var(--accent)" }}>
            Assess a stock →
          </p>
        </Link>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem", marginBottom: "1.25rem" }}>
          <Link href="/portfolios" className="card" style={{ textDecoration: "none", color: "var(--text)" }}>
            <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Portfolios</p>
            <p className="num" style={{ fontSize: "1.8rem", margin: "0 0 0.25rem" }}>
              {portfolios?.length ?? 0}
            </p>
            <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--accent)" }}>View all →</p>
          </Link>

          <Link href="/terminal" className="card" style={{ textDecoration: "none", color: "var(--text)" }}>
            <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Watchlist</p>
            <p className="num" style={{ fontSize: "1.8rem", margin: "0 0 0.25rem" }}>
              {watchlist?.length ?? 0}
            </p>
            <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--accent)" }}>
              Triage, news, earnings →
            </p>
          </Link>
        </div>

        <Link href="/chat" className="card" style={{ textDecoration: "none", color: "var(--text)", display: "block" }}>
          <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Ask Conviction</p>
          <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
            Factor scores, portfolio risk, theme synthesis, deleting a
            theme — anything on the platform, grounded in real computation.
          </p>
          <p style={{ margin: "0.6rem 0 0", fontSize: "0.85rem", color: "var(--accent)" }}>
            Open chat →
          </p>
        </Link>
      </main>
    </AppShell>
  );
}
