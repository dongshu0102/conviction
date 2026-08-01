"""Use case: latest news for watchlist tickers (or any explicit tickers).

Per-ticker failures degrade to an empty article list for that ticker
plus an entry in tickers_failed — one dead ticker never blanks the
whole news feed. Providers without news support (NotImplementedError)
surface as a clean "unavailable" result, not a crash.
"""
from __future__ import annotations

import logging

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.domain.entities.news import NewsArticle
from src.domain.repositories.watchlist_repository import WatchlistRepository

logger = logging.getLogger(__name__)

DEFAULT_LIMIT_PER_TICKER = 5


class GetWatchlistNewsUseCase:
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
        tickers: list[str] | None = None,
        limit_per_ticker: int = DEFAULT_LIMIT_PER_TICKER,
    ) -> tuple[dict[str, list[NewsArticle]], list[str]]:
        """tickers, if given, overrides the watchlist lookup (lets the
        chat tool ask about any single ticker). Returns
        (articles_by_ticker, tickers_failed)."""
        if tickers is None:
            items = self._watchlist_repo.list_for_user(user_id, list_name)
            # dedupe while preserving order — same ticker on two lists
            # should not fetch news twice
            seen: set[str] = set()
            tickers = [i.ticker for i in items if not (i.ticker in seen or seen.add(i.ticker))]

        by_ticker: dict[str, list[NewsArticle]] = {}
        failed: list[str] = []
        for ticker in tickers:
            ticker = ticker.strip().upper()
            try:
                by_ticker[ticker] = self._data_provider.get_stock_news(
                    ticker, limit=limit_per_ticker
                )
            except (DataProviderError, NotImplementedError) as exc:
                logger.warning("News fetch failed for %s: %s", ticker, exc)
                failed.append(ticker)
        return by_ticker, failed
