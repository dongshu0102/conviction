from __future__ import annotations

from dataclasses import replace

from sqlalchemy import select

from src.domain.entities.monitoring import Alert, AlertType, PriceSnapshot
from src.domain.repositories.monitoring_repository import (
    AlertRepository,
    PriceSnapshotRepository,
)
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import AlertModel, PriceSnapshotModel


class SqlAlchemyPriceSnapshotRepository(PriceSnapshotRepository):
    def get_latest(self, ticker: str) -> PriceSnapshot | None:
        with session_scope() as session:
            row = session.get(PriceSnapshotModel, ticker.strip().upper())
            if row is None:
                return None
            return PriceSnapshot(ticker=row.ticker, price=row.price, captured_at=row.captured_at)

    def save(self, snapshot: PriceSnapshot) -> None:
        with session_scope() as session:
            existing = session.get(PriceSnapshotModel, snapshot.ticker)
            if existing is None:
                session.add(
                    PriceSnapshotModel(
                        ticker=snapshot.ticker, price=snapshot.price,
                        captured_at=snapshot.captured_at,
                    )
                )
            else:
                existing.price = snapshot.price
                existing.captured_at = snapshot.captured_at


class SqlAlchemyAlertRepository(AlertRepository):
    def save(self, alert: Alert) -> Alert:
        with session_scope() as session:
            row = AlertModel(
                user_id=alert.user_id, ticker=alert.ticker,
                alert_type=alert.alert_type.value, message=alert.message,
                change_pct=alert.change_pct, is_read=alert.is_read,
                created_at=alert.created_at,
            )
            session.add(row)
            session.flush()  # populate row.id before the session closes
            return replace(alert, id=row.id)

    def list_for_user(self, user_id: str, unread_only: bool = False) -> list[Alert]:
        with session_scope() as session:
            stmt = select(AlertModel).where(AlertModel.user_id == user_id)
            if unread_only:
                stmt = stmt.where(AlertModel.is_read.is_(False))
            stmt = stmt.order_by(AlertModel.created_at.desc())
            rows = session.execute(stmt).scalars().all()
            return [
                Alert(
                    user_id=row.user_id, ticker=row.ticker,
                    alert_type=AlertType(row.alert_type), message=row.message,
                    created_at=row.created_at, change_pct=row.change_pct,
                    is_read=row.is_read, id=row.id,
                )
                for row in rows
            ]

    def mark_read(self, user_id: str, alert_id: int) -> bool:
        with session_scope() as session:
            row = session.get(AlertModel, alert_id)
            if row is None or row.user_id != user_id:
                return False
            row.is_read = True
            return True
