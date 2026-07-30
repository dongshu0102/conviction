"""Use case: read a company's stored profile and financial statements.

Kept separate from ingestion (CQRS-lite): reads have different failure
modes and performance needs than writes, and every future agent that
"looks up a company" will call this same use case rather than duplicating
query logic against the repositories.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.domain.entities.company import Company
from src.domain.entities.financial_statement import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
    Period,
)
from src.domain.repositories.company_repository import CompanyRepository
from src.domain.repositories.financial_statement_repository import (
    FinancialStatementRepository,
)


class CompanyNotFoundError(Exception):
    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(f"No company found for ticker '{ticker}'")


@dataclass(frozen=True, slots=True)
class CompanyFinancials:
    company: Company
    income_statements: list[IncomeStatement]
    balance_sheets: list[BalanceSheet]
    cash_flow_statements: list[CashFlowStatement]


class GetCompanyFinancialsUseCase:
    def __init__(
        self,
        company_repository: CompanyRepository,
        statement_repository: FinancialStatementRepository,
    ) -> None:
        self._company_repo = company_repository
        self._statement_repo = statement_repository

    def execute(
        self, ticker: str, period: Period = Period.ANNUAL, years: int = 5
    ) -> CompanyFinancials:
        ticker = ticker.strip().upper()
        company = self._company_repo.get_by_ticker(ticker)
        if company is None:
            raise CompanyNotFoundError(ticker)

        return CompanyFinancials(
            company=company,
            income_statements=self._statement_repo.get_income_statements(
                ticker, period=period, limit=years
            ),
            balance_sheets=self._statement_repo.get_balance_sheets(
                ticker, period=period, limit=years
            ),
            cash_flow_statements=self._statement_repo.get_cash_flow_statements(
                ticker, period=period, limit=years
            ),
        )
