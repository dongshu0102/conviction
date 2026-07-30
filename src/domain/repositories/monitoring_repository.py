from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.monitoring import Alert, PriceSnapshot


class PriceSnapshotRepository(ABC):
    @abstractmethod
    def get_latest(self, ticker: str) -> PriceSnapshot | None: ...

    @abstractmethod
    def save(self, snapshot: PriceSnapshot) -> None:
        """Upsert by ticker — one snapshot per ticker, always the most
        recent monitoring run's observation, not a full price history."""


class AlertRepository(ABC):
    @abstractmethod
    def save(self, alert: Alert) -> Alert:
        """Returns the alert with its DB-assigned id populated."""

    @abstractmethod
    def list_for_user(self, user_id: str, unread_only: bool = False) -> list[Alert]: ...

    @abstractmethod
    def mark_read(self, user_id: str, alert_id: int) -> bool: ...
