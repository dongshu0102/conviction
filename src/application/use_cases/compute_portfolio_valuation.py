"""Use case: compute live portfolio valuation.

Deterministic arithmetic over live quotes, same principle as
ComputeValuationUseCase — no LLM involved, exact numbers. This reuses
FinancialDataProvider.get_quote, the exact same method the single-company
Valuation Agent uses, so a position's price here and its price via
GET /companies/{ticker}/valuation are guaranteed to come from the same
source with the same logic — no risk of two "current price" numbers
silently diverging.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.application.use_cases.manage_portfolio import PortfolioNotFoundError
from src.domain.entities.portfolio_valuation import PortfolioValuation, PositionValue
from src.domain.repositories.portfolio_repository import PortfolioRepository


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


class ComputePortfolioValuationUseCase:
    def __init__(
        self, portfolio_repo: PortfolioRepository, data_provider: FinancialDataProvider
    ) -> None:
        self._portfolio_repo = portfolio_repo
        self._data_provider = data_provider

    def execute(self, portfolio_id: str) -> PortfolioValuation:
        portfolio = self._portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)

        # Fetch all quotes first, before computing anything — a failure
        # partway through must not leave the caller with a valuation that
        # silently priced only some positions.
        quotes_by_ticker = {}
        for holding in portfolio.holdings:
            try:
                quotes_by_ticker[holding.ticker] = self._data_provider.get_quote(holding.ticker)
            except DataProviderError:
                raise

        positions_raw = []
        total_market_value = 0.0
        total_cost_basis = 0.0

        for holding in portfolio.holdings:
            quote = quotes_by_ticker[holding.ticker]
            market_value = holding.shares * quote.price
            cost_basis_total = holding.shares * holding.cost_basis_per_share
            unrealized_gain = market_value - cost_basis_total

            positions_raw.append(
                {
                    "ticker": holding.ticker,
                    "shares": holding.shares,
                    "cost_basis_per_share": holding.cost_basis_per_share,
                    "current_price": quote.price,
                    "market_value": market_value,
                    "cost_basis_total": cost_basis_total,
                    "unrealized_gain": unrealized_gain,
                    "unrealized_gain_pct": _safe_div(unrealized_gain, cost_basis_total),
                }
            )
            total_market_value += market_value
            total_cost_basis += cost_basis_total

        positions = [
            PositionValue(
                **p,
                weight=_safe_div(p["market_value"], total_market_value),
            )
            for p in positions_raw
        ]

        total_unrealized_gain = total_market_value - total_cost_basis

        return PortfolioValuation(
            portfolio_id=portfolio.portfolio_id,
            name=portfolio.name,
            as_of=datetime.now(timezone.utc),
            positions=positions,
            total_market_value=total_market_value,
            total_cost_basis=total_cost_basis,
            total_unrealized_gain=total_unrealized_gain,
            total_unrealized_gain_pct=_safe_div(total_unrealized_gain, total_cost_basis),
        )
