export function LedgerRow({
  label,
  sublabel,
  value,
  changePct,
  onRemove,
  removing,
}: {
  label: string;
  sublabel?: string;
  value: string;
  changePct?: number | null;
  onRemove?: () => void;
  removing?: boolean;
}) {
  const changeClass =
    changePct === null || changePct === undefined ? "" : changePct >= 0 ? "gain" : "loss";
  return (
    <div className="ledger-row">
      <div>
        <div style={{ fontWeight: 500 }}>{label}</div>
        {sublabel && (
          <div className="num" style={{ fontSize: "0.8rem", color: "var(--text-soft)" }}>
            {sublabel}
          </div>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <div style={{ textAlign: "right" }}>
          <div className={`num ${changeClass}`} style={{ fontSize: "1.05rem" }}>
            {value}
          </div>
          {changePct !== null && changePct !== undefined && (
            <div className={`num ${changeClass}`} style={{ fontSize: "0.8rem" }}>
              {changePct >= 0 ? "+" : ""}
              {(changePct * 100).toFixed(1)}%
            </div>
          )}
        </div>
        {onRemove && (
          <button
            onClick={onRemove}
            disabled={removing}
            aria-label={`Remove ${label}`}
            style={{ background: "none", border: "none", color: "var(--text-soft)", fontSize: "0.75rem", cursor: "pointer", padding: "0.25rem" }}
          >
            {removing ? "…" : "✕"}
          </button>
        )}
      </div>
    </div>
  );
}
