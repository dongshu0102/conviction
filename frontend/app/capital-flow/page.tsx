"use client";

// Capital Flow Agent — a broad, market-wide feed of real, unusually
// large capital-flow events: insider trading, Senate/House financial
// disclosures, and (when configured) real FRED macro-flow shifts.
// Deliberately not per-user or watchlist-scoped, unlike Alerts — this
// is one shared feed across the whole platform, not personal to any
// one account. The real, scheduled scan runs on a cron job
// (scripts/run_capital_flow_scan.py); "Scan now" here is a manual
// trigger for testing/demo convenience, same rationale as Alerts'
// "Check now".

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, getApiKey, CapitalFlowEvent, Next13FDeadline } from "@/lib/api";

const SOURCE_LABEL: Record<string, string> = {
  INSIDER: "Insider",
  SENATE: "Senate",
  HOUSE: "House",
  VOLUME: "Volume",
  MACRO: "Macro",
};

const DIRECTION_COLOR: Record<string, string> = {
  BUY: "var(--gain)",
  SELL: "var(--loss)",
};

function fmtWhen(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return d.toLocaleString();
}

function fmtDateHeading(isoDate: string): string {
  // event_date is a plain date (YYYY-MM-DD), not a datetime — parsed
  // as UTC-midnight and displayed with UTC to avoid the real,
  // well-known bug where a plain date string shifts a day backward in
  // negative-UTC-offset timezones.
  const d = new Date(`${isoDate}T00:00:00Z`);
  return d.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
}

function groupEventsByDate(events: CapitalFlowEvent[]): [string, CapitalFlowEvent[]][] {
  const groups = new Map<string, CapitalFlowEvent[]>();
  for (const e of events) {
    const existing = groups.get(e.event_date);
    if (existing) {
      existing.push(e);
    } else {
      groups.set(e.event_date, [e]);
    }
  }
  // Most recent date first — events within a query are already
  // ordered by detected_at, but event_date grouping needs its own
  // explicit sort since insertion order follows detection order, not
  // the real event date.
  return Array.from(groups.entries()).sort((a, b) => (a[0] < b[0] ? 1 : -1));
}

export default function CapitalFlowPage() {
  const router = useRouter();
  const [events, setEvents] = useState<CapitalFlowEvent[] | null>(null);
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<string | null>(null);
  const [next13F, setNext13F] = useState<Next13FDeadline | null>(null);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, sourceFilter]);

  useEffect(() => {
    if (!getApiKey()) return;
    api.getNext13FDeadline().then(setNext13F).catch((err) => {
      // Non-critical — the page works fine without this banner if it
      // fails to load, but a silent, trace-free failure would make a
      // real future outage harder to debug than it needs to be.
      console.warn("Couldn't load the 13F deadline banner:", err);
    });
  }, []);

  function load() {
    setError(null);
    return api
      .getCapitalFlow({ source: sourceFilter || undefined })
      .then(setEvents)
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load capital flow events"));
  }

  async function handleScanNow() {
    setScanning(true);
    setScanResult(null);
    setError(null);
    try {
      const result = await api.triggerCapitalFlowScan();
      setScanResult(
        result.new_event_count === 0
          ? "No new unusually large capital flow events detected since the last scan."
          : `${result.new_event_count} new event${result.new_event_count === 1 ? "" : "s"} detected.`
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't run the scan");
    } finally {
      setScanning(false);
    }
  }

  return (
    <AppShell>
      <main style={{ maxWidth: 720, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Capital Flow</p>
        <h1 style={{ margin: "0.3rem 0 0.75rem" }}>Capital Flow</h1>
        <p style={{ color: "var(--text-soft)", lineHeight: 1.6, marginBottom: "1.75rem", fontSize: "0.95rem" }}>
          A broad, market-wide feed of real, unusually large capital-flow events — insider
          trading (genuine open-market purchases/sales only, not routine grants or
          conversions), U.S. Senate and House financial disclosures (legally-required dollar
          ranges, never exact figures), and real FRED macro-flow shifts. Every event already
          cleared an explicit size threshold. This is real, disclosed activity, not insider
          information, and none of it is advice to mirror anyone&apos;s trades.
        </p>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem", gap: "0.75rem" }}>
          <select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            className="num"
            style={{ padding: "0.5rem 0.75rem", fontSize: "0.85rem" }}
          >
            <option value="">All sources</option>
            <option value="INSIDER">Insider</option>
            <option value="SENATE">Senate</option>
            <option value="HOUSE">House</option>
            <option value="VOLUME">Volume</option>
            <option value="MACRO">Macro</option>
          </select>
          <button className="btn-primary" onClick={handleScanNow} disabled={scanning} style={{ padding: "0.5rem 1.1rem", fontSize: "0.85rem", whiteSpace: "nowrap" }}>
            {scanning ? "Scanning…" : "Scan now"}
          </button>
        </div>

        {error && (
          <p className="num loss" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>{error}</p>
        )}
        {scanResult && (
          <p className="num" style={{ fontSize: "0.85rem", color: "var(--text-soft)", marginBottom: "1rem" }}>
            {scanResult}
          </p>
        )}

        {next13F && next13F.next_deadline && (
          <div className="card" style={{ marginBottom: "1.25rem", padding: "0.85rem 1rem" }}>
            <p style={{ margin: 0, fontSize: "0.85rem" }}>
              Next Form 13F filing deadline: <span className="num" style={{ fontWeight: 600 }}>{fmtDateHeading(next13F.next_deadline)}</span>
              {next13F.days_until !== null && (
                <span style={{ color: "var(--text-soft)" }}> ({next13F.days_until === 0 ? "today" : `${next13F.days_until} day${next13F.days_until === 1 ? "" : "s"} away`})</span>
              )}
            </p>
            <p style={{ margin: "0.3rem 0 0", fontSize: "0.72rem", color: "var(--text-soft)" }}>
              {next13F.source_note}
            </p>
          </div>
        )}

        <div className="card">
          {events && events.length === 0 && (
            <p style={{ margin: 0, color: "var(--text-soft)" }}>
              No unusually large capital flow events detected yet.
            </p>
          )}
          {events && groupEventsByDate(events).map(([dateKey, dayEvents]) => (
            <div key={dateKey} style={{ marginBottom: "1.25rem" }}>
              <p className="eyebrow" style={{ fontSize: "0.68rem", marginBottom: "0.5rem" }}>
                {fmtDateHeading(dateKey)}
              </p>
              {dayEvents.map((e, i) => (
                <div key={`${e.source}-${e.symbol}-${e.detected_at}-${i}`} className="ledger-row" style={{ padding: "0.65rem 0" }}>
                  <div>
                    <div style={{ fontWeight: 500 }}>
                      {e.symbol ?? "Market-wide"}{" "}
                      <span style={{ fontWeight: 400, color: "var(--text-soft)", fontSize: "0.78rem" }}>
                        {SOURCE_LABEL[e.source] ?? e.source}
                      </span>
                      {e.direction !== "UNKNOWN" && (
                        <span className="num" style={{ fontSize: "0.72rem", marginLeft: "0.5rem", color: DIRECTION_COLOR[e.direction] }}>
                          {e.direction}
                        </span>
                      )}
                      {e.is_late_filing && (
                        <span className="num" style={{ fontSize: "0.68rem", marginLeft: "0.5rem", color: "var(--loss)", border: "1px solid var(--loss)", borderRadius: "3px", padding: "0.05rem 0.35rem" }}>
                          LATE FILING
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: "0.85rem", margin: "0.2rem 0" }}>
                      {e.detail_url ? (
                        <a href={e.detail_url} target="_blank" rel="noopener noreferrer" style={{ color: "inherit" }}>
                          {e.headline}
                        </a>
                      ) : (
                        e.headline
                      )}
                    </div>
                    <div className="num" style={{ fontSize: "0.72rem", color: "var(--text-soft)" }}>
                      Detected {fmtWhen(e.detected_at)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </main>
    </AppShell>
  );
}
