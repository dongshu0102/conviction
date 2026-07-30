export function LedgerRow({
  label,
  sublabel,
  value,
  changePct,
}: {
  label: string;
  sublabel?: string;
  value: string;
  changePct?: number | null;
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
    </div>
  );
}
