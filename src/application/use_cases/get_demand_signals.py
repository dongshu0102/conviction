"""Use case: compute real "Demand Signals" for one ticker, combining
three, real, already-existing, hand-verified pieces of this app's own
data -- built directly on top of the existing use cases, never
duplicating their own, real data-fetching logic.
"""
from __future__ import annotations

from src.application.use_cases.classify_economic_cycle import ClassifyEconomicCycleUseCase
from src.application.use_cases.compute_financial_analysis import ComputeFinancialAnalysisUseCase
from src.application.use_cases.get_analyst_ratings import GetAnalystRatingsUseCase
from src.domain.services.demand_signals_math import (
    DemandSignals,
    compute_analyst_consensus_direction,
    compute_revenue_growth_acceleration,
)


class GetDemandSignalsUseCase:
    def __init__(
        self,
        financial_analysis_use_case: ComputeFinancialAnalysisUseCase,
        analyst_ratings_use_case: GetAnalystRatingsUseCase,
        economic_cycle_use_case: ClassifyEconomicCycleUseCase,
    ) -> None:
        self._financial_analysis_use_case = financial_analysis_use_case
        self._analyst_ratings_use_case = analyst_ratings_use_case
        self._economic_cycle_use_case = economic_cycle_use_case

    def execute(self, ticker: str) -> DemandSignals:
        ticker = ticker.strip().upper()

        analysis = self._financial_analysis_use_case.execute(ticker)
        latest_growth = analysis.yearly_ratios[-1].revenue_growth_yoy if analysis.yearly_ratios else None
        prior_growth = (
            analysis.yearly_ratios[-2].revenue_growth_yoy if len(analysis.yearly_ratios) >= 2 else None
        )

        ratings = self._analyst_ratings_use_case.execute(ticker)
        upgrades = sum(1 for g in ratings.recent_grades if g.action == "upgrade") if ratings else 0
        downgrades = sum(1 for g in ratings.recent_grades if g.action == "downgrade") if ratings else 0
        avg_price_target = ratings.last_quarter_avg_price_target if ratings else None

        cycle = self._economic_cycle_use_case.execute()

        return DemandSignals(
            ticker=ticker,
            latest_revenue_growth_yoy=latest_growth,
            prior_revenue_growth_yoy=prior_growth,
            revenue_growth_accelerating=compute_revenue_growth_acceleration(latest_growth, prior_growth),
            recent_upgrades=upgrades,
            recent_downgrades=downgrades,
            analyst_consensus_direction=compute_analyst_consensus_direction(upgrades, downgrades),
            last_quarter_avg_price_target=avg_price_target,
            economic_cycle_state=cycle.state,
        )
