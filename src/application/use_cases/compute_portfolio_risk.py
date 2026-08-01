"""Use case: compute portfolio risk metrics.

Deliberately a composition over existing use cases rather than a new
data path: reuses ComputePortfolioValuationUseCase for weights,
ComputeFinancialAnalysisUseCase for leverage ratios, and
CompanyRepository for sector. This is the payoff of the layering used
throughout the platform — a "new agent" here means combining outputs
that already exist, not building new infrastructure.

Volatility/correlation is an ADDITIVE, OPTIONAL extension: data_provider
defaults to None so every existing caller keeps working with just
concentration + leverage, exactly as before. When a data_provider that
supports get_daily_closes is supplied, the report also gets portfolio
volatility, parametric VaR, and pairwise correlations — computed from
live price history (Phase C), never stored locally.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.manage_portfolio import PortfolioNotFoundError
from src.domain.entities.portfolio_risk import (
    PairwiseCorrelation,
    PortfolioRiskAnalysis,
    SectorExposure,
)
from src.domain.repositories.company_repository import CompanyRepository
from src.domain.services.portfolio_risk_math import (
    annualize_volatility,
    compute_simple_returns,
    correlation as compute_correlation,
    parametric_var,
    portfolio_variance,
    trim_to_common_length,
)

logger = logging.getLogger(__name__)

# ~3 months of trading days — long enough for a stable covariance
# estimate, short enough to reflect current regime rather than stale
# history.
LOOKBACK_TRADING_DAYS = 60
MIN_RETURN_OBSERVATIONS = 20


class ComputePortfolioRiskUseCase:
    def __init__(
        self,
        compute_valuation: ComputePortfolioValuationUseCase,
        compute_analysis: ComputeFinancialAnalysisUseCase,
        company_repo: CompanyRepository,
        data_provider=None,
    ) -> None:
        self._compute_valuation = compute_valuation
        self._compute_analysis = compute_analysis
        self._company_repo = company_repo
        self._data_provider = data_provider

    def execute(self, portfolio_id: str) -> PortfolioRiskAnalysis:
        try:
            valuation = self._compute_valuation.execute(portfolio_id)
        except PortfolioNotFoundError:
            raise

        if not valuation.positions:
            return PortfolioRiskAnalysis(
                portfolio_id=portfolio_id,
                as_of=datetime.now(timezone.utc),
                largest_position_weight=None,
                herfindahl_index=None,
            )

        weights = [p.weight for p in valuation.positions if p.weight is not None]
        largest_position_weight = max(weights) if weights else None
        herfindahl_index = sum(w * w for w in weights) if weights else None

        sector_weights: dict[str, float] = defaultdict(float)
        for position in valuation.positions:
            if position.weight is None:
                continue
            company = self._company_repo.get_by_ticker(position.ticker)
            sector = company.sector.value if company else "Unknown"
            sector_weights[sector] += position.weight

        sector_exposures = [
            SectorExposure(sector=sector, weight=weight)
            for sector, weight in sorted(sector_weights.items(), key=lambda x: -x[1])
        ]

        weighted_leverage_sum = 0.0
        weighted_leverage_total_weight = 0.0
        excluded: list[str] = []

        for position in valuation.positions:
            if position.weight is None:
                excluded.append(position.ticker)
                continue
            analysis = self._compute_analysis.execute(position.ticker, years=1)
            if not analysis.yearly_ratios or analysis.yearly_ratios[-1].debt_to_equity is None:
                excluded.append(position.ticker)
                continue
            latest_ratios = analysis.yearly_ratios[-1]
            weighted_leverage_sum += latest_ratios.debt_to_equity * position.weight
            weighted_leverage_total_weight += position.weight

        weighted_avg_debt_to_equity = (
            weighted_leverage_sum / weighted_leverage_total_weight
            if weighted_leverage_total_weight > 0
            else None
        )

        vol_result = self._compute_volatility_block(valuation.positions, valuation.total_market_value)

        return PortfolioRiskAnalysis(
            portfolio_id=portfolio_id,
            as_of=datetime.now(timezone.utc),
            largest_position_weight=largest_position_weight,
            herfindahl_index=herfindahl_index,
            sector_exposures=sector_exposures,
            weighted_avg_debt_to_equity=weighted_avg_debt_to_equity,
            excluded_from_leverage_calc=excluded,
            portfolio_daily_volatility=vol_result["daily_volatility"],
            portfolio_annualized_volatility=vol_result["annualized_volatility"],
            parametric_var_95_1day_dollar=vol_result["var_95_1day_dollar"],
            volatility_covered_weight=vol_result["covered_weight"],
            volatility_lookback_days_used=vol_result["lookback_days_used"],
            pairwise_correlations=vol_result["pairwise_correlations"],
            excluded_from_volatility_calc=vol_result["excluded"],
        )

    def _compute_volatility_block(self, positions, total_market_value: float) -> dict:
        """Returns an all-None/empty dict if no data_provider was
        supplied, or if it doesn't support get_daily_closes — the rest
        of the risk report is entirely unaffected either way."""
        empty = {
            "daily_volatility": None, "annualized_volatility": None,
            "var_95_1day_dollar": None, "covered_weight": None,
            "lookback_days_used": None, "pairwise_correlations": [], "excluded": [],
        }
        if self._data_provider is None or not hasattr(self._data_provider, "get_daily_closes"):
            return empty

        priced_positions = [p for p in positions if p.weight is not None]
        returns_by_ticker: dict[str, list[float]] = {}
        fetch_failed: list[str] = []

        for position in priced_positions:
            try:
                bars = self._data_provider.get_daily_closes(
                    position.ticker, limit=LOOKBACK_TRADING_DAYS + 1
                )
            except Exception as exc:  # noqa: BLE001 — one bad ticker must never abort the report
                logger.warning("Risk: price history unavailable for %s: %s", position.ticker, exc)
                fetch_failed.append(position.ticker)
                continue
            closes = [b.close for b in bars]
            returns_by_ticker[position.ticker] = compute_simple_returns(closes)

        aligned, too_short = trim_to_common_length(returns_by_ticker, MIN_RETURN_OBSERVATIONS)
        excluded = sorted(set(fetch_failed) | set(too_short))

        if not aligned:
            empty["excluded"] = excluded
            return empty

        weight_by_ticker = {p.ticker: p.weight for p in priced_positions}
        covered_weight = sum(weight_by_ticker[t] for t in aligned)
        if covered_weight == 0:
            empty["excluded"] = excluded
            return empty

        normalized_weights = {t: weight_by_ticker[t] / covered_weight for t in aligned}
        variance = portfolio_variance(normalized_weights, aligned)
        if variance is None or variance < 0:
            empty["excluded"] = excluded
            return empty

        daily_vol = variance ** 0.5
        annualized_vol = annualize_volatility(daily_vol)
        covered_market_value = total_market_value * covered_weight
        var_95 = parametric_var(covered_market_value, daily_vol)

        pairwise: list[PairwiseCorrelation] = []
        tickers = sorted(aligned.keys())
        for i, ticker_a in enumerate(tickers):
            for ticker_b in tickers[i + 1:]:
                corr = compute_correlation(aligned[ticker_a], aligned[ticker_b])
                if corr is not None:
                    pairwise.append(
                        PairwiseCorrelation(ticker_a=ticker_a, ticker_b=ticker_b, correlation=corr)
                    )

        return {
            "daily_volatility": daily_vol,
            "annualized_volatility": annualized_vol,
            "var_95_1day_dollar": var_95,
            "covered_weight": covered_weight,
            "lookback_days_used": len(next(iter(aligned.values()))),
            "pairwise_correlations": pairwise,
            "excluded": excluded,
        }
