from __future__ import annotations

from sqlalchemy import select

from src.domain.entities.watchlist import WatchlistItem
from src.domain.repositories.watchlist_repository import WatchlistRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import WatchlistItemModel


def _to_domain(row: WatchlistItemModel) -> WatchlistItem:
    return WatchlistItem(
        user_id=row.user_id,
        ticker=row.ticker,
        added_at=row.added_at,
        notes=row.notes,
        list_name=row.list_name,
        target_price=row.target_price,
        alert_threshold_pct=row.alert_threshold_pct,
        added_price=row.added_price,
        added_pe=row.added_pe,
    )


class SqlAlchemyWatchlistRepository(WatchlistRepository):
    def add(self, item: WatchlistItem) -> None:
        with session_scope() as session:
            existing = session.execute(
                select(WatchlistItemModel).where(
                    WatchlistItemModel.user_id == item.user_id,
                    WatchlistItemModel.list_name == item.list_name,
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
                        list_name=item.list_name,
                        target_price=item.target_price,
                        alert_threshold_pct=item.alert_threshold_pct,
                        added_price=item.added_price,
                        added_pe=item.added_pe,
                    )
                )
            else:
                existing.notes = item.notes
                existing.added_at = item.added_at
                existing.target_price = item.target_price
                existing.alert_threshold_pct = item.alert_threshold_pct
                existing.added_price = item.added_price
                existing.added_pe = item.added_pe

    def remove(self, user_id: str, ticker: str, list_name: str | None = None) -> bool:
        with session_scope() as session:
            query = select(WatchlistItemModel).where(
                WatchlistItemModel.user_id == user_id,
                WatchlistItemModel.ticker == ticker,
            )
            if list_name is not None:
                query = query.where(WatchlistItemModel.list_name == list_name)
            rows = session.execute(query).scalars().all()
            if not rows:
                return False
            for row in rows:
                session.delete(row)
            return True

    def get(self, user_id: str, ticker: str, list_name: str) -> WatchlistItem | None:
        with session_scope() as session:
            row = session.execute(
                select(WatchlistItemModel).where(
                    WatchlistItemModel.user_id == user_id,
                    WatchlistItemModel.ticker == ticker.strip().upper(),
                    WatchlistItemModel.list_name == list_name,
                )
            ).scalar_one_or_none()
            return _to_domain(row) if row else None

    def list_for_user(self, user_id: str, list_name: str | None = None) -> list[WatchlistItem]:
        with session_scope() as session:
            query = (
                select(WatchlistItemModel)
                .where(WatchlistItemModel.user_id == user_id)
                .order_by(WatchlistItemModel.added_at.desc())
            )
            if list_name is not None:
                query = query.where(WatchlistItemModel.list_name == list_name)
            rows = session.execute(query).scalars().all()
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
