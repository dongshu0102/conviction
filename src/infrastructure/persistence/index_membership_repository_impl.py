from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, select

from src.domain.repositories.index_membership_repository import IndexMembershipRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import IndexMembershipModel


class SqlAlchemyIndexMembershipRepository(IndexMembershipRepository):
    def save_memberships(self, ticker: str, index_names: list[str]) -> None:
        with session_scope() as session:
            # Scoped to this ticker alone, not the whole table --
            # same reasoning as ConvictionScreenerRepository.save_one.
            session.execute(delete(IndexMembershipModel).where(IndexMembershipModel.ticker == ticker))
            for index_name in index_names:
                session.add(IndexMembershipModel(ticker=ticker, index_name=index_name))

    def get_memberships_for_tickers(self, tickers: list[str]) -> dict[str, list[str]]:
        if not tickers:
            return {}
        with session_scope() as session:
            rows = session.execute(
                select(IndexMembershipModel).where(IndexMembershipModel.ticker.in_(tickers))
            ).scalars().all()
            result: dict[str, list[str]] = defaultdict(list)
            for row in rows:
                result[row.ticker].append(row.index_name)
            return dict(result)
