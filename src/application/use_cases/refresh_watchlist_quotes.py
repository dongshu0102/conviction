"""Use case: cheaply refresh real, current prices across a whole
watchlist in a single bulk call, rather than one call per ticker.

Genuinely distinct from TriageWatchlistUseCase (which computes a
richer, weighted urgency score via one FMP quote call per ticker) --
this is the simpler "monitor a shortlist" need described directly:
MarketData.app's bulk quotes endpoint lets a whole list's prices be
refreshed cheaply in one request.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.interfaces.stock_data_provider import (
    StockDataProvider,
    StockDataProviderError,
)
from src.domain.entities.watchlist_quote_refresh import (
    WatchlistQuoteRefreshItem,
    WatchlistQuoteRefreshResult,
)
from src.domain.repositories.watchlist_repository import WatchlistRepository


class RefreshWatchlistQuotesUseCase:
    def __init__(
        self, watchlist_repo: WatchlistRepository, stock_provider: StockDataProvider,
    ) -> None:
        self._watchlist_repo = watchlist_repo
        self._stock_provider = stock_provider

    def execute(self, user_id: str, list_name: str | None = None) -> WatchlistQuoteRefreshResult:
        watchlist_items = self._watchlist_repo.list_for_user(user_id, list_name)
        if not watchlist_items:
            return WatchlistQuoteRefreshResult(
                user_id=user_id, as_of=datetime.now(timezone.utc), items=[], tickers_excluded=[],
            )

        tickers = [item.ticker for item in watchlist_items]
        try:
            quotes = self._stock_provider.get_bulk_quotes(tickers)
        except StockDataProviderError:
            # The whole bulk call failed -- every ticker is honestly
            # excluded, never given a stale or fabricated price.
            return WatchlistQuoteRefreshResult(
                user_id=user_id, as_of=datetime.now(timezone.utc), items=[], tickers_excluded=tickers,
            )

        price_by_ticker = {q.ticker: q.price for q in quotes}
        results: list[WatchlistQuoteRefreshItem] = []
        excluded: list[str] = []

        for item in watchlist_items:
            current_price = price_by_ticker.get(item.ticker)
            if current_price is None:
                excluded.append(item.ticker)
                continue

            change_pct = (
                (current_price - item.added_price) / item.added_price
                if item.added_price is not None and item.added_price > 0
                else None
            )
            target_reached = (
                item.target_price is not None and current_price <= item.target_price
            )
            results.append(WatchlistQuoteRefreshItem(
                ticker=item.ticker, list_name=item.list_name, current_price=current_price,
                added_price=item.added_price, change_since_added_pct=change_pct,
                target_price=item.target_price, target_reached=target_reached,
            ))

        return WatchlistQuoteRefreshResult(
            user_id=user_id, as_of=datetime.now(timezone.utc), items=results, tickers_excluded=excluded,
        )
