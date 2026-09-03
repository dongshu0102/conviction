from __future__ import annotations

from sqlalchemy import select

from src.domain.entities.bond import BondHolding, BondIdentity
from src.domain.entities.option import OptionContract, OptionHolding
from src.domain.entities.portfolio import Portfolio, PortfolioHolding
from src.domain.repositories.portfolio_repository import PortfolioRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import (
    BondHoldingModel,
    OptionHoldingModel,
    PortfolioHoldingModel,
    PortfolioModel,
)


def _holding_to_domain(row: PortfolioHoldingModel) -> PortfolioHolding:
    return PortfolioHolding(
        ticker=row.ticker,
        shares=row.shares,
        cost_basis_per_share=row.cost_basis_per_share,
        acquired_at=row.acquired_at,
    )


def _option_holding_to_domain(row: OptionHoldingModel) -> OptionHolding:
    return OptionHolding(
        contract=OptionContract(
            underlying_ticker=row.underlying_ticker,
            strike=row.strike,
            expiration=row.expiration,
            option_type=row.option_type,
        ),
        contracts_held=row.contracts_held,
        cost_basis_per_contract=row.cost_basis_per_contract,
        acquired_at=row.acquired_at,
    )


def _bond_holding_to_domain(row: BondHoldingModel) -> BondHolding:
    return BondHolding(
        bond=BondIdentity(
            cusip=row.cusip,
            issuer_name=row.issuer_name,
            coupon_rate=row.coupon_rate,
            maturity_date=row.maturity_date,
            face_value=row.face_value,
        ),
        quantity=row.quantity,
        cost_basis_price=row.cost_basis_price,
        acquired_at=row.acquired_at,
    )


def _portfolio_to_domain(row: PortfolioModel, include_holdings: bool) -> Portfolio:
    return Portfolio(
        portfolio_id=row.portfolio_id,
        user_id=row.user_id,
        name=row.name,
        created_at=row.created_at,
        holdings=[_holding_to_domain(h) for h in row.holdings] if include_holdings else [],
        option_holdings=(
            [_option_holding_to_domain(h) for h in row.option_holdings]
            if include_holdings
            else []
        ),
        bond_holdings=(
            [_bond_holding_to_domain(h) for h in row.bond_holdings]
            if include_holdings
            else []
        ),
    )


class SqlAlchemyPortfolioRepository(PortfolioRepository):
    def create(self, portfolio: Portfolio) -> None:
        with session_scope() as session:
            session.add(
                PortfolioModel(
                    portfolio_id=portfolio.portfolio_id,
                    user_id=portfolio.user_id,
                    name=portfolio.name,
                    created_at=portfolio.created_at,
                )
            )

    def get_by_id(self, portfolio_id: str) -> Portfolio | None:
        with session_scope() as session:
            row = session.get(PortfolioModel, portfolio_id)
            return _portfolio_to_domain(row, include_holdings=True) if row else None

    def list_for_user(self, user_id: str) -> list[Portfolio]:
        with session_scope() as session:
            rows = session.execute(
                select(PortfolioModel).where(PortfolioModel.user_id == user_id)
            ).scalars().all()
            return [_portfolio_to_domain(row, include_holdings=False) for row in rows]

    def delete(self, portfolio_id: str) -> bool:
        with session_scope() as session:
            row = session.get(PortfolioModel, portfolio_id)
            if row is None:
                return False
            session.delete(row)
            return True

    def upsert_holding(self, portfolio_id: str, holding: PortfolioHolding) -> None:
        with session_scope() as session:
            existing = session.execute(
                select(PortfolioHoldingModel).where(
                    PortfolioHoldingModel.portfolio_id == portfolio_id,
                    PortfolioHoldingModel.ticker == holding.ticker,
                )
            ).scalar_one_or_none()

            if existing is None:
                session.add(
                    PortfolioHoldingModel(
                        portfolio_id=portfolio_id,
                        ticker=holding.ticker,
                        shares=holding.shares,
                        cost_basis_per_share=holding.cost_basis_per_share,
                        acquired_at=holding.acquired_at,
                    )
                )
            else:
                existing.shares = holding.shares
                existing.cost_basis_per_share = holding.cost_basis_per_share
                existing.acquired_at = holding.acquired_at

    def remove_holding(self, portfolio_id: str, ticker: str) -> bool:
        with session_scope() as session:
            existing = session.execute(
                select(PortfolioHoldingModel).where(
                    PortfolioHoldingModel.portfolio_id == portfolio_id,
                    PortfolioHoldingModel.ticker == ticker,
                )
            ).scalar_one_or_none()
            if existing is None:
                return False
            session.delete(existing)
            return True

    def upsert_option_holding(self, portfolio_id: str, holding: OptionHolding) -> None:
        with session_scope() as session:
            c = holding.contract
            existing = session.execute(
                select(OptionHoldingModel).where(
                    OptionHoldingModel.portfolio_id == portfolio_id,
                    OptionHoldingModel.underlying_ticker == c.underlying_ticker,
                    OptionHoldingModel.strike == c.strike,
                    OptionHoldingModel.expiration == c.expiration,
                    OptionHoldingModel.option_type == c.option_type,
                )
            ).scalar_one_or_none()

            if existing is None:
                session.add(
                    OptionHoldingModel(
                        portfolio_id=portfolio_id,
                        underlying_ticker=c.underlying_ticker,
                        strike=c.strike,
                        expiration=c.expiration,
                        option_type=c.option_type,
                        contracts_held=holding.contracts_held,
                        cost_basis_per_contract=holding.cost_basis_per_contract,
                        acquired_at=holding.acquired_at,
                    )
                )
            else:
                existing.contracts_held = holding.contracts_held
                existing.cost_basis_per_contract = holding.cost_basis_per_contract
                existing.acquired_at = holding.acquired_at

    def remove_option_holding(self, portfolio_id: str, contract: OptionContract) -> bool:
        with session_scope() as session:
            existing = session.execute(
                select(OptionHoldingModel).where(
                    OptionHoldingModel.portfolio_id == portfolio_id,
                    OptionHoldingModel.underlying_ticker == contract.underlying_ticker,
                    OptionHoldingModel.strike == contract.strike,
                    OptionHoldingModel.expiration == contract.expiration,
                    OptionHoldingModel.option_type == contract.option_type,
                )
            ).scalar_one_or_none()
            if existing is None:
                return False
            session.delete(existing)
            return True

    def upsert_bond_holding(self, portfolio_id: str, holding: BondHolding) -> None:
        with session_scope() as session:
            b = holding.bond
            existing = session.execute(
                select(BondHoldingModel).where(
                    BondHoldingModel.portfolio_id == portfolio_id,
                    BondHoldingModel.issuer_name == b.issuer_name,
                    BondHoldingModel.coupon_rate == b.coupon_rate,
                    BondHoldingModel.maturity_date == b.maturity_date,
                )
            ).scalar_one_or_none()

            if existing is None:
                session.add(
                    BondHoldingModel(
                        portfolio_id=portfolio_id,
                        cusip=b.cusip,
                        issuer_name=b.issuer_name,
                        coupon_rate=b.coupon_rate,
                        maturity_date=b.maturity_date,
                        face_value=b.face_value,
                        quantity=holding.quantity,
                        cost_basis_price=holding.cost_basis_price,
                        acquired_at=holding.acquired_at,
                    )
                )
            else:
                existing.cusip = b.cusip
                existing.face_value = b.face_value
                existing.quantity = holding.quantity
                existing.cost_basis_price = holding.cost_basis_price
                existing.acquired_at = holding.acquired_at

    def remove_bond_holding(self, portfolio_id: str, bond: BondIdentity) -> bool:
        with session_scope() as session:
            existing = session.execute(
                select(BondHoldingModel).where(
                    BondHoldingModel.portfolio_id == portfolio_id,
                    BondHoldingModel.issuer_name == bond.issuer_name,
                    BondHoldingModel.coupon_rate == bond.coupon_rate,
                    BondHoldingModel.maturity_date == bond.maturity_date,
                )
            ).scalar_one_or_none()
            if existing is None:
                return False
            session.delete(existing)
            return True
