"""Use case: resolve one CUSIP to its real ticker, checking the cache
first so a given CUSIP is only ever sent to FMP once (there are far
fewer distinct CUSIPs than institutional_holdings rows).
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.interfaces.data_provider import FinancialDataProvider
from src.domain.entities.cusip_ticker_mapping import CusipTickerMapping
from src.domain.repositories.cusip_ticker_map_repository import (
    CusipTickerMapRepository,
)
from src.domain.services.cusip_ticker_resolution import pick_primary_us_ticker


class ResolveCusipTickerUseCase:
    def __init__(
        self,
        repository: CusipTickerMapRepository,
        provider: FinancialDataProvider,
    ) -> None:
        self._repository = repository
        self._provider = provider

    def execute(self, cusip: str, force: bool = False) -> CusipTickerMapping:
        if not force:
            existing = self._repository.get(cusip)
            if existing is not None:
                return existing

        results = self._provider.search_cusip(cusip)
        ticker = pick_primary_us_ticker(results)
        company_name = results[0].company_name if results else None

        mapping = CusipTickerMapping(
            cusip=cusip, ticker=ticker, company_name=company_name,
            resolved_at=datetime.now(timezone.utc),
        )
        self._repository.save(mapping)
        return mapping
