"""Alert API routes. Requires a valid API key (X-Api-Key header).

The manual-trigger endpoint exists for testing/demo convenience — real
scheduled monitoring runs via scripts/run_monitoring.py + cron, not
through this endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth import get_authenticated_user_id
from src.api.routers.companies import get_data_provider
from src.api.routers.watchlist import get_watchlist_repository
from src.api.schemas import AlertSchema
from src.application.use_cases.manage_alerts import GetAlertsUseCase, MarkAlertReadUseCase
from src.application.use_cases.run_monitoring_check import RunMonitoringCheckUseCase
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.monitoring_repository_impl import (
    SqlAlchemyAlertRepository,
    SqlAlchemyPriceSnapshotRepository,
)
from src.infrastructure.persistence.watchlist_repository_impl import (
    SqlAlchemyWatchlistRepository,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


def get_alert_repository() -> SqlAlchemyAlertRepository:
    return SqlAlchemyAlertRepository()


def get_snapshot_repository() -> SqlAlchemyPriceSnapshotRepository:
    return SqlAlchemyPriceSnapshotRepository()


def get_alerts_use_case(
    repo: SqlAlchemyAlertRepository = Depends(get_alert_repository),
) -> GetAlertsUseCase:
    return GetAlertsUseCase(repo)


def get_mark_read_use_case(
    repo: SqlAlchemyAlertRepository = Depends(get_alert_repository),
) -> MarkAlertReadUseCase:
    return MarkAlertReadUseCase(repo)


def get_monitoring_check_use_case(
    watchlist_repo: SqlAlchemyWatchlistRepository = Depends(get_watchlist_repository),
    snapshot_repo: SqlAlchemyPriceSnapshotRepository = Depends(get_snapshot_repository),
    alert_repo: SqlAlchemyAlertRepository = Depends(get_alert_repository),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> RunMonitoringCheckUseCase:
    return RunMonitoringCheckUseCase(watchlist_repo, snapshot_repo, alert_repo, provider)


def _to_schema(alert) -> AlertSchema:
    return AlertSchema(
        id=alert.id, user_id=alert.user_id, ticker=alert.ticker,
        alert_type=alert.alert_type.value, message=alert.message,
        change_pct=alert.change_pct, is_read=alert.is_read, created_at=alert.created_at,
    )


@router.get("", response_model=list[AlertSchema])
def get_alerts(
    unread_only: bool = Query(default=False),
    user_id: str = Depends(get_authenticated_user_id),
    use_case: GetAlertsUseCase = Depends(get_alerts_use_case),
) -> list[AlertSchema]:
    return [_to_schema(a) for a in use_case.execute(user_id, unread_only=unread_only)]


@router.post("/{alert_id}/read")
def mark_alert_read(
    alert_id: int,
    user_id: str = Depends(get_authenticated_user_id),
    use_case: MarkAlertReadUseCase = Depends(get_mark_read_use_case),
) -> dict[str, bool]:
    marked = use_case.execute(user_id, alert_id)
    if not marked:
        raise HTTPException(status_code=404, detail=f"No alert {alert_id} found for you")
    return {"marked_read": True}


@router.post("/check", response_model=list[AlertSchema])
def trigger_monitoring_check(
    user_id: str = Depends(get_authenticated_user_id),
    use_case: RunMonitoringCheckUseCase = Depends(get_monitoring_check_use_case),
) -> list[AlertSchema]:
    """Manual trigger for testing — see module docstring."""
    return [_to_schema(a) for a in use_case.execute(user_id)]
