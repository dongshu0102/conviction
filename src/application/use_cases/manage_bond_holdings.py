"""Use cases for managing bond holdings within a portfolio.

Same "state, not a transaction log" principle as PortfolioHolding and
OptionHolding -- adding the same bond (same issuer + coupon rate +
maturity date) again updates the position rather than appending a
trade.

Deliberately does NOT validate the issuer against our ingested company
universe -- same reasoning as option holdings: a bond can be issued by
an entity that was never in scope for equity ingestion (a municipality,
a foreign government, a private company), and requiring "ingest this
as a company first" would be a nonsensical requirement for a Treasury
or municipal bond.
"""
from __future__ import annotations

from datetime import date

from src.application.use_cases.manage_portfolio import PortfolioNotFoundError
from src.domain.entities.bond import BondHolding, BondIdentity
from src.domain.repositories.portfolio_repository import PortfolioRepository


class AddBondHoldingUseCase:
    def __init__(self, portfolio_repo: PortfolioRepository) -> None:
        self._portfolio_repo = portfolio_repo

    def execute(
        self,
        portfolio_id: str,
        issuer_name: str,
        coupon_rate: float,
        maturity_date: date,
        quantity: int,
        cost_basis_price: float,
        cusip: str | None = None,
        face_value: float = 1000.0,
        acquired_at: date | None = None,
    ) -> BondHolding:
        if self._portfolio_repo.get_by_id(portfolio_id) is None:
            raise PortfolioNotFoundError(portfolio_id)

        bond = BondIdentity(
            cusip=cusip.strip().upper() if cusip else None,
            issuer_name=issuer_name.strip(),
            coupon_rate=coupon_rate,
            maturity_date=maturity_date,
            face_value=face_value,
        )
        holding = BondHolding(
            bond=bond, quantity=quantity, cost_basis_price=cost_basis_price, acquired_at=acquired_at,
        )
        self._portfolio_repo.upsert_bond_holding(portfolio_id, holding)
        return holding


class RemoveBondHoldingUseCase:
    def __init__(self, portfolio_repo: PortfolioRepository) -> None:
        self._portfolio_repo = portfolio_repo

    def execute(
        self, portfolio_id: str, issuer_name: str, coupon_rate: float, maturity_date: date,
    ) -> bool:
        bond = BondIdentity(
            cusip=None, issuer_name=issuer_name.strip(), coupon_rate=coupon_rate, maturity_date=maturity_date,
        )
        return self._portfolio_repo.remove_bond_holding(portfolio_id, bond)
