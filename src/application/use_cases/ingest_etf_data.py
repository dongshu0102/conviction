"""Use case: ingest an ETF's profile into CompanyRepository.

Deliberately does NOT touch the financial statement repositories at
all — an ETF has no income statement, balance sheet, or cash flow
statement to ingest, by construction (it holds other companies' shares
instead of running an operation). Every downstream consumer
(valuation, factor scoring, screening) already treats a ticker with
zero ingested statements as honestly-partial data, not a hard failure
— this use case relies on that existing behavior rather than
special-casing ETFs throughout the codebase.
"""
from __future__ import annotations

import logging

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.domain.entities.company import AssetType, Company, Sector
from src.domain.repositories.company_repository import CompanyRepository

logger = logging.getLogger(__name__)


class EtfNotFoundError(Exception):
    def __init__(self, ticker: str) -> None:
        super().__init__(f"'{ticker}' was not found as a recognized ETF.")


class EtfLookupUnavailableError(Exception):
    def __init__(self) -> None:
        super().__init__("This data provider does not support ETF lookups.")


class IngestEtfDataUseCase:
    def __init__(
        self,
        company_repo: CompanyRepository,
        data_provider: FinancialDataProvider,
    ) -> None:
        self._company_repo = company_repo
        self._data_provider = data_provider

    def execute(self, ticker: str) -> Company:
        ticker = ticker.strip().upper()
        if not hasattr(self._data_provider, "get_etf_profile"):
            raise EtfLookupUnavailableError()

        try:
            profile = self._data_provider.get_etf_profile(ticker)
        except (NotImplementedError, DataProviderError) as exc:
            logger.warning("ETF profile fetch failed for %s: %s", ticker, exc)
            raise EtfLookupUnavailableError() from exc

        if profile is None:
            raise EtfNotFoundError(ticker)

        company = Company(
            ticker=ticker,
            name=profile.name,
            sector=Sector.ETF,
            industry=profile.asset_class or "ETF",
            exchange="",
            country=profile.domicile or "",
            description=profile.description,
            asset_type=AssetType.ETF,
            expense_ratio=profile.expense_ratio,
            aum=profile.aum,
        )
        self._company_repo.save(company)
        logger.info("Ingested ETF %s (%s)", ticker, profile.name)
        return company
