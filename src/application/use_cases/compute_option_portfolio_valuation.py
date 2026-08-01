"""Use case: compute live valuation and P&L for option holdings.

Mirrors ComputePortfolioValuationUseCase's exact pattern for stocks —
deterministic arithmetic over live quotes, no LLM involved. Deliberately
a SEPARATE use case rather than folded into the stock valuation
use case: options data can fail independently (as it did during real
testing — a 402 paywall error from the provider), and that must never
break the widely-used, previously-100%-reliable stock valuation path.
Same principle as ComputePortfolioGreeksUseCase being separate from
ComputePortfolioRiskUseCase.

Uses `mid` price when available (the standard field for valuation,
avoiding bid-ask spread bias), falling back to `last` if mid is
missing — same "best available real number, never fabricated" spirit
as elsewhere. A position with NEITHER available is excluded, not
zeroed.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.interfaces.options_data_provider import OptionsDataProvider
from src.application.use_cases.manage_portfolio import PortfolioNotFoundError
from src.domain.entities.option import OptionPortfolioValuation, OptionPositionValue
from src.domain.repositories.portfolio_repository import PortfolioRepository

CONTRACT_MULTIPLIER = 100  # standard: 1 option contract = 100 shares of the underlying


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


class ComputeOptionPortfolioValuationUseCase:
    def __init__(
        self, portfolio_repo: PortfolioRepository, options_provider: OptionsDataProvider
    ) -> None:
        self._portfolio_repo = portfolio_repo
        self._options_provider = options_provider

    def execute(self, portfolio_id: str) -> OptionPortfolioValuation:
        portfolio = self._portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)

        positions: list[OptionPositionValue] = []
        excluded: list[str] = []
        total_market_value = 0.0
        total_cost_basis = 0.0

        for holding in portfolio.option_holdings:
            quote = self._options_provider.get_option_quote(holding.contract)
            current_price = None
            if quote is not None:
                current_price = quote.mid if quote.mid is not None else quote.last

            if current_price is None:
                excluded.append(holding.contract.occ_symbol_fragment)
                continue

            market_value = holding.contracts_held * current_price * CONTRACT_MULTIPLIER
            cost_basis_total = (
                holding.contracts_held * holding.cost_basis_per_contract * CONTRACT_MULTIPLIER
            )
            unrealized_gain = market_value - cost_basis_total

            positions.append(
                OptionPositionValue(
                    contract=holding.contract,
                    contracts_held=holding.contracts_held,
                    cost_basis_per_contract=holding.cost_basis_per_contract,
                    current_price=current_price,
                    market_value=market_value,
                    cost_basis_total=cost_basis_total,
                    unrealized_gain=unrealized_gain,
                    unrealized_gain_pct=_safe_div(unrealized_gain, abs(cost_basis_total)),
                )
            )
            total_market_value += market_value
            total_cost_basis += cost_basis_total

        total_unrealized_gain = total_market_value - total_cost_basis

        return OptionPortfolioValuation(
            portfolio_id=portfolio_id,
            as_of=datetime.now(timezone.utc),
            positions=positions,
            total_market_value=total_market_value,
            total_cost_basis=total_cost_basis,
            total_unrealized_gain=total_unrealized_gain,
            total_unrealized_gain_pct=_safe_div(total_unrealized_gain, abs(total_cost_basis)),
            positions_excluded=excluded,
        )
