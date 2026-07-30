from __future__ import annotations

from sqlalchemy import select

from src.domain.entities.portfolio import Portfolio, PortfolioHolding
from src.domain.repositories.portfolio_repository import PortfolioRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import PortfolioHoldingModel, PortfolioModel


def _holding_to_domain(row: PortfolioHoldingModel) -> PortfolioHolding:
    return PortfolioHolding(
        ticker=row.ticker,
        shares=row.shares,
        cost_basis_per_share=row.cost_basis_per_share,
        acquired_at=row.acquired_at,
    )


def _portfolio_to_domain(row: PortfolioModel, include_holdings: bool) -> Portfolio:
    return Portfolio(
        portfolio_id=row.portfolio_id,
        user_id=row.user_id,
        name=row.name,
        created_at=row.created_at,
        holdings=[_holding_to_domain(h) for h in row.holdings] if include_holdings else [],
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
