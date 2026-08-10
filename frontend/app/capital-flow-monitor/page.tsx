"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import {
  api,
  getApiKey,
  CapitalFlowMonitorModuleDef,
  CapitalFlowMonitorModuleResult,
  CapitalFlowMonitorSynthesis,
  CapitalFlowMonitorSnapshot,
} from "@/lib/api";

interface ModuleState {
  status: "idle" | "loading" | "done" | "error";
  data: CapitalFlowMonitorModuleResult | null;
  error: string | null;
}

function directionTone(direction: string | null): "gain" | "loss" | "neutral" {
  if (direction === "inflow" || direction === "supportive") return "gain";
  if (direction === "outflow" || direction === "headwind") return "loss";
  return "neutral"; // "mixed", null (e.g. Event Calendar has no direction), or any future value
}

function DirectionBadge({ direction }: { direction: string | null }) {
  if (!direction) return null;
  const tone = directionTone(direction);
  const color = tone === "gain" ? "var(--gain)" : tone === "loss" ? "var(--loss)" : "var(--accent)";
  const label =
    direction === "inflow" ? "▲ inflow" :
    direction === "outflow" ? "▼ outflow" :
    direction === "supportive" ? "▲ supportive" :
    direction === "headwind" ? "▼ headwind" :
    "◆ mixed";
  return (
    <span
      className="num"
      style={{
        fontSize: "0.72rem", color, border: `1px solid ${color}`, borderRadius: "999px",
        padding: "0.1rem 0.55rem", marginLeft: "0.5rem",
      }}
    >
      {label}
    </span>
  );
}

function ModuleCard({
  moduleDef, state, onLoad,
}: {
  moduleDef: CapitalFlowMonitorModuleDef;
  state: ModuleState;
  onLoad: () => void;
}) {
  const { status, data, error } = state;
  return (
    <div className="card" style={{ padding: "1.25rem", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.75rem", marginBottom: "0.75rem" }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>{moduleDef.title}</div>
          <div className="num" style={{ fontSize: "0.72rem", color: "var(--text-soft)", marginTop: "0.15rem" }}>
            {moduleDef.cadence} · {moduleDef.source}
          </div>
        </div>
        <button
          onClick={onLoad}
          disabled={status === "loading"}
          className="num"
          style={{
            fontSize: "0.72rem", color: "var(--accent)", border: "1px solid var(--accent)",
            borderRadius: "4px", padding: "0.3rem 0.65rem", background: "transparent",
            opacity: status === "loading" ? 0.4 : 1, flexShrink: 0,
          }}
        >
          {status === "loading" ? "loading…" : status === "done" ? "refresh" : "load"}
        </button>
      </div>

      {status === "idle" && (
        <p style={{ fontSize: "0.85rem", color: "var(--text-soft)", margin: 0 }}>
          Press load to fetch the latest {moduleDef.title.toLowerCase()} data.
        </p>
      )}

      {status === "error" && (
        <p className="loss" style={{ fontSize: "0.85rem", margin: 0 }}>
          Couldn&apos;t load this module{error ? `: ${error}` : "."} Try load again.
        </p>
      )}

      {status === "done" && data && (
        <div>
          <div style={{ display: "flex", alignItems: "baseline", flexWrap: "wrap" }}>
            <span className="num" style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--accent)" }}>
              {data.headline_value}
            </span>
            <DirectionBadge direction={data.headline_direction} />
          </div>
          <div className="num" style={{ fontSize: "0.72rem", color: "var(--text-soft)", marginTop: "0.15rem", marginBottom: "0.75rem" }}>
            {data.headline_label} · as of {data.as_of}
          </div>

          {data.details.length > 0 && (
            <div style={{ marginBottom: "0.75rem" }}>
              {data.details.map((d, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", fontSize: "0.85rem", padding: "0.2rem 0" }}>
                  <span style={{ color: "var(--text-soft)" }}>{d.label}</span>
                  <span className="num" style={{ textAlign: "right" }}>{d.value}</span>
                </div>
              ))}
            </div>
          )}

          {data.read && (
            <p style={{ fontSize: "0.85rem", lineHeight: 1.4, paddingLeft: "0.6rem", borderLeft: "2px solid var(--accent)", margin: "0 0 0.6rem" }}>
              {data.read}
            </p>
          )}

          <div className="num" style={{ fontSize: "0.68rem", color: "var(--text-soft)" }}>
            {data.is_agent_estimate ? "AI web-search estimate" : "Real FRED data"} · src: {data.source_note}
          </div>
        </div>
      )}
    </div>
  );
}

function SynthesisCard({
  status, data, error, readyCount, total, onRun,
}: {
  status: "idle" | "loading" | "done" | "error";
  data: CapitalFlowMonitorSynthesis | null;
  error: string | null;
  readyCount: number;
  total: number;
  onRun: () => void;
}) {
  const tone = data ? directionTone(data.stance === "supportive" ? "supportive" : data.stance === "headwind" ? "headwind" : "mixed") : "neutral";
  const stanceColor = tone === "gain" ? "var(--gain)" : tone === "loss" ? "var(--loss)" : "var(--accent)";

  return (
    <div className="card" style={{ padding: "1.25rem", marginBottom: "1.5rem", border: "1px solid var(--accent)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <p className="eyebrow" style={{ margin: 0 }}>Synthesis</p>
          {status === "done" && data ? (
            <div style={{ display: "flex", alignItems: "baseline", gap: "0.75rem", marginTop: "0.3rem" }}>
              <span style={{ fontSize: "1.4rem", fontWeight: 700, color: stanceColor }}>{data.regime}</span>
              <DirectionBadge direction={data.stance === "supportive" ? "supportive" : data.stance === "headwind" ? "headwind" : "mixed"} />
            </div>
          ) : (
            <p style={{ fontSize: "0.85rem", color: "var(--text-soft)", margin: "0.3rem 0 0" }}>
              {status === "loading" ? "Strategist agent reading the board…" : `Load at least 3 modules, then synthesize for an overall verdict (${readyCount}/${total} loaded).`}
            </p>
          )}
        </div>
        <button
          onClick={onRun}
          disabled={status === "loading" || readyCount < 3}
          className="btn-primary"
          style={{ padding: "0.6rem 1.25rem", fontSize: "0.85rem" }}
        >
          {status === "loading" ? "Reading…" : status === "done" ? "Re-synthesize" : "Synthesize board"}
        </button>
      </div>

      {status === "error" && (
        <p className="loss" style={{ fontSize: "0.85rem", marginTop: "0.75rem" }}>
          Synthesis failed{error ? `: ${error}` : "."} Try again.
        </p>
      )}

      {status === "done" && data && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem", marginTop: "1.25rem" }}>
          <div>
            <p className="num" style={{ fontSize: "0.68rem", textTransform: "uppercase", color: "var(--gain)", margin: "0 0 0.4rem" }}>Supportive</p>
            {data.supportive.map((s, i) => (
              <p key={i} style={{ fontSize: "0.85rem", paddingLeft: "0.6rem", borderLeft: "2px solid var(--gain)", margin: "0 0 0.4rem" }}>{s}</p>
            ))}
          </div>
          <div>
            <p className="num" style={{ fontSize: "0.68rem", textTransform: "uppercase", color: "var(--loss)", margin: "0 0 0.4rem" }}>Headwinds</p>
            {data.headwinds.map((s, i) => (
              <p key={i} style={{ fontSize: "0.85rem", paddingLeft: "0.6rem", borderLeft: "2px solid var(--loss)", margin: "0 0 0.4rem" }}>{s}</p>
            ))}
          </div>
          <div style={{ gridColumn: "1 / -1", fontSize: "0.85rem", color: "var(--text-soft)" }}>
            <p style={{ margin: "0 0 0.3rem" }}><span className="num" style={{ color: "var(--accent)", textTransform: "uppercase", fontSize: "0.68rem" }}>Conflict · </span>{data.conflict}</p>
            <p style={{ margin: 0 }}><span className="num" style={{ color: "var(--accent)", textTransform: "uppercase", fontSize: "0.68rem" }}>Watch · </span><span style={{ color: "var(--text)" }}>{data.watch}</span></p>
          </div>
        </div>
      )}
    </div>
  );
}

function HistoryStrip({ history, moduleDefs }: { history: CapitalFlowMonitorSnapshot[]; moduleDefs: CapitalFlowMonitorModuleDef[] }) {
  if (history.length === 0) return null;
  const dotColor = (dir: string | null | undefined) => {
    if (!dir) return "var(--rule)";
    const tone = directionTone(dir);
    return tone === "gain" ? "var(--gain)" : tone === "loss" ? "var(--loss)" : "var(--accent)";
  };

  return (
    <div className="card" style={{ padding: "1rem 1.25rem", marginBottom: "1.5rem", overflowX: "auto" }}>
      <p className="eyebrow" style={{ margin: "0 0 0.6rem" }}>History — last {history.length} saved day{history.length === 1 ? "" : "s"}</p>
      <table className="num" style={{ fontSize: "0.72rem", color: "var(--text-soft)", borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", paddingRight: "1rem", paddingBottom: "0.3rem", fontWeight: 400 }}>date</th>
            {moduleDefs.map((m) => (
              <th key={m.id} title={m.title} style={{ padding: "0 0.35rem 0.3rem", fontWeight: 400 }}>
                {m.title.split(" ")[0].slice(0, 4).toLowerCase()}
              </th>
            ))}
            <th style={{ textAlign: "left", paddingLeft: "0.75rem", paddingBottom: "0.3rem", fontWeight: 400 }}>regime</th>
          </tr>
        </thead>
        <tbody>
          {history.map((day) => (
            <tr key={day.snapshot_date}>
              <td style={{ paddingRight: "1rem", padding: "0.15rem 1rem 0.15rem 0", color: "var(--text)" }}>{day.snapshot_date}</td>
              {moduleDefs.map((m) => {
                const sig = day.signals[m.id];
                return (
                  <td key={m.id} style={{ textAlign: "center", padding: "0.15rem 0.35rem" }}>
                    <span title={sig ? `${m.title}: ${sig[0]}` : `${m.title}: not loaded`} style={{ color: dotColor(sig?.[1]) }}>●</span>
                  </td>
                );
              })}
              <td style={{ paddingLeft: "0.75rem", padding: "0.15rem 0 0.15rem 0.75rem", color: day.regime_label ? "var(--accent)" : "var(--rule)" }}>
                {day.regime_label || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: "0.72rem", color: "var(--text-soft)", margin: "0.6rem 0 0" }}>
        <span style={{ color: "var(--gain)" }}>●</span> supportive/inflow ·{" "}
        <span style={{ color: "var(--loss)" }}>●</span> headwind/outflow ·{" "}
        <span style={{ color: "var(--rule)" }}>●</span> not loaded · hover a dot for the value
      </p>
    </div>
  );
}

export default function CapitalFlowMonitorPage() {
  const router = useRouter();
  const [moduleDefs, setModuleDefs] = useState<CapitalFlowMonitorModuleDef[] | null>(null);
  const [modules, setModules] = useState<Record<string, ModuleState>>({});
  const [loadingAll, setLoadingAll] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [synthesisStatus, setSynthesisStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [synthesisData, setSynthesisData] = useState<CapitalFlowMonitorSynthesis | null>(null);
  const [synthesisError, setSynthesisError] = useState<string | null>(null);
  const [history, setHistory] = useState<CapitalFlowMonitorSnapshot[]>([]);

  useEffect(() => {
    if (!getApiKey()) {
      router.push("/login");
      return;
    }
    api.getCapitalFlowMonitorModules()
      .then((defs) => {
        setModuleDefs(defs);
        setModules(Object.fromEntries(defs.map((d) => [d.id, { status: "idle", data: null, error: null }])));
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : String(err)));
    api.getCapitalFlowMonitorHistory().then(setHistory).catch(() => {
      // Non-critical — the strip just doesn't render without it.
    });
    // Deliberately run once on mount only — including `router` here
    // would re-fire this effect (and reset modules back to idle) on
    // every re-render, since a mocked useRouter() in tests returns a
    // fresh object each call. Auth/data fetching only needs to happen
    // once; individual module loads are handled by loadOne, not this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadOne = useCallback(async (moduleDef: CapitalFlowMonitorModuleDef) => {
    setModules((prev) => ({ ...prev, [moduleDef.id]: { ...prev[moduleDef.id], status: "loading", error: null } }));
    try {
      const data = await api.loadCapitalFlowMonitorModule(moduleDef.id);
      setModules((prev) => ({ ...prev, [moduleDef.id]: { status: "done", data, error: null } }));
      api.getCapitalFlowMonitorHistory().then(setHistory).catch(() => {});
    } catch (err) {
      setModules((prev) => ({
        ...prev,
        [moduleDef.id]: { ...prev[moduleDef.id], status: "error", error: err instanceof Error ? err.message : String(err) },
      }));
    }
  }, []);

  const loadAll = useCallback(async () => {
    if (!moduleDefs) return;
    setLoadingAll(true);
    for (const def of moduleDefs) {
      // Sequential, matching the artifact's original design — keeps
      // agent-backed searches reliable rather than firing 9 at once.
      // eslint-disable-next-line no-await-in-loop
      await loadOne(def);
    }
    setLoadingAll(false);
  }, [moduleDefs, loadOne]);

  const runSynthesis = useCallback(async () => {
    if (!moduleDefs) return;
    setSynthesisStatus("loading");
    setSynthesisError(null);
    try {
      const loaded = moduleDefs
        .filter((d) => modules[d.id]?.status === "done" && modules[d.id]?.data)
        .map((d) => ({ title: d.title, group: d.group, result: modules[d.id].data as CapitalFlowMonitorModuleResult }));
      const data = await api.synthesizeCapitalFlowMonitor(loaded);
      setSynthesisData(data);
      setSynthesisStatus("done");
      api.getCapitalFlowMonitorHistory().then(setHistory).catch(() => {});
    } catch (err) {
      setSynthesisStatus("error");
      setSynthesisError(err instanceof Error ? err.message : String(err));
    }
  }, [moduleDefs, modules]);

  const doneCount = Object.values(modules).filter((m) => m.status === "done").length;

  return (
    <AppShell>
      <main style={{ maxWidth: 960, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: "0.75rem", paddingBottom: "1.25rem", marginBottom: "1.5rem", borderBottom: "1px solid var(--rule)" }}>
          <div>
            <p className="eyebrow" style={{ margin: 0 }}>Conviction · Capital Flow Monitor</p>
            <h1 style={{ fontSize: "1.6rem", margin: "0.3rem 0 0" }}>Capital Flow Monitor</h1>
            <p style={{ fontSize: "0.9rem", color: "var(--text-soft)", margin: "0.35rem 0 0" }}>
              11 flow and macro-driver signals — 2 from real FRED data, 9 from an AI agent searching the live web.
            </p>
          </div>
          {moduleDefs && (
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <span className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}>{doneCount}/{moduleDefs.length} loaded</span>
              <button onClick={loadAll} disabled={loadingAll} className="btn-primary" style={{ padding: "0.6rem 1.25rem", fontSize: "0.85rem" }}>
                {loadingAll ? "Loading all…" : "Load all"}
              </button>
            </div>
          )}
        </div>

        {loadError && <p className="loss" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>{loadError}</p>}

        {!moduleDefs && !loadError && <p style={{ color: "var(--text-soft)" }}>Loading modules…</p>}

        {moduleDefs && (
          <>
            <SynthesisCard
              status={synthesisStatus} data={synthesisData} error={synthesisError}
              readyCount={doneCount} total={moduleDefs.length} onRun={runSynthesis}
            />
            <HistoryStrip history={history} moduleDefs={moduleDefs} />

            <p className="eyebrow" style={{ margin: "0 0 0.75rem" }}>I · Who is buying &amp; selling — flows</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
              {moduleDefs.filter((m) => m.group === "flow").map((m) => (
                <ModuleCard key={m.id} moduleDef={m} state={modules[m.id] || { status: "idle", data: null, error: null }} onLoad={() => loadOne(m)} />
              ))}
            </div>

            <p className="eyebrow" style={{ margin: "0 0 0.75rem" }}>II · Why they&apos;re doing it — macro drivers</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem" }}>
              {moduleDefs.filter((m) => m.group === "macro").map((m) => (
                <ModuleCard key={m.id} moduleDef={m} state={modules[m.id] || { status: "idle", data: null, error: null }} onLoad={() => loadOne(m)} />
              ))}
              <div className="card" style={{ padding: "1.25rem", border: "1px dashed var(--rule)", background: "transparent" }}>
                <p style={{ fontWeight: 600, fontSize: "0.9rem", margin: "0 0 0.5rem" }}>How to read this</p>
                <p style={{ fontSize: "0.82rem", color: "var(--text-soft)", margin: "0 0 0.5rem" }}>
                  Section I is the money itself: inflows, rising leverage, heavy buybacks mean demand; outflows and net-short positioning mean supply and caution.
                </p>
                <p style={{ fontSize: "0.82rem", color: "var(--text-soft)", margin: "0 0 0.5rem" }}>
                  Section II is what&apos;s driving the money: earnings and Fed policy set direction, credit spreads give early warning, sentiment flags extremes.
                </p>
                <p style={{ fontSize: "0.72rem", color: "var(--text-soft)", margin: 0 }}>
                  Credit Spreads and Liquidity Plumbing are real FRED data. The other 9 modules are an AI agent&apos;s best-effort read of a live web search — not verified numbers, and not investment advice.
                </p>
              </div>
            </div>
          </>
        )}
      </main>
    </AppShell>
  );
}
