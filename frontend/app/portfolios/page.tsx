"use client";

// Portfolios index — a real gap this redesign fixes: previously there
// was no way to SEE all your portfolios, only jump directly to one by
// ID. This is the missing "browse" step.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, getApiKey, ApiError, Portfolio } from "@/lib/api";

export default function PortfoliosIndexPage() {
  const router = useRouter();
  const [portfolios, setPortfolios] = useState<Portfolio[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    load();
  }, [router]);

  async function load() {
    try {
      setPortfolios(await api.listPortfolios());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.push("/login");
        return;
      }
      setError(err instanceof Error ? err.message : "Couldn't load portfolios");
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const created = await api.createPortfolio(newName.trim());
      setNewName("");
      router.push(`/portfolios/${created.portfolio_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create portfolio");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(portfolioId: string) {
    setDeletingId(portfolioId);
    try {
      await api.deletePortfolio(portfolioId);
      setConfirmingDeleteId(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't delete this portfolio");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <AppShell>
      <main style={{ maxWidth: "900px", margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Portfolios</p>
        <h1 style={{ margin: "0.3rem 0 1.75rem" }}>Your portfolios</h1>

        {error && (
          <section className="card" style={{ borderLeft: "3px solid var(--loss)", marginBottom: "1.5rem" }}>
            <p style={{ margin: 0 }}>{error}</p>
          </section>
        )}

        <section className="card" style={{ marginBottom: "1.75rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>Create a portfolio</p>
          <form onSubmit={handleCreate} style={{ display: "flex", gap: "0.5rem" }}>
            <input
              type="text"
              placeholder="Portfolio name, e.g. Growth"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              style={{ flex: 1, fontSize: "0.95rem" }}
            />
            <button type="submit" className="btn-primary" disabled={creating || !newName.trim()}>
              {creating ? "…" : "Create"}
            </button>
          </form>
        </section>

        {portfolios === null && !error && (
          <p className="num" style={{ color: "var(--text-soft)" }}>Loading…</p>
        )}

        {portfolios !== null && portfolios.length === 0 && (
          <p style={{ color: "var(--text-soft)" }}>
            No portfolios yet — create one above to get started.
          </p>
        )}

        {portfolios && portfolios.length > 0 && (
          <div style={{ display: "grid", gap: "0.75rem" }}>
            {portfolios.map((p) => (
              <div
                key={p.portfolio_id}
                className="card"
                style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
              >
                <div>
                  <p style={{ margin: 0, fontWeight: 600, fontSize: "1.05rem" }}>{p.name}</p>
                  <p className="num" style={{ margin: "0.3rem 0 0", fontSize: "0.8rem", color: "var(--text-soft)" }}>
                    {p.holdings.length} holding{p.holdings.length === 1 ? "" : "s"}
                  </p>
                </div>
                {confirmingDeleteId !== p.portfolio_id ? (
                  <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                    <button
                      onClick={() => setConfirmingDeleteId(p.portfolio_id)}
                      style={{ background: "none", border: "none", color: "var(--text-soft)", fontSize: "0.78rem", cursor: "pointer" }}
                    >
                      Delete
                    </button>
                    <Link
                      href={`/portfolios/${p.portfolio_id}`}
                      className="num"
                      style={{ color: "var(--accent)", fontSize: "0.85rem", textDecoration: "none" }}
                    >
                      View →
                    </Link>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}>Delete it?</span>
                    <button
                      onClick={() => handleDelete(p.portfolio_id)}
                      disabled={deletingId === p.portfolio_id}
                      className="num loss"
                      style={{ background: "none", border: "1px solid var(--loss)", borderRadius: "4px", fontSize: "0.78rem", padding: "0.25rem 0.6rem", cursor: "pointer" }}
                    >
                      {deletingId === p.portfolio_id ? "…" : "Confirm"}
                    </button>
                    <button
                      onClick={() => setConfirmingDeleteId(null)}
                      disabled={deletingId === p.portfolio_id}
                      style={{ background: "none", border: "none", color: "var(--text-soft)", fontSize: "0.78rem", cursor: "pointer" }}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </AppShell>
  );
}
