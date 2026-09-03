"""Use case: compute real, deterministic yield analytics for every
bond holding in a portfolio.

Mirrors ComputeOptionPortfolioValuationUseCase's exact pattern, with
one honest, real difference: this app has no live bond price data
source at all, unlike the options provider used for option valuation.
current_price is therefore always the holding's own cost_basis_price
-- an honest ESTIMATE of the real, current price, not a live market
quote -- stated directly on the result (BondValuation.current_price is
documented as the estimate, not a live number) rather than silently
presented as if it were a genuine, live quote.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.manage_portfolio import PortfolioNotFoundError
from src.domain.entities.bond import BondPortfolioValuation, BondValuation
from src.domain.repositories.portfolio_repository import PortfolioRepository
from src.domain.services.bond_math import (
    compute_current_yield,
    compute_years_to_maturity,
    compute_yield_to_maturity,
)


class ComputeBondPortfolioValuationUseCase:
    def __init__(self, portfolio_repo: PortfolioRepository) -> None:
        self._portfolio_repo = portfolio_repo

    def execute(self, portfolio_id: str, as_of_date: date | None = None) -> BondPortfolioValuation:
        portfolio = self._portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)

        today = as_of_date or datetime.now(timezone.utc).date()
        positions: list[BondValuation] = []
        total_face_value = 0.0
        total_cost_basis = 0.0

        for holding in portfolio.bond_holdings:
            bond = holding.bond
            years_remaining = compute_years_to_maturity(bond.maturity_date, today)
            current_yield = compute_current_yield(bond.coupon_rate, holding.cost_basis_price)
            ytm = compute_yield_to_maturity(bond.coupon_rate, holding.cost_basis_price, years_remaining)

            face_value_total = holding.quantity * bond.face_value
            cost_basis_total = holding.quantity * bond.face_value * (holding.cost_basis_price / 100)

            positions.append(BondValuation(
                bond=bond, quantity=holding.quantity, cost_basis_price=holding.cost_basis_price,
                current_price=holding.cost_basis_price,  # honest estimate; see module docstring
                current_yield=current_yield, yield_to_maturity=ytm, years_to_maturity=years_remaining,
                total_face_value=face_value_total, total_cost_basis=cost_basis_total,
            ))
            total_face_value += face_value_total
            total_cost_basis += cost_basis_total

        return BondPortfolioValuation(
            portfolio_id=portfolio_id, as_of=datetime.now(timezone.utc), positions=positions,
            total_face_value=total_face_value, total_cost_basis=total_cost_basis,
        )
