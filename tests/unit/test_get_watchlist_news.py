from __future__ import annotations

from datetime import datetime, timezone

from src.application.interfaces.data_provider import DataProviderError
from src.application.use_cases.get_watchlist_news import GetWatchlistNewsUseCase
from src.domain.entities.news import NewsArticle
from src.domain.entities.watchlist import WatchlistItem
from tests.unit.fakes import FakeWatchlistRepository

NOW = datetime.now(timezone.utc)


class _NewsProvider:
    def __init__(self, news_by_ticker, failing=None):
        self._news = news_by_ticker
        self._failing = failing or set()

    def get_stock_news(self, ticker: str, limit: int = 10):
        if ticker in self._failing:
            raise DataProviderError("news down")
        return self._news.get(ticker, [])[:limit]


def _article(ticker: str, title: str) -> NewsArticle:
    return NewsArticle(ticker=ticker, title=title, published_at=NOW, source="T", url=None, snippet=None)


def test_watchlist_news_dedupes_ticker_across_lists_and_reports_failures() -> None:
    repo = FakeWatchlistRepository()
    repo.add(WatchlistItem(user_id="alice", ticker="NVDA", added_at=NOW, list_name="A"))
    repo.add(WatchlistItem(user_id="alice", ticker="NVDA", added_at=NOW, list_name="B"))
    repo.add(WatchlistItem(user_id="alice", ticker="DEAD", added_at=NOW))

    provider = _NewsProvider({"NVDA": [_article("NVDA", "chip news")]}, failing={"DEAD"})
    by_ticker, failed = GetWatchlistNewsUseCase(repo, provider).execute("alice")

    assert list(by_ticker.keys()) == ["NVDA"]  # deduped: fetched once despite two lists
    assert by_ticker["NVDA"][0].title == "chip news"
    assert failed == ["DEAD"]


def test_explicit_ticker_overrides_watchlist() -> None:
    provider = _NewsProvider({"TSLA": [_article("TSLA", "auto news")]})
    by_ticker, failed = GetWatchlistNewsUseCase(FakeWatchlistRepository(), provider).execute(
        "alice", tickers=["tsla"]
    )
    assert by_ticker["TSLA"][0].title == "auto news"
    assert failed == []


def test_provider_without_news_support_degrades_to_failed_not_crash() -> None:
    class _NoNews:
        def get_stock_news(self, ticker, limit=10):
            raise NotImplementedError("unsupported")

    repo = FakeWatchlistRepository()
    repo.add(WatchlistItem(user_id="alice", ticker="NVDA", added_at=NOW))
    by_ticker, failed = GetWatchlistNewsUseCase(repo, _NoNews()).execute("alice")
    assert by_ticker == {} and failed == ["NVDA"]
