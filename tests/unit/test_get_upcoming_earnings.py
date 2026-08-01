"""Tests for GetUpcomingEarningsUseCase — watchlist filtering,
graceful degradation when the provider lacks earnings-calendar support,
and honest failure when the live call fails."""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.interfaces.data_provider import DataProviderError
from src.application.use_cases.get_upcoming_earnings import (
    EarningsCalendarUnavailableError,
    GetUpcomingEarningsUseCase,
)
from src.domain.entities.earnings import EarningsEvent
from src.domain.entities.watchlist import WatchlistItem
from tests.unit.fakes import FakeDataProvider, FakeWatchlistRepository

NOW = datetime.now(timezone.utc)


def _event(ticker: str, d: date) -> EarningsEvent:
    return EarningsEvent(ticker=ticker, report_date=d, eps_estimated=1.0,
                           eps_actual=None, revenue_estimated=None, revenue_actual=None)


class _EarningsProvider(FakeDataProvider):
    def __init__(self, *args, events=None, fail=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._events = events or []
        self._fail = fail

    def get_earnings_calendar(self, from_date, to_date):
        if self._fail:
            raise DataProviderError("earnings calendar down")
        return self._events


def test_filters_to_watchlist_tickers_only() -> None:
    watchlist_repo = FakeWatchlistRepository()
    watchlist_repo.add(WatchlistItem(user_id="alice", ticker="AAPL", added_at=NOW))
    watchlist_repo.add(WatchlistItem(user_id="alice", ticker="MSFT", added_at=NOW))

    provider = _EarningsProvider(company=None, events=[
        _event("AAPL", date(2026, 8, 10)),
        _event("GOOG", date(2026, 8, 11)),  # not on watchlist -> filtered out
        _event("MSFT", date(2026, 8, 9)),
    ])
    use_case = GetUpcomingEarningsUseCase(watchlist_repo, provider)

    result = use_case.execute("alice")

    assert [e.ticker for e in result] == ["MSFT", "AAPL"]  # sorted by date ascending


def test_empty_watchlist_returns_empty_without_calling_provider() -> None:
    watchlist_repo = FakeWatchlistRepository()
    provider = _EarningsProvider(company=None, events=[_event("AAPL", date(2026, 8, 10))])
    use_case = GetUpcomingEarningsUseCase(watchlist_repo, provider)

    assert use_case.execute("alice") == []


def test_provider_without_earnings_support_raises_clean_error() -> None:
    watchlist_repo = FakeWatchlistRepository()
    watchlist_repo.add(WatchlistItem(user_id="alice", ticker="AAPL", added_at=NOW))
    provider = FakeDataProvider(company=None)  # no get_earnings_calendar override at all

    use_case = GetUpcomingEarningsUseCase(watchlist_repo, provider)
    try:
        use_case.execute("alice")
        raise AssertionError("expected EarningsCalendarUnavailableError")
    except EarningsCalendarUnavailableError:
        pass


def test_provider_failure_raises_clean_error_not_crash() -> None:
    watchlist_repo = FakeWatchlistRepository()
    watchlist_repo.add(WatchlistItem(user_id="alice", ticker="AAPL", added_at=NOW))
    provider = _EarningsProvider(company=None, fail=True)

    use_case = GetUpcomingEarningsUseCase(watchlist_repo, provider)
    try:
        use_case.execute("alice")
        raise AssertionError("expected EarningsCalendarUnavailableError")
    except EarningsCalendarUnavailableError:
        pass
