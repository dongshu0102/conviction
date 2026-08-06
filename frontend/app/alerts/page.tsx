"use client";

// Alerts — the actual output of everything the monitoring pipeline
// generates: price moves, upcoming earnings, and growth-candidate
// condition changes. Before this page, the alert system was entirely
// invisible on the web — real alerts have been generating in
// production all session with no way to actually see them here.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, getApiKey, Alert } from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  PRICE_MOVE: "Price move",
  TARGET_REACHED: "Target reached",
  EARNINGS_UPCOMING: "Earnings upcoming",
  GROWTH_CONDITION_CHANGED: "Growth condition changed",
};

function fmtWhen(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return d.toLocaleString();
}

export default function AlertsPage() {
  const router = useRouter();
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [markingId, setMarkingId] = useState<number | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState<string | null>(null);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, unreadOnly]);

  function load() {
    setError(null);
    return api
      .getAlerts(unreadOnly)
      .then(setAlerts)
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load alerts"));
  }

  async function handleMarkRead(id: number) {
    setMarkingId(id);
    try {
      await api.markAlertRead(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't mark that alert as read");
    } finally {
      setMarkingId(null);
    }
  }

  async function handleCheckNow() {
    setChecking(true);
    setCheckResult(null);
    setError(null);
    try {
      const fresh = await api.checkAlerts();
      setCheckResult(
        fresh.length === 0
          ? "No new price moves or earnings alerts detected since the last check."
          : `${fresh.length} new alert${fresh.length === 1 ? "" : "s"} detected.`
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't run the check");
    } finally {
      setChecking(false);
    }
  }

  return (
    <AppShell>
      <main style={{ maxWidth: 720, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Alerts</p>
        <h1 style={{ margin: "0.3rem 0 0.75rem" }}>Alerts</h1>
        <p style={{ color: "var(--text-soft)", lineHeight: 1.6, marginBottom: "1.75rem", fontSize: "0.95rem" }}>
          Real output from the monitoring pipeline — price moves, upcoming earnings, and
          growth-candidate condition changes. Runs on a real schedule in the background;
          use Check now for an on-demand check instead of waiting.
        </p>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.9rem" }}>
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.checked)}
            />
            Unread only
          </label>
          <button className="btn-primary" onClick={handleCheckNow} disabled={checking} style={{ padding: "0.5rem 1.1rem", fontSize: "0.85rem" }}>
            {checking ? "Checking…" : "Check now"}
          </button>
        </div>

        {error && (
          <p className="num loss" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>{error}</p>
        )}
        {checkResult && (
          <p className="num" style={{ fontSize: "0.85rem", color: "var(--text-soft)", marginBottom: "1rem" }}>
            {checkResult}
          </p>
        )}

        <div className="card">
          {alerts && alerts.length === 0 && (
            <p style={{ margin: 0, color: "var(--text-soft)" }}>
              {unreadOnly ? "No unread alerts." : "No alerts yet."}
            </p>
          )}
          {alerts && alerts.map((a) => (
            <div
              key={a.id}
              className="ledger-row"
              style={{ padding: "0.65rem 0", opacity: a.is_read ? 0.6 : 1 }}
            >
              <div>
                <div style={{ fontWeight: 500 }}>
                  {a.ticker} <span style={{ fontWeight: 400, color: "var(--text-soft)", fontSize: "0.78rem" }}>
                    {TYPE_LABEL[a.alert_type] ?? a.alert_type}
                  </span>
                </div>
                <div style={{ fontSize: "0.85rem", margin: "0.2rem 0" }}>{a.message}</div>
                <div className="num" style={{ fontSize: "0.72rem", color: "var(--text-soft)" }}>
                  {fmtWhen(a.created_at)}
                  {a.change_pct !== null && ` · ${a.change_pct >= 0 ? "+" : ""}${(a.change_pct * 100).toFixed(1)}%`}
                </div>
              </div>
              {!a.is_read && (
                <button
                  onClick={() => handleMarkRead(a.id)}
                  disabled={markingId === a.id}
                  style={{ background: "none", border: "none", color: "var(--accent)", fontSize: "0.78rem", cursor: "pointer", whiteSpace: "nowrap" }}
                >
                  {markingId === a.id ? "…" : "Mark read"}
                </button>
              )}
            </div>
          ))}
        </div>
      </main>
    </AppShell>
  );
}
