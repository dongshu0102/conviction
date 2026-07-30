from __future__ import annotations

from sqlalchemy import select

from src.domain.entities.watchlist import WatchlistItem
from src.domain.repositories.watchlist_repository import WatchlistRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import WatchlistItemModel


def _to_domain(row: WatchlistItemModel) -> WatchlistItem:
    return WatchlistItem(
        user_id=row.user_id, ticker=row.ticker, added_at=row.added_at, notes=row.notes
    )


class SqlAlchemyWatchlistRepository(WatchlistRepository):
    def add(self, item: WatchlistItem) -> None:
        with session_scope() as session:
            existing = session.execute(
                select(WatchlistItemModel).where(
                    WatchlistItemModel.user_id == item.user_id,
                    WatchlistItemModel.ticker == item.ticker,
                )
            ).scalar_one_or_none()

            if existing is None:
                session.add(
                    WatchlistItemModel(
                        user_id=item.user_id,
                        ticker=item.ticker,
                        added_at=item.added_at,
                        notes=item.notes,
                    )
                )
            else:
                existing.notes = item.notes
                existing.added_at = item.added_at

    def remove(self, user_id: str, ticker: str) -> bool:
        with session_scope() as session:
            existing = session.execute(
                select(WatchlistItemModel).where(
                    WatchlistItemModel.user_id == user_id,
                    WatchlistItemModel.ticker == ticker,
                )
            ).scalar_one_or_none()
            if existing is None:
                return False
            session.delete(existing)
            return True

    def list_for_user(self, user_id: str) -> list[WatchlistItem]:
        with session_scope() as session:
            rows = session.execute(
                select(WatchlistItemModel)
                .where(WatchlistItemModel.user_id == user_id)
                .order_by(WatchlistItemModel.added_at.desc())
            ).scalars().all()
            return [_to_domain(row) for row in rows]

    def contains(self, user_id: str, ticker: str) -> bool:
        with session_scope() as session:
            existing = session.execute(
                select(WatchlistItemModel).where(
                    WatchlistItemModel.user_id == user_id,
                    WatchlistItemModel.ticker == ticker.strip().upper(),
                )
            ).scalar_one_or_none()
            return existing is not None
