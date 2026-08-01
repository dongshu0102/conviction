"""Use case: upcoming earnings announcements for a user's watchlist.

Fetches FMP's earnings calendar for a date range (every ticker, any
market) and filters down to the tickers actually on the user's
watchlist — same "fetch broad, filter narrow" shape as the factor
snapshot fetching a whole universe and callers filtering by theme.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.domain.entities.earnings import EarningsEvent
from src.domain.repositories.watchlist_repository import WatchlistRepository

logger = logging.getLogger(__name__)

DEFAULT_LOOKAHEAD_DAYS = 14


class EarningsCalendarUnavailableError(Exception):
    def __init__(self) -> None:
        super().__init__("This data provider does not support the earnings calendar.")


class GetUpcomingEarningsUseCase:
    def __init__(
        self,
        watchlist_repo: WatchlistRepository,
        data_provider: FinancialDataProvider,
    ) -> None:
        self._watchlist_repo = watchlist_repo
        self._data_provider = data_provider

    def execute(
        self,
        user_id: str,
        list_name: str | None = None,
        lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
    ) -> list[EarningsEvent]:
        if not hasattr(self._data_provider, "get_earnings_calendar"):
            raise EarningsCalendarUnavailableError()

        items = self._watchlist_repo.list_for_user(user_id, list_name)
        if not items:
            return []
        watchlist_tickers = {i.ticker for i in items}

        today = date.today()
        try:
            events = self._data_provider.get_earnings_calendar(
                today, today + timedelta(days=lookahead_days)
            )
        except (NotImplementedError, DataProviderError) as exc:
            logger.warning("Earnings calendar fetch failed: %s", exc)
            raise EarningsCalendarUnavailableError() from exc

        relevant = [e for e in events if e.ticker in watchlist_tickers]
        relevant.sort(key=lambda e: e.report_date)
        return relevant
