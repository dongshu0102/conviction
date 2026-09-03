"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { AppShell } from "@/components/AppShell";
import {
  api, getApiKey, PortfolioRiskAnalysis, PortfolioValuation, OptionPortfolioValuation,
  BondPortfolioValuation, PortfolioGreeks, HedgingPlan, Recommendations, RebalancePlan,
} from "@/lib/api";
import { LedgerRow } from "@/components/LedgerRow";

const usd = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

const CHART_COLORS = ["#d4a24e", "#6a9f5e", "#93887a", "#c1584f", "#8a5a6b"];

function AddHoldingForm({ portfolioId, onAdded }: { portfolioId: string; onAdded: () => void }) {
  const [ticker, setTicker] = useState("");
  const [shares, setShares] = useState("");
  const [costBasis, setCostBasis] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const sharesNum = parseFloat(shares);
    const costNum = parseFloat(costBasis);
    if (!ticker.trim() || !sharesNum || sharesNum <= 0 || isNaN(costNum) || costNum < 0) {
      setError("Enter a ticker, positive shares, and a cost basis.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.addHolding(portfolioId, ticker.trim(), sharesNum, costNum);
      setTicker("");
      setShares("");
      setCostBasis("");
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add holding");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: "1rem" }}>
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <input
          type="text"
          placeholder="Ticker"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          style={{ flex: "1 1 90px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <input
          type="number"
          placeholder="Shares"
          value={shares}
          onChange={(e) => setShares(e.target.value)}
          style={{ flex: "1 1 90px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <input
          type="number"
          placeholder="Cost / share"
          value={costBasis}
          onChange={(e) => setCostBasis(e.target.value)}
          style={{ flex: "1 1 110px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <button
          type="submit"
          className="btn-primary"
          disabled={loading}
          style={{ padding: "0.55rem 1.1rem", fontSize: "0.9rem", whiteSpace: "nowrap" }}
        >
          {loading ? "…" : "Add"}
        </button>
      </div>
      {error && (
        <p className="num loss" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}>
          {error}
        </p>
      )}
    </form>
  );
}

function AddOptionForm({ portfolioId, onAdded }: { portfolioId: string; onAdded: () => void }) {
  const [ticker, setTicker] = useState("");
  const [strike, setStrike] = useState("");
  const [expiration, setExpiration] = useState("");
  const [optionType, setOptionType] = useState<"call" | "put">("call");
  const [contracts, setContracts] = useState("");
  const [costBasis, setCostBasis] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const strikeNum = parseFloat(strike);
    const contractsNum = parseFloat(contracts);
    const costNum = parseFloat(costBasis);
    if (
      !ticker.trim() || !strikeNum || strikeNum <= 0 || !expiration ||
      !contractsNum || contractsNum <= 0 || isNaN(costNum) || costNum < 0
    ) {
      setError("Enter a ticker, positive strike, expiration date, positive contracts, and a cost basis.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.addOptionHolding(portfolioId, ticker.trim(), strikeNum, expiration, optionType, contractsNum, costNum);
      setTicker("");
      setStrike("");
      setExpiration("");
      setContracts("");
      setCostBasis("");
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add option holding");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: "1rem" }}>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <input
          type="text"
          placeholder="Ticker"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          style={{ flex: "1 1 80px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <select
          value={optionType}
          onChange={(e) => setOptionType(e.target.value as "call" | "put")}
          style={{ flex: "1 1 80px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        >
          <option value="call">Call</option>
          <option value="put">Put</option>
        </select>
        <input
          type="number"
          placeholder="Strike"
          value={strike}
          onChange={(e) => setStrike(e.target.value)}
          style={{ flex: "1 1 90px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <input
          type="date"
          placeholder="Expiration"
          value={expiration}
          onChange={(e) => setExpiration(e.target.value)}
          style={{ flex: "1 1 140px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <input
          type="number"
          placeholder="Contracts"
          value={contracts}
          onChange={(e) => setContracts(e.target.value)}
          style={{ flex: "1 1 90px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <input
          type="number"
          placeholder="Cost / contract"
          value={costBasis}
          onChange={(e) => setCostBasis(e.target.value)}
          style={{ flex: "1 1 120px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <button
          type="submit"
          className="btn-primary"
          disabled={loading}
          style={{ padding: "0.55rem 1.1rem", fontSize: "0.9rem", whiteSpace: "nowrap" }}
        >
          {loading ? "…" : "Add"}
        </button>
      </div>
      {error && (
        <p className="num loss" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}>
          {error}
        </p>
      )}
    </form>
  );
}

function AddBondForm({ portfolioId, onAdded }: { portfolioId: string; onAdded: () => void }) {
  const [issuer, setIssuer] = useState("");
  const [coupon, setCoupon] = useState("");
  const [maturity, setMaturity] = useState("");
  const [quantity, setQuantity] = useState("");
  const [costBasis, setCostBasis] = useState("");
  const [cusip, setCusip] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const couponNum = parseFloat(coupon);
    const quantityNum = parseInt(quantity, 10);
    const costNum = parseFloat(costBasis);
    if (
      !issuer.trim() || isNaN(couponNum) || couponNum < 0 || !maturity ||
      !quantityNum || quantityNum <= 0 || isNaN(costNum) || costNum <= 0
    ) {
      setError("Enter an issuer, non-negative coupon rate (%), maturity date, positive quantity, and a positive price (% of face value).");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // Coupon entered as a real, human percentage (e.g. "4.5") — converted
      // to the decimal convention this app's own API uses everywhere (0.045).
      await api.addBondHolding(
        portfolioId, issuer.trim(), couponNum / 100, maturity, quantityNum, costNum, cusip.trim() || undefined,
      );
      setIssuer("");
      setCoupon("");
      setMaturity("");
      setQuantity("");
      setCostBasis("");
      setCusip("");
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add bond holding");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: "1rem" }}>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <input
          type="text"
          placeholder="Issuer name"
          value={issuer}
          onChange={(e) => setIssuer(e.target.value)}
          style={{ flex: "2 1 140px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <input
          type="number"
          placeholder="Coupon %"
          step="0.01"
          value={coupon}
          onChange={(e) => setCoupon(e.target.value)}
          style={{ flex: "1 1 90px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <input
          type="date"
          placeholder="Maturity"
          value={maturity}
          onChange={(e) => setMaturity(e.target.value)}
          style={{ flex: "1 1 140px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <input
          type="number"
          placeholder="Quantity"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          style={{ flex: "1 1 90px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <input
          type="number"
          placeholder="Price (% of face)"
          step="0.01"
          value={costBasis}
          onChange={(e) => setCostBasis(e.target.value)}
          style={{ flex: "1 1 130px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <input
          type="text"
          placeholder="CUSIP (optional)"
          value={cusip}
          onChange={(e) => setCusip(e.target.value)}
          style={{ flex: "1 1 120px", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        <button
          type="submit"
          className="btn-primary"
          disabled={loading}
          style={{ padding: "0.55rem 1.1rem", fontSize: "0.9rem", whiteSpace: "nowrap" }}
        >
          {loading ? "…" : "Add"}
        </button>
      </div>
      {error && (
        <p className="num loss" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}>
          {error}
        </p>
      )}
    </form>
  );
}

export default function PortfolioDetailPage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  const [valuation, setValuation] = useState<PortfolioValuation | null>(null);
  const [risk, setRisk] = useState<PortfolioRiskAnalysis | null>(null);
  const [options, setOptions] = useState<OptionPortfolioValuation | null>(null);
  const [bonds, setBonds] = useState<BondPortfolioValuation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [removingTicker, setRemovingTicker] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [removingOption, setRemovingOption] = useState<string | null>(null);
  const [removingBond, setRemovingBond] = useState<string | null>(null);
  const [greeks, setGreeks] = useState<PortfolioGreeks | null>(null);
  const [greeksLoading, setGreeksLoading] = useState(false);
  const [greeksError, setGreeksError] = useState<string | null>(null);
  const [hedging, setHedging] = useState<HedgingPlan | null>(null);
  const [hedgingLoading, setHedgingLoading] = useState(false);
  const [hedgingError, setHedgingError] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendations | null>(null);
  const [recommendationsLoading, setRecommendationsLoading] = useState(false);
  const [recommendationsError, setRecommendationsError] = useState<string | null>(null);
  const [rebalance, setRebalance] = useState<RebalancePlan | null>(null);
  const [rebalanceLoading, setRebalanceLoading] = useState(false);
  const [rebalanceError, setRebalanceError] = useState<string | null>(null);

  useEffect(() => {
    if (!getApiKey()) {
      router.replace("/login");
      return;
    }
    loadValuation();
    // Risk and options are loaded separately and allowed to fail
    // quietly — a portfolio's core valuation must never be blocked by
    // either panel not loading (e.g. too little price history, or no
    // options positions at all).
    api.getPortfolioRisk(id).then(setRisk).catch(() => setRisk(null));
    loadOptions();
    loadBonds();
  }, [id, router]);

  function loadOptions() {
    return api.getOptionPortfolioValuation(id).then(setOptions).catch(() => setOptions(null));
  }

  function loadBonds() {
    return api.getBondPortfolioValuation(id).then(setBonds).catch(() => setBonds(null));
  }

  function loadValuation() {
    return api
      .getPortfolioValuation(id)
      .then(setValuation)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }

  async function handleRemoveHolding(ticker: string) {
    setRemovingTicker(ticker);
    try {
      await api.removeHolding(id, ticker);
      await loadValuation();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Couldn't remove ${ticker}`);
    } finally {
      setRemovingTicker(null);
    }
  }

  async function handleRemoveOption(position: OptionPortfolioValuation["positions"][number]) {
    setRemovingOption(position.contract);
    try {
      await api.removeOptionHolding(
        id, position.underlying_ticker, position.strike, position.expiration, position.option_type
      );
      await loadOptions();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Couldn't remove ${position.contract}`);
    } finally {
      setRemovingOption(null);
    }
  }

  async function handleRemoveBond(position: BondPortfolioValuation["positions"][number]) {
    const key = `${position.issuer_name}-${position.coupon_rate}-${position.maturity_date}`;
    setRemovingBond(key);
    try {
      await api.removeBondHolding(id, position.issuer_name, position.coupon_rate, position.maturity_date);
      await loadBonds();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Couldn't remove ${position.issuer_name}`);
    } finally {
      setRemovingBond(null);
    }
  }

  async function handleLoadGreeks() {
    setGreeksLoading(true);
    setGreeksError(null);
    try {
      setGreeks(await api.getPortfolioGreeks(id));
    } catch (err) {
      setGreeksError(err instanceof Error ? err.message : "Couldn't compute Greeks");
    } finally {
      setGreeksLoading(false);
    }
  }

  async function handleLoadHedging() {
    setHedgingLoading(true);
    setHedgingError(null);
    try {
      setHedging(await api.getHedgingSuggestion(id));
    } catch (err) {
      setHedgingError(err instanceof Error ? err.message : "Couldn't compute a hedging suggestion");
    } finally {
      setHedgingLoading(false);
    }
  }

  async function handleLoadRecommendations() {
    setRecommendationsLoading(true);
    setRecommendationsError(null);
    try {
      setRecommendations(await api.getRecommendations(id));
    } catch (err) {
      setRecommendationsError(err instanceof Error ? err.message : "Couldn't compute recommendations");
    } finally {
      setRecommendationsLoading(false);
    }
  }

  async function handleLoadRebalance() {
    setRebalanceLoading(true);
    setRebalanceError(null);
    try {
      setRebalance(await api.getRebalanceSuggestion(id));
    } catch (err) {
      setRebalanceError(err instanceof Error ? err.message : "Couldn't compute a rebalancing plan");
    } finally {
      setRebalanceLoading(false);
    }
  }

  async function handleDeletePortfolio() {
    setDeleting(true);
    try {
      await api.deletePortfolio(id);
      router.push("/portfolios");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't delete this portfolio");
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <AppShell>
        <main style={{ padding: "3rem", maxWidth: 720, margin: "0 auto" }}>
          <p className="num" style={{ color: "var(--text-soft)" }}>
            Loading…
          </p>
        </main>
      </AppShell>
    );
  }

  if (error || !valuation) {
    return (
      <AppShell>
        <main style={{ padding: "3rem", maxWidth: 720, margin: "0 auto" }}>
          <p className="num loss">{error || "Portfolio not found."}</p>
          <Link href="/portfolios" style={{ fontSize: "0.9rem" }}>
            ← Back to portfolios
          </Link>
        </main>
      </AppShell>
    );
  }

  const chartData = valuation.positions.map((p) => ({
    name: p.ticker,
    value: p.market_value,
  }));
  const totalGainClass = valuation.total_unrealized_gain >= 0 ? "gain" : "loss";

  return (
    <AppShell>
    <main style={{ padding: "2rem 1.5rem 4rem", maxWidth: 720, margin: "0 auto" }}>
      <Link
        href="/portfolios"
        className="num"
        style={{ fontSize: "0.85rem", color: "var(--text-soft)", textDecoration: "none" }}
      >
        ← Portfolios
      </Link>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", margin: "0.5rem 0 2rem" }}>
        <h1 style={{ margin: 0, fontSize: "1.75rem" }}>{valuation.name}</h1>
        {!confirmingDelete ? (
          <button
            onClick={() => setConfirmingDelete(true)}
            style={{ background: "none", border: "none", color: "var(--text-soft)", fontSize: "0.78rem", cursor: "pointer" }}
          >
            Delete portfolio
          </button>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}>
              Delete &ldquo;{valuation.name}&rdquo; and all its holdings? This can&rsquo;t be undone.
            </span>
            <button
              onClick={handleDeletePortfolio}
              disabled={deleting}
              className="num loss"
              style={{ background: "none", border: "1px solid var(--loss)", borderRadius: "4px", fontSize: "0.78rem", padding: "0.25rem 0.6rem", cursor: "pointer" }}
            >
              {deleting ? "Deleting…" : "Confirm delete"}
            </button>
            <button
              onClick={() => setConfirmingDelete(false)}
              disabled={deleting}
              style={{ background: "none", border: "none", color: "var(--text-soft)", fontSize: "0.78rem", cursor: "pointer" }}
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      <section className="card" style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div>
            <p className="eyebrow">Total value</p>
            <p className="num" style={{ fontSize: "2rem", marginTop: "0.25rem" }}>
              {usd(valuation.total_market_value)}
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <p className="eyebrow">Unrealized gain</p>
            <p className={`num ${totalGainClass}`} style={{ fontSize: "1.4rem", marginTop: "0.25rem" }}>
              {usd(valuation.total_unrealized_gain)}
              {valuation.total_unrealized_gain_pct !== null && (
                <span style={{ fontSize: "0.9rem" }}>
                  {" "}
                  ({valuation.total_unrealized_gain_pct >= 0 ? "+" : ""}
                  {(valuation.total_unrealized_gain_pct * 100).toFixed(1)}%)
                </span>
              )}
            </p>
          </div>
        </div>
      </section>

      {chartData.length > 0 && (
        <section style={{ marginBottom: "2.5rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
            Allocation
          </p>
          <div className="card" style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={(entry) => entry.name}
                >
                  {chartData.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => usd(Number(value))} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      <section>
        <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
          Holdings
        </p>
        <div className="card">
          {valuation.positions.length === 0 && (
            <p style={{ color: "var(--text-soft)" }}>No holdings yet — add one below.</p>
          )}
          {valuation.positions.map((p) => (
            <LedgerRow
              key={p.ticker}
              label={p.ticker}
              sublabel={`${p.shares} shares @ ${usd(p.current_price)}`}
              value={usd(p.market_value)}
              changePct={p.unrealized_gain_pct}
              onRemove={() => handleRemoveHolding(p.ticker)}
              removing={removingTicker === p.ticker}
            />
          ))}
          <AddHoldingForm portfolioId={id} onAdded={loadValuation} />
        </div>
      </section>

      <section style={{ marginTop: "2.5rem" }}>
        <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
          Options
        </p>
        <div className="card">
          {(!options || options.positions.length === 0) && (
            <p style={{ color: "var(--text-soft)" }}>No option holdings yet — add one below.</p>
          )}
          {options && options.positions.length > 0 && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "1rem" }}>
                <p className="eyebrow" style={{ fontSize: "0.65rem", margin: 0 }}>Total options value</p>
                <p className={`num ${options.total_unrealized_gain >= 0 ? "gain" : "loss"}`} style={{ margin: 0, fontSize: "1.1rem" }}>
                  {usd(options.total_market_value)}
                  <span style={{ fontSize: "0.8rem" }}>
                    {" "}({options.total_unrealized_gain >= 0 ? "+" : ""}
                    {(options.total_unrealized_gain_pct * 100).toFixed(1)}%)
                  </span>
                </p>
              </div>
              {options.positions.map((p) => (
                <LedgerRow
                  key={p.contract}
                  label={p.contract}
                  sublabel={`${p.contracts_held} contract${p.contracts_held === 1 ? "" : "s"} @ ${usd(p.current_price)}`}
                  value={usd(p.market_value)}
                  changePct={p.unrealized_gain_pct}
                  onRemove={() => handleRemoveOption(p)}
                  removing={removingOption === p.contract}
                />
              ))}
              {options.positions_excluded.length > 0 && (
                <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.75rem", marginTop: "0.75rem" }}>
                  Excluded from valuation (no live pricing available): {options.positions_excluded.join(", ")}
                </p>
              )}
            </>
          )}
          <AddOptionForm portfolioId={id} onAdded={loadOptions} />
        </div>
      </section>

      <section style={{ marginTop: "2.5rem" }}>
        <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
          Bonds
        </p>
        <div className="card">
          {(!bonds || bonds.positions.length === 0) && (
            <p style={{ color: "var(--text-soft)" }}>No bond holdings yet — add one below.</p>
          )}
          {bonds && bonds.positions.length > 0 && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "1rem" }}>
                <p className="eyebrow" style={{ fontSize: "0.65rem", margin: 0 }}>Total face value</p>
                <p className="num" style={{ margin: 0, fontSize: "1.1rem" }}>
                  {usd(bonds.total_face_value)}
                  <span className="num" style={{ fontSize: "0.8rem", color: "var(--text-soft)" }}>
                    {" "}(cost basis {usd(bonds.total_cost_basis)})
                  </span>
                </p>
              </div>
              {bonds.positions.map((p) => {
                const key = `${p.issuer_name}-${p.coupon_rate}-${p.maturity_date}`;
                const ytmText = p.yield_to_maturity !== null ? `${(p.yield_to_maturity * 100).toFixed(2)}% YTM` : "YTM n/a";
                return (
                  <LedgerRow
                    key={key}
                    label={p.issuer_name}
                    sublabel={`${(p.coupon_rate * 100).toFixed(2)}% coupon · matures ${p.maturity_date} · ${ytmText}`}
                    value={usd(p.total_face_value)}
                    onRemove={() => handleRemoveBond(p)}
                    removing={removingBond === key}
                  />
                );
              })}
              <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.75rem", marginTop: "0.75rem" }}>
                No live bond price source is available — yields shown are estimated directly from the price paid, not a current market quote.
              </p>
            </>
          )}
          <AddBondForm portfolioId={id} onAdded={loadBonds} />
        </div>
      </section>

      <section style={{ marginTop: "2.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
          <p className="eyebrow" style={{ margin: 0 }}>Portfolio Greeks</p>
          {!greeks && (
            <button className="btn-primary" onClick={handleLoadGreeks} disabled={greeksLoading} style={{ padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}>
              {greeksLoading ? "Computing…" : "Compute"}
            </button>
          )}
        </div>
        <div className="card">
          {greeksError && <p className="num loss" style={{ margin: 0, fontSize: "0.85rem" }}>{greeksError}</p>}
          {!greeks && !greeksError && (
            <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
              Aggregate delta, gamma, theta, and vega across every option position.
            </p>
          )}
          {greeks && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: "1.25rem" }}>
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Delta</p>
                  <p className="num" style={{ fontSize: "1.15rem", margin: "0.2rem 0 0" }}>{greeks.total_delta.toFixed(2)}</p>
                </div>
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Gamma</p>
                  <p className="num" style={{ fontSize: "1.15rem", margin: "0.2rem 0 0" }}>{greeks.total_gamma.toFixed(4)}</p>
                </div>
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Theta</p>
                  <p className="num" style={{ fontSize: "1.15rem", margin: "0.2rem 0 0" }}>{greeks.total_theta.toFixed(2)}</p>
                </div>
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Vega</p>
                  <p className="num" style={{ fontSize: "1.15rem", margin: "0.2rem 0 0" }}>{greeks.total_vega.toFixed(2)}</p>
                </div>
              </div>
              {greeks.positions_excluded.length > 0 && (
                <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.75rem", marginTop: "1rem", marginBottom: 0 }}>
                  Excluded ({greeks.positions_included} position{greeks.positions_included === 1 ? "" : "s"} included): {greeks.positions_excluded.join(", ")}
                </p>
              )}
            </>
          )}
        </div>
      </section>

      <section style={{ marginTop: "2.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
          <p className="eyebrow" style={{ margin: 0 }}>Hedging Suggestion</p>
          {!hedging && (
            <button className="btn-primary" onClick={handleLoadHedging} disabled={hedgingLoading} style={{ padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}>
              {hedgingLoading ? "Computing…" : "Compute"}
            </button>
          )}
        </div>
        <div className="card">
          {hedgingError && <p className="num loss" style={{ margin: 0, fontSize: "0.85rem" }}>{hedgingError}</p>}
          {!hedging && !hedgingError && (
            <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
              Share trades that would bring each underlying's net delta exposure toward zero.
            </p>
          )}
          {hedging && hedging.suggestions.length === 0 && (
            <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>{hedging.note}</p>
          )}
          {hedging && hedging.suggestions.map((s) => (
            <div key={s.underlying_ticker} className="ledger-row" style={{ padding: "0.5rem 0" }}>
              <div>
                <div style={{ fontWeight: 500 }}>{s.underlying_ticker}</div>
                <div className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}>
                  Net delta {s.net_delta.toFixed(2)} → resulting {s.resulting_delta.toFixed(2)}
                </div>
              </div>
              <div className="num" style={{ fontSize: "0.95rem" }}>
                {s.shares_to_trade >= 0 ? "Buy" : "Sell"} {Math.abs(s.shares_to_trade).toFixed(0)} sh
              </div>
            </div>
          ))}
        </div>
      </section>

      {risk && (
        <section style={{ marginTop: "2.5rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
            Risk analysis
          </p>
          <div className="card">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "1.25rem", marginBottom: "1.25rem" }}>
              {risk.largest_position_weight !== null && (
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Largest position</p>
                  <p className="num" style={{ fontSize: "1.15rem", margin: "0.2rem 0 0" }}>{pct(risk.largest_position_weight)}</p>
                </div>
              )}
              {risk.herfindahl_index !== null && (
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Concentration (HHI)</p>
                  <p className="num" style={{ fontSize: "1.15rem", margin: "0.2rem 0 0" }}>{risk.herfindahl_index.toFixed(2)}</p>
                </div>
              )}
              {risk.portfolio_annualized_volatility !== null && (
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>Annualized volatility</p>
                  <p className="num" style={{ fontSize: "1.15rem", margin: "0.2rem 0 0" }}>{pct(risk.portfolio_annualized_volatility)}</p>
                </div>
              )}
              {risk.parametric_var_95_1day_dollar !== null && (
                <div>
                  <p className="eyebrow" style={{ fontSize: "0.65rem" }}>95% 1-day VaR</p>
                  <p className="num loss" style={{ fontSize: "1.15rem", margin: "0.2rem 0 0" }}>
                    -{usd(risk.parametric_var_95_1day_dollar)}
                  </p>
                </div>
              )}
            </div>

            {risk.volatility_covered_weight !== null && risk.volatility_covered_weight < 0.999 && (
              <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.75rem", marginBottom: "1rem" }}>
                Volatility figures cover {pct(risk.volatility_covered_weight)} of this portfolio by
                value — {risk.excluded_from_volatility_calc.join(", ")} lacked enough price history.
              </p>
            )}

            {risk.sector_exposures.length > 0 && (
              <div style={{ marginBottom: "1.25rem" }}>
                <p className="eyebrow" style={{ fontSize: "0.65rem", marginBottom: "0.5rem" }}>Sector exposure</p>
                {risk.sector_exposures.map((s) => (
                  <div key={s.sector} className="ledger-row" style={{ padding: "0.5rem 0" }}>
                    <span style={{ fontSize: "0.85rem" }}>{s.sector}</span>
                    <span className="num" style={{ fontSize: "0.85rem" }}>{pct(s.weight)}</span>
                  </div>
                ))}
              </div>
            )}

            {risk.pairwise_correlations.length > 0 && (
              <div>
                <p className="eyebrow" style={{ fontSize: "0.65rem", marginBottom: "0.5rem" }}>Pairwise correlation</p>
                {risk.pairwise_correlations.map((c) => (
                  <div key={`${c.ticker_a}-${c.ticker_b}`} className="ledger-row" style={{ padding: "0.4rem 0" }}>
                    <span className="num" style={{ fontSize: "0.82rem" }}>{c.ticker_a} · {c.ticker_b}</span>
                    <span className="num" style={{ fontSize: "0.82rem" }}>{c.correlation.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            )}

            <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.7rem", marginTop: "1.25rem", marginBottom: 0 }}>
              Parametric estimate assuming normally-distributed returns — a standard
              approximation, not a guarantee.
            </p>
          </div>
        </section>
      )}

      <section style={{ marginTop: "2.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
          <p className="eyebrow" style={{ margin: 0 }}>Recommendations</p>
          {!recommendations && (
            <button className="btn-primary" onClick={handleLoadRecommendations} disabled={recommendationsLoading} style={{ padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}>
              {recommendationsLoading ? "Computing…" : "Compute"}
            </button>
          )}
        </div>
        <div className="card">
          {recommendationsError && <p className="num loss" style={{ margin: 0, fontSize: "0.85rem" }}>{recommendationsError}</p>}
          {!recommendations && !recommendationsError && (
            <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
              Picks that would fill sector gaps this portfolio doesn't already have exposure to.
            </p>
          )}
          {recommendations && recommendations.picks.length === 0 && (
            <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>{recommendations.note}</p>
          )}
          {recommendations && recommendations.picks.length > 0 && (
            <>
              {recommendations.scoring_note && (
                <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.72rem", marginBottom: "0.75rem" }}>
                  {recommendations.scoring_note}
                </p>
              )}
              {recommendations.picks.map((p) => (
                <div key={p.ticker} className="ledger-row" style={{ padding: "0.5rem 0" }}>
                  <div>
                    <div style={{ fontWeight: 500 }}>{p.ticker}</div>
                    <div className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}>
                      Fills {p.gap_sector} gap (currently {(p.current_sector_weight * 100).toFixed(1)}%)
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div className="num" style={{ fontSize: "0.95rem" }}>{usd(p.price)}</div>
                    {p.composite_score !== null && (
                      <div className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}>
                        score {p.composite_score.toFixed(2)}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </section>

      <section style={{ marginTop: "2.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
          <p className="eyebrow" style={{ margin: 0 }}>Rebalancing Suggestion</p>
          {!rebalance && (
            <button className="btn-primary" onClick={handleLoadRebalance} disabled={rebalanceLoading} style={{ padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}>
              {rebalanceLoading ? "Computing…" : "Compute"}
            </button>
          )}
        </div>
        <div className="card">
          {rebalanceError && <p className="num loss" style={{ margin: 0, fontSize: "0.85rem" }}>{rebalanceError}</p>}
          {!rebalance && !rebalanceError && (
            <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>
              Trims for any position over 30% of the portfolio, by default.
            </p>
          )}
          {rebalance && rebalance.suggestions.length === 0 && (
            <p style={{ margin: 0, color: "var(--text-soft)", fontSize: "0.9rem" }}>{rebalance.note}</p>
          )}
          {rebalance && rebalance.suggestions.map((s) => (
            <div key={s.ticker} className="ledger-row" style={{ padding: "0.5rem 0" }}>
              <div>
                <div style={{ fontWeight: 500 }}>{s.ticker}</div>
                <div className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}>
                  {(s.current_weight * 100).toFixed(1)}% → {(s.target_weight * 100).toFixed(1)}%
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div className="num" style={{ fontSize: "0.95rem" }}>Trim {s.shares_to_trim.toFixed(0)} sh</div>
                <div className="num" style={{ fontSize: "0.78rem", color: "var(--text-soft)" }}>
                  ~{usd(s.estimated_proceeds)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
    </AppShell>
  );
}
