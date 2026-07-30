"""Use case: compute portfolio risk metrics.

Deliberately a composition over existing use cases rather than a new
data path: reuses ComputePortfolioValuationUseCase for weights,
ComputeFinancialAnalysisUseCase for leverage ratios, and
CompanyRepository for sector. This is the payoff of the layering used
throughout the platform — a "new agent" here means combining outputs
that already exist, not building new infrastructure.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.manage_portfolio import PortfolioNotFoundError
from src.domain.entities.portfolio_risk import PortfolioRiskAnalysis, SectorExposure
from src.domain.repositories.company_repository import CompanyRepository


class ComputePortfolioRiskUseCase:
    def __init__(
        self,
        compute_valuation: ComputePortfolioValuationUseCase,
        compute_analysis: ComputeFinancialAnalysisUseCase,
        company_repo: CompanyRepository,
    ) -> None:
        self._compute_valuation = compute_valuation
        self._compute_analysis = compute_analysis
        self._company_repo = company_repo

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

        return PortfolioRiskAnalysis(
            portfolio_id=portfolio_id,
            as_of=datetime.now(timezone.utc),
            largest_position_weight=largest_position_weight,
            herfindahl_index=herfindahl_index,
            sector_exposures=sector_exposures,
            weighted_avg_debt_to_equity=weighted_avg_debt_to_equity,
            excluded_from_leverage_calc=excluded,
        )
