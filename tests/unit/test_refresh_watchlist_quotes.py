from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.refresh_watchlist_quotes import RefreshWatchlistQuotesUseCase
from src.domain.entities.stock_candle import BulkQuote
from src.domain.entities.watchlist import WatchlistItem
from tests.unit.fakes import FakeStockDataProvider, FakeWatchlistRepository


def _item(user_id: str, ticker: str, **kwargs) -> WatchlistItem:
    return WatchlistItem(user_id=user_id, ticker=ticker, added_at=datetime.now(timezone.utc), **kwargs)


def test_empty_watchlist_returns_a_genuinely_empty_result() -> None:
    watchlist_repo = FakeWatchlistRepository()
    provider = FakeStockDataProvider()
    use_case = RefreshWatchlistQuotesUseCase(watchlist_repo, provider)

    result = use_case.execute("alice")

    assert result.items == []
    assert result.tickers_excluded == []


def test_refreshes_real_prices_and_computes_change_since_added() -> None:
    watchlist_repo = FakeWatchlistRepository()
    watchlist_repo.add(_item("alice", "AAPL", added_price=100.0))
    provider = FakeStockDataProvider(bulk_quotes=[
        BulkQuote(ticker="AAPL", price=110.0, as_of=datetime.now(timezone.utc)),
    ])
    use_case = RefreshWatchlistQuotesUseCase(watchlist_repo, provider)

    result = use_case.execute("alice")

    assert len(result.items) == 1
    item = result.items[0]
    assert item.current_price == 110.0
    assert round(item.change_since_added_pct, 4) == 0.10


def test_flags_target_reached_when_price_crosses_at_or_below_target() -> None:
    watchlist_repo = FakeWatchlistRepository()
    watchlist_repo.add(_item("alice", "AAPL", target_price=95.0))
    provider = FakeStockDataProvider(bulk_quotes=[
        BulkQuote(ticker="AAPL", price=94.0, as_of=datetime.now(timezone.utc)),
    ])
    use_case = RefreshWatchlistQuotesUseCase(watchlist_repo, provider)

    result = use_case.execute("alice")

    assert result.items[0].target_reached is True


def test_does_not_flag_target_reached_when_price_is_still_above_target() -> None:
    watchlist_repo = FakeWatchlistRepository()
    watchlist_repo.add(_item("alice", "AAPL", target_price=95.0))
    provider = FakeStockDataProvider(bulk_quotes=[
        BulkQuote(ticker="AAPL", price=96.0, as_of=datetime.now(timezone.utc)),
    ])
    use_case = RefreshWatchlistQuotesUseCase(watchlist_repo, provider)

    result = use_case.execute("alice")

    assert result.items[0].target_reached is False


def test_a_genuinely_missing_quote_is_honestly_excluded_not_given_a_stale_price() -> None:
    watchlist_repo = FakeWatchlistRepository()
    watchlist_repo.add(_item("alice", "AAPL"))
    watchlist_repo.add(_item("alice", "BADTICKER"))
    provider = FakeStockDataProvider(bulk_quotes=[
        BulkQuote(ticker="AAPL", price=100.0, as_of=datetime.now(timezone.utc)),
    ])
    use_case = RefreshWatchlistQuotesUseCase(watchlist_repo, provider)

    result = use_case.execute("alice")

    assert len(result.items) == 1
    assert result.items[0].ticker == "AAPL"
    assert result.tickers_excluded == ["BADTICKER"]


def test_a_genuinely_failed_bulk_call_honestly_excludes_every_ticker_rather_than_a_stale_price() -> None:
    watchlist_repo = FakeWatchlistRepository()
    watchlist_repo.add(_item("alice", "AAPL"))
    watchlist_repo.add(_item("alice", "MSFT"))
    provider = FakeStockDataProvider(raise_on_bulk=True)
    use_case = RefreshWatchlistQuotesUseCase(watchlist_repo, provider)

    result = use_case.execute("alice")

    assert result.items == []
    assert sorted(result.tickers_excluded) == ["AAPL", "MSFT"]
