"""Watchlist use cases.

AddToWatchlistUseCase deliberately validates the company exists in our
system (has been ingested) before allowing it onto a watchlist. Without
this check, a user could watchlist a typo'd or never-ingested ticker and
every subsequent read (valuation, analysis, research) would silently
fail — better to reject at the point of adding, with a clear error, than
let a broken watchlist entry surface as confusing failures later.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.domain.entities.watchlist import WatchlistItem
from src.domain.repositories.company_repository import CompanyRepository
from src.domain.repositories.watchlist_repository import WatchlistRepository


class TickerNotIngestedError(Exception):
    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(
            f"'{ticker}' has not been ingested yet — ingest it first via "
            f"POST /companies/{ticker}/ingest before adding to a watchlist."
        )


class AddToWatchlistUseCase:
    def __init__(
        self, watchlist_repo: WatchlistRepository, company_repo: CompanyRepository
    ) -> None:
        self._watchlist_repo = watchlist_repo
        self._company_repo = company_repo

    def execute(self, user_id: str, ticker: str, notes: str | None = None) -> WatchlistItem:
        ticker = ticker.strip().upper()
        if self._company_repo.get_by_ticker(ticker) is None:
            raise TickerNotIngestedError(ticker)

        item = WatchlistItem(
            user_id=user_id, ticker=ticker, added_at=datetime.now(timezone.utc), notes=notes
        )
        self._watchlist_repo.add(item)
        return item


class RemoveFromWatchlistUseCase:
    def __init__(self, watchlist_repo: WatchlistRepository) -> None:
        self._watchlist_repo = watchlist_repo

    def execute(self, user_id: str, ticker: str) -> bool:
        return self._watchlist_repo.remove(user_id, ticker.strip().upper())


class GetWatchlistUseCase:
    def __init__(self, watchlist_repo: WatchlistRepository) -> None:
        self._watchlist_repo = watchlist_repo

    def execute(self, user_id: str) -> list[WatchlistItem]:
        return self._watchlist_repo.list_for_user(user_id)
