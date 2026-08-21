from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from src.domain.repositories.synced_order_repository import SyncedOrderRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import SyncedOrderModel


class SqlAlchemySyncedOrderRepository(SyncedOrderRepository):
    def is_already_synced(self, order_id: str) -> bool:
        with session_scope() as session:
            row = session.execute(
                select(SyncedOrderModel).where(SyncedOrderModel.order_id == order_id)
            ).scalar_one_or_none()
            return row is not None

    def record_sync(self, order_id: str, portfolio_id: str, ticker: str, synced_at: datetime) -> None:
        with session_scope() as session:
            session.add(SyncedOrderModel(
                order_id=order_id, portfolio_id=portfolio_id, ticker=ticker, synced_at=synced_at,
            ))
