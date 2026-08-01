"""Watchlist use cases.

AddToWatchlistUseCase deliberately validates the company exists in our
system (has been ingested) before allowing it onto a watchlist. Without
this check, a user could watchlist a typo'd or never-ingested ticker and
every subsequent read (valuation, analysis, research) would silently
fail — better to reject at the point of adding, with a clear error, than
let a broken watchlist entry surface as confusing failures later.

Add-time baselines (added_price, added_pe) are captured BEST EFFORT:
a failure to fetch a quote or compute a P/E must never block adding a
ticker to a watchlist — the baseline is an enhancement, not a
requirement. Missing baselines stay None, which the triage scorer
already treats honestly (signal absent, not zero). The provider
dependencies default to None so every existing wiring site keeps
working unchanged; wiring them in is opt-in per call site.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone

from src.domain.entities.watchlist import WatchlistItem
from src.domain.repositories.company_repository import CompanyRepository
from src.domain.repositories.watchlist_repository import WatchlistRepository

logger = logging.getLogger(__name__)


class TickerNotIngestedError(Exception):
    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(
            f"'{ticker}' has not been ingested yet — ingest it first via "
            f"POST /companies/{ticker}/ingest before adding to a watchlist."
        )


class WatchlistItemNotFoundError(Exception):
    def __init__(self, ticker: str, list_name: str) -> None:
        super().__init__(f"'{ticker}' is not on watchlist '{list_name}'.")


class AddToWatchlistUseCase:
    def __init__(
        self,
        watchlist_repo: WatchlistRepository,
        company_repo: CompanyRepository,
        data_provider=None,  # optional FinancialDataProvider for added_price baseline
        valuation_use_case=None,  # optional ComputeValuationUseCase for added_pe baseline
    ) -> None:
        self._watchlist_repo = watchlist_repo
        self._company_repo = company_repo
        self._data_provider = data_provider
        self._valuation_use_case = valuation_use_case

    def execute(
        self,
        user_id: str,
        ticker: str,
        notes: str | None = None,
        list_name: str = "Default",
        target_price: float | None = None,
        alert_threshold_pct: float | None = None,
    ) -> WatchlistItem:
        ticker = ticker.strip().upper()
        if self._company_repo.get_by_ticker(ticker) is None:
            raise TickerNotIngestedError(ticker)

        added_price = self._capture_price(ticker)
        added_pe = self._capture_pe(ticker)

        item = WatchlistItem(
            user_id=user_id,
            ticker=ticker,
            added_at=datetime.now(timezone.utc),
            notes=notes,
            list_name=list_name,
            target_price=target_price,
            alert_threshold_pct=alert_threshold_pct,
            added_price=added_price,
            added_pe=added_pe,
        )
        self._watchlist_repo.add(item)
        return item

    def _capture_price(self, ticker: str) -> float | None:
        if self._data_provider is None:
            return None
        try:
            return self._data_provider.get_quote(ticker).price
        except Exception as exc:  # best effort by design — see module docstring
            logger.warning("Add-time price baseline failed for %s: %s", ticker, exc)
            return None

    def _capture_pe(self, ticker: str) -> float | None:
        if self._valuation_use_case is None:
            return None
        try:
            return self._valuation_use_case.execute(ticker).price_to_earnings
        except Exception as exc:  # best effort by design — see module docstring
            logger.warning("Add-time P/E baseline failed for %s: %s", ticker, exc)
            return None


class UpdateWatchlistItemUseCase:
    """Update individual fields of an existing item without clobbering
    the others — critically, the add-time baselines and added_at are
    preserved, which a naive re-add would silently destroy."""

    def __init__(self, watchlist_repo: WatchlistRepository) -> None:
        self._watchlist_repo = watchlist_repo

    _UNSET = object()

    def execute(
        self,
        user_id: str,
        ticker: str,
        list_name: str = "Default",
        notes=_UNSET,
        target_price=_UNSET,
        alert_threshold_pct=_UNSET,
    ) -> WatchlistItem:
        ticker = ticker.strip().upper()
        existing = self._watchlist_repo.get(user_id, ticker, list_name)
        if existing is None:
            raise WatchlistItemNotFoundError(ticker, list_name)

        changes = {}
        if notes is not self._UNSET:
            changes["notes"] = notes
        if target_price is not self._UNSET:
            changes["target_price"] = target_price
        if alert_threshold_pct is not self._UNSET:
            changes["alert_threshold_pct"] = alert_threshold_pct

        updated = replace(existing, **changes) if changes else existing
        self._watchlist_repo.add(updated)
        return updated


class RemoveFromWatchlistUseCase:
    def __init__(self, watchlist_repo: WatchlistRepository) -> None:
        self._watchlist_repo = watchlist_repo

    def execute(self, user_id: str, ticker: str, list_name: str | None = None) -> bool:
        return self._watchlist_repo.remove(user_id, ticker.strip().upper(), list_name)


class GetWatchlistUseCase:
    def __init__(self, watchlist_repo: WatchlistRepository) -> None:
        self._watchlist_repo = watchlist_repo

    def execute(self, user_id: str, list_name: str | None = None) -> list[WatchlistItem]:
        return self._watchlist_repo.list_for_user(user_id, list_name)


class ListWatchlistNamesUseCase:
    """Distinct list names for a user, with item counts — derived from
    the items themselves since named lists are a label, not a table."""

    def __init__(self, watchlist_repo: WatchlistRepository) -> None:
        self._watchlist_repo = watchlist_repo

    def execute(self, user_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self._watchlist_repo.list_for_user(user_id):
            counts[item.list_name] = counts.get(item.list_name, 0) + 1
        return counts
