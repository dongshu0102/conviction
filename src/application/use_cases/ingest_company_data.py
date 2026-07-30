"""Use case: ingest a single company's profile and financial statements
from an external data provider into our persistence layer.

This is deliberately plain, deterministic, and LLM-free. Ingestion is a
data-engineering problem, not an AI problem — and it needs to be, because
every agent we build later reasons over what lands here. An AI agent
reasoning over unreliable or missing data produces confident-sounding
hallucination, which is the worst possible failure mode for a financial
product. Get this boring and correct first.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.domain.entities.financial_statement import Period
from src.domain.repositories.company_repository import CompanyRepository
from src.domain.repositories.financial_statement_repository import (
    FinancialStatementRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IngestCompanyDataResult:
    ticker: str
    income_statements_ingested: int
    balance_sheets_ingested: int
    cash_flow_statements_ingested: int


class IngestCompanyDataUseCase:
    def __init__(
        self,
        data_provider: FinancialDataProvider,
        company_repository: CompanyRepository,
        statement_repository: FinancialStatementRepository,
    ) -> None:
        self._data_provider = data_provider
        self._company_repo = company_repository
        self._statement_repo = statement_repository

    def execute(self, ticker: str, years: int = 5) -> IngestCompanyDataResult:
        ticker = ticker.strip().upper()
        logger.info("Ingesting company data for %s", ticker)

        try:
            profile = self._data_provider.get_company_profile(ticker)
            self._company_repo.save(profile)

            income_statements = self._data_provider.get_income_statements(
                ticker, period=Period.ANNUAL, limit=years
            )
            balance_sheets = self._data_provider.get_balance_sheets(
                ticker, period=Period.ANNUAL, limit=years
            )
            cash_flows = self._data_provider.get_cash_flow_statements(
                ticker, period=Period.ANNUAL, limit=years
            )
        except DataProviderError:
            logger.exception("Data provider failed while ingesting %s", ticker)
            raise

        for stmt in income_statements:
            self._statement_repo.save_income_statement(stmt)
        for stmt in balance_sheets:
            self._statement_repo.save_balance_sheet(stmt)
        for stmt in cash_flows:
            self._statement_repo.save_cash_flow_statement(stmt)

        result = IngestCompanyDataResult(
            ticker=ticker,
            income_statements_ingested=len(income_statements),
            balance_sheets_ingested=len(balance_sheets),
            cash_flow_statements_ingested=len(cash_flows),
        )
        logger.info("Ingestion complete: %s", result)
        return result
