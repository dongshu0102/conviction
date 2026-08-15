"""Use case: resolve real tickers for every distinct CUSIP across the
whole institutional_holdings table that hasn't been resolved yet.

Filters to genuinely unresolved CUSIPs first via a single, bulk
get_unresolved() call, rather than calling ResolveCusipTickerUseCase
for all ~37,000 distinct CUSIPs on every run (which would still skip
the real FMP call for already-cached ones, but would mean tens of
thousands of unnecessary individual cache-lookup queries every time
this script is re-run to pick up newly-ingested securities).

A single CUSIP's resolution failing (a real, transient network error,
not just "no US ticker exists," which is itself a valid, cached
non-error outcome -- see resolve_cusip_ticker's own docstring) must
never abort the whole backfill; it's logged and skipped, and the next
run will simply retry it, since it was never actually cached as
resolved.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from src.application.use_cases.resolve_cusip_ticker import ResolveCusipTickerUseCase
from src.domain.repositories.cusip_ticker_map_repository import CusipTickerMapRepository
from src.domain.repositories.institutional_holding_repository import (
    InstitutionalHoldingRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BackfillCusipTickersResult:
    total_distinct_cusips: int
    already_resolved: int
    newly_attempted: int
    newly_resolved_to_a_ticker: int
    newly_resolved_to_no_ticker: int
    errors: int


class BackfillCusipTickersUseCase:
    def __init__(
        self,
        holding_repository: InstitutionalHoldingRepository,
        ticker_map_repository: CusipTickerMapRepository,
        ticker_resolver: ResolveCusipTickerUseCase,
    ) -> None:
        self._holding_repository = holding_repository
        self._ticker_map_repository = ticker_map_repository
        self._ticker_resolver = ticker_resolver

    def execute(
        self, on_progress: Callable[[int, int], None] | None = None, limit: int | None = None,
    ) -> BackfillCusipTickersResult:
        all_cusips = self._holding_repository.get_all_distinct_cusips()
        unresolved = self._ticker_map_repository.get_unresolved(all_cusips)
        already_resolved = len(all_cusips) - len(unresolved)
        if limit is not None:
            unresolved = unresolved[:limit]

        resolved_to_ticker = 0
        resolved_to_none = 0
        errors = 0

        for i, cusip in enumerate(unresolved):
            try:
                mapping = self._ticker_resolver.execute(cusip)
                if mapping.ticker is not None:
                    resolved_to_ticker += 1
                else:
                    resolved_to_none += 1
            except Exception:
                errors += 1
                logger.warning("Skipping cusip %s after a resolution error", cusip, exc_info=True)

            if on_progress is not None:
                on_progress(i + 1, len(unresolved))

        return BackfillCusipTickersResult(
            total_distinct_cusips=len(all_cusips),
            already_resolved=already_resolved,
            newly_attempted=len(unresolved),
            newly_resolved_to_a_ticker=resolved_to_ticker,
            newly_resolved_to_no_ticker=resolved_to_none,
            errors=errors,
        )
