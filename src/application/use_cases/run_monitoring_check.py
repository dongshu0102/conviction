"""Use case: run a monitoring check.

Compares each watchlisted ticker's current live price against its last
stored PriceSnapshot. A move beyond the threshold generates an Alert.
The very first check for a ticker has no prior snapshot to compare
against — it just establishes the baseline, generating no alert. This
is correct behavior, not a gap: there is no "change" to report before a
baseline exists.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.domain.entities.monitoring import Alert, AlertType, PriceSnapshot
from src.domain.repositories.monitoring_repository import (
    AlertRepository,
    PriceSnapshotRepository,
)
from src.domain.repositories.watchlist_repository import WatchlistRepository

logger = logging.getLogger(__name__)

DEFAULT_ALERT_THRESHOLD = 0.05  # 5% move since last check


class RunMonitoringCheckUseCase:
    def __init__(
        self,
        watchlist_repo: WatchlistRepository,
        snapshot_repo: PriceSnapshotRepository,
        alert_repo: AlertRepository,
        data_provider: FinancialDataProvider,
        threshold: float = DEFAULT_ALERT_THRESHOLD,
    ) -> None:
        self._watchlist_repo = watchlist_repo
        self._snapshot_repo = snapshot_repo
        self._alert_repo = alert_repo
        self._data_provider = data_provider
        self._threshold = threshold

    def execute(self, user_id: str) -> list[Alert]:
        watchlist = self._watchlist_repo.list_for_user(user_id)
        new_alerts: list[Alert] = []

        for item in watchlist:
            try:
                quote = self._data_provider.get_quote(item.ticker)
            except DataProviderError:
                logger.warning("Monitoring: quote fetch failed for %s, skipping", item.ticker)
                continue

            prior = self._snapshot_repo.get_latest(item.ticker)
            now = datetime.now(timezone.utc)

            if prior is not None and prior.price > 0:
                change_pct = (quote.price - prior.price) / prior.price
                if abs(change_pct) >= self._threshold:
                    direction = "up" if change_pct > 0 else "down"
                    alert = Alert(
                        user_id=user_id,
                        ticker=item.ticker,
                        alert_type=AlertType.PRICE_MOVE,
                        message=(
                            f"{item.ticker} moved {direction} "
                            f"{abs(change_pct) * 100:.1f}% since last check "
                            f"(${prior.price:.2f} -> ${quote.price:.2f})"
                        ),
                        created_at=now,
                        change_pct=change_pct,
                    )
                    saved = self._alert_repo.save(alert)
                    new_alerts.append(saved)

            self._snapshot_repo.save(
                PriceSnapshot(ticker=item.ticker, price=quote.price, captured_at=now)
            )

        return new_alerts
