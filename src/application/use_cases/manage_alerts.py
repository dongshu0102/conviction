from __future__ import annotations

from src.domain.entities.monitoring import Alert
from src.domain.repositories.monitoring_repository import AlertRepository


class GetAlertsUseCase:
    def __init__(self, alert_repo: AlertRepository) -> None:
        self._alert_repo = alert_repo

    def execute(self, user_id: str, unread_only: bool = False) -> list[Alert]:
        return self._alert_repo.list_for_user(user_id, unread_only=unread_only)


class MarkAlertReadUseCase:
    def __init__(self, alert_repo: AlertRepository) -> None:
        self._alert_repo = alert_repo

    def execute(self, user_id: str, alert_id: int) -> bool:
        return self._alert_repo.mark_read(user_id, alert_id)
