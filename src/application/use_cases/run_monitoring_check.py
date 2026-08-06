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
from datetime import datetime, timedelta, timezone

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
EARNINGS_ALERT_WINDOW_DAYS = 3  # alert when earnings is within this many days out


def _as_utc(dt: datetime) -> datetime:
    """Alerts loaded back from the database can come back timezone-naive
    depending on the column type/driver, while freshly-computed cutoffs
    use timezone-aware UTC — comparing the two directly raises
    TypeError. Every created_at in this codebase is written in UTC, so
    a naive value is safely assumed to already be UTC, not local time."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


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

        # The same ticker can be on multiple named lists. Group by
        # ticker: fetch the quote once, read the prior snapshot once
        # (BEFORE saving the new one — otherwise the first item's save
        # would pollute the comparison baseline for later items), then
        # evaluate every item's own threshold/target against that same
        # prior, and save the new snapshot once at the end.
        by_ticker: dict[str, list] = {}
        for item in watchlist:
            by_ticker.setdefault(item.ticker, []).append(item)

        for ticker, items in by_ticker.items():
            try:
                quote = self._data_provider.get_quote(ticker)
            except DataProviderError:
                logger.warning("Monitoring: quote fetch failed for %s, skipping", ticker)
                continue

            prior = self._snapshot_repo.get_latest(ticker)
            now = datetime.now(timezone.utc)

            if prior is not None and prior.price > 0:
                change_pct = (quote.price - prior.price) / prior.price

                for item in items:
                    # Per-item override falls back to the global default —
                    # the IBKR-style "custom alert threshold per ticker".
                    threshold = (
                        item.alert_threshold_pct
                        if item.alert_threshold_pct is not None
                        else self._threshold
                    )
                    if abs(change_pct) >= threshold:
                        direction = "up" if change_pct > 0 else "down"
                        alert = Alert(
                            user_id=user_id,
                            ticker=ticker,
                            alert_type=AlertType.PRICE_MOVE,
                            message=(
                                f"{ticker} moved {direction} "
                                f"{abs(change_pct) * 100:.1f}% since last check "
                                f"(${prior.price:.2f} -> ${quote.price:.2f})"
                            ),
                            created_at=now,
                            change_pct=change_pct,
                        )
                        saved = self._alert_repo.save(alert)
                        new_alerts.append(saved)

                    # Entry-target alert: fires ONCE, on the crossing —
                    # prior price was above the target and current price
                    # is at or below it. Checks that stay below the
                    # target afterward don't re-alert every run. With no
                    # prior snapshot there is no crossing to detect
                    # (same baseline-establishment principle as moves).
                    if (
                        item.target_price is not None
                        and prior.price > item.target_price
                        and quote.price <= item.target_price
                    ):
                        target_alert = Alert(
                            user_id=user_id,
                            ticker=ticker,
                            alert_type=AlertType.TARGET_REACHED,
                            message=(
                                f"{ticker} reached your entry target of "
                                f"${item.target_price:.2f} "
                                f"(${prior.price:.2f} -> ${quote.price:.2f}) "
                                f"on list '{item.list_name}'"
                            ),
                            created_at=now,
                            change_pct=change_pct,
                        )
                        saved = self._alert_repo.save(target_alert)
                        new_alerts.append(saved)

            self._snapshot_repo.save(
                PriceSnapshot(ticker=ticker, price=quote.price, captured_at=now)
            )

        new_alerts.extend(self._check_upcoming_earnings(user_id, watchlist))
        return new_alerts

    def _check_upcoming_earnings(self, user_id: str, watchlist: list) -> list[Alert]:
        """Fires an EARNINGS_UPCOMING alert once per ticker within
        EARNINGS_ALERT_WINDOW_DAYS of its report date. Deduped against
        EXISTING alerts (not a stored "already alerted" flag) so this
        stays correct even across restarts — a cron running every 15
        minutes would otherwise re-alert on the same earnings date
        dozens of times a day without this check. Silently does
        nothing if the data provider lacks earnings-calendar support,
        since this is an additive capability, not a required one."""
        if not hasattr(self._data_provider, "get_earnings_calendar"):
            return []

        tickers = {item.ticker for item in watchlist}
        if not tickers:
            return []

        today = datetime.now(timezone.utc).date()
        try:
            events = self._data_provider.get_earnings_calendar(
                today, today + timedelta(days=EARNINGS_ALERT_WINDOW_DAYS)
            )
        except (NotImplementedError, DataProviderError) as exc:
            logger.warning("Monitoring: earnings calendar unavailable: %s", exc)
            return []

        relevant = [
            e for e in events
            if e.ticker in tickers and today <= e.report_date <= today + timedelta(days=EARNINGS_ALERT_WINDOW_DAYS)
        ]
        if not relevant:
            return []

        existing_alerts = self._alert_repo.list_for_user(user_id)
        recency_cutoff = datetime.now(timezone.utc) - timedelta(days=EARNINGS_ALERT_WINDOW_DAYS)
        already_alerted_tickers = {
            a.ticker for a in existing_alerts
            if a.alert_type == AlertType.EARNINGS_UPCOMING
            and _as_utc(a.created_at) >= recency_cutoff
        }

        fired: list[Alert] = []
        for event in relevant:
            if event.ticker in already_alerted_tickers:
                continue
            alert = Alert(
                user_id=user_id,
                ticker=event.ticker,
                alert_type=AlertType.EARNINGS_UPCOMING,
                message=(
                    f"{event.ticker} reports earnings on "
                    f"{event.report_date.isoformat()}"
                    + (
                        f" (est. EPS ${event.eps_estimated:.2f})"
                        if event.eps_estimated is not None
                        else ""
                    )
                ),
                created_at=datetime.now(timezone.utc),
                change_pct=None,
            )
            fired.append(self._alert_repo.save(alert))
            already_alerted_tickers.add(event.ticker)  # don't double-fire within this same run

        return fired
