"""Persistence contract for financial statement entities."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.financial_statement import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
    Period,
)


class FinancialStatementRepository(ABC):
    @abstractmethod
    def save_income_statement(self, statement: IncomeStatement) -> None:
        """Upsert by (ticker, fiscal_year, fiscal_quarter, period)."""

    @abstractmethod
    def save_balance_sheet(self, statement: BalanceSheet) -> None: ...

    @abstractmethod
    def save_cash_flow_statement(self, statement: CashFlowStatement) -> None: ...

    @abstractmethod
    def get_income_statements(
        self, ticker: str, period: Period = Period.ANNUAL, limit: int = 5
    ) -> list[IncomeStatement]:
        """Most recent `limit` periods, newest first."""

    @abstractmethod
    def get_balance_sheets(
        self, ticker: str, period: Period = Period.ANNUAL, limit: int = 5
    ) -> list[BalanceSheet]: ...

    @abstractmethod
    def get_cash_flow_statements(
        self, ticker: str, period: Period = Period.ANNUAL, limit: int = 5
    ) -> list[CashFlowStatement]: ...
