"""Use case: suggest position trims to reduce over-concentration.

Deterministic, not LLM-reasoned — same principle as
ComputeFinancialAnalysisUseCase: financial arithmetic (how many shares
to sell to hit a target weight) is exact math, not something to trust
a language model to approximate. The chat agent's job is to decide
WHEN to call this and how to phrase the result conversationally, never
to compute the numbers itself.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.domain.entities.rebalancing import RebalancingPlan, RebalancingSuggestion

DEFAULT_TARGET_MAX_WEIGHT = 0.30  # no single position above 30% of the portfolio


class SuggestRebalancingUseCase:
    def __init__(self, compute_valuation: ComputePortfolioValuationUseCase) -> None:
        self._compute_valuation = compute_valuation

    def execute(
        self, portfolio_id: str, target_max_weight: float = DEFAULT_TARGET_MAX_WEIGHT
    ) -> RebalancingPlan:
        valuation = self._compute_valuation.execute(portfolio_id)
        suggestions: list[RebalancingSuggestion] = []

        for position in valuation.positions:
            if position.weight is None or position.weight <= target_max_weight:
                continue
            if position.current_price <= 0:
                continue  # can't compute a meaningful share count against a zero price

            target_value = target_max_weight * valuation.total_market_value
            excess_value = position.market_value - target_value
            shares_to_trim = excess_value / position.current_price

            suggestions.append(
                RebalancingSuggestion(
                    ticker=position.ticker,
                    current_weight=position.weight,
                    target_weight=target_max_weight,
                    shares_to_trim=shares_to_trim,
                    estimated_proceeds=shares_to_trim * position.current_price,
                )
            )

        # Largest excess first — the most impactful trim is the most
        # relevant thing to lead with in a conversational reply.
        suggestions.sort(key=lambda s: s.current_weight, reverse=True)

        return RebalancingPlan(
            portfolio_id=portfolio_id,
            as_of=datetime.now(timezone.utc),
            target_max_weight=target_max_weight,
            suggestions=suggestions,
        )
