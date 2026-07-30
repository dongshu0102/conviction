from __future__ import annotations

from sqlalchemy import select

from src.domain.entities.financial_statement import (
    BalanceSheet,
    CashFlowStatement,
    FiscalPeriodKey,
    IncomeStatement,
    Period,
)
from src.domain.repositories.financial_statement_repository import (
    FinancialStatementRepository,
)
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import (
    BalanceSheetModel,
    CashFlowStatementModel,
    IncomeStatementModel,
)


def _income_to_domain(row: IncomeStatementModel) -> IncomeStatement:
    return IncomeStatement(
        key=FiscalPeriodKey(row.ticker, row.fiscal_year, Period(row.period), row.fiscal_quarter),
        fiscal_date_ending=row.fiscal_date_ending,
        reported_currency=row.reported_currency,
        revenue=row.revenue,
        cost_of_revenue=row.cost_of_revenue,
        gross_profit=row.gross_profit,
        operating_expenses=row.operating_expenses,
        operating_income=row.operating_income,
        net_income=row.net_income,
        eps_basic=row.eps_basic,
        eps_diluted=row.eps_diluted,
        ebitda=row.ebitda,
        raw=row.raw or {},
    )


def _balance_to_domain(row: BalanceSheetModel) -> BalanceSheet:
    return BalanceSheet(
        key=FiscalPeriodKey(row.ticker, row.fiscal_year, Period(row.period), row.fiscal_quarter),
        fiscal_date_ending=row.fiscal_date_ending,
        reported_currency=row.reported_currency,
        total_assets=row.total_assets,
        total_current_assets=row.total_current_assets,
        cash_and_equivalents=row.cash_and_equivalents,
        total_liabilities=row.total_liabilities,
        total_current_liabilities=row.total_current_liabilities,
        total_debt=row.total_debt,
        total_equity=row.total_equity,
        shares_outstanding=row.shares_outstanding,
        raw=row.raw or {},
    )


def _cash_flow_to_domain(row: CashFlowStatementModel) -> CashFlowStatement:
    return CashFlowStatement(
        key=FiscalPeriodKey(row.ticker, row.fiscal_year, Period(row.period), row.fiscal_quarter),
        fiscal_date_ending=row.fiscal_date_ending,
        reported_currency=row.reported_currency,
        operating_cash_flow=row.operating_cash_flow,
        capital_expenditures=row.capital_expenditures,
        free_cash_flow=row.free_cash_flow,
        dividends_paid=row.dividends_paid,
        net_change_in_cash=row.net_change_in_cash,
        raw=row.raw or {},
    )


class SqlAlchemyFinancialStatementRepository(FinancialStatementRepository):
    def save_income_statement(self, statement: IncomeStatement) -> None:
        with session_scope() as session:
            existing = session.execute(
                select(IncomeStatementModel).where(
                    IncomeStatementModel.ticker == statement.key.ticker,
                    IncomeStatementModel.fiscal_year == statement.key.fiscal_year,
                    IncomeStatementModel.fiscal_quarter == statement.key.fiscal_quarter,
                    IncomeStatementModel.period == statement.key.period.value,
                )
            ).scalar_one_or_none()

            fields = dict(
                fiscal_date_ending=statement.fiscal_date_ending,
                reported_currency=statement.reported_currency,
                revenue=statement.revenue,
                cost_of_revenue=statement.cost_of_revenue,
                gross_profit=statement.gross_profit,
                operating_expenses=statement.operating_expenses,
                operating_income=statement.operating_income,
                net_income=statement.net_income,
                eps_basic=statement.eps_basic,
                eps_diluted=statement.eps_diluted,
                ebitda=statement.ebitda,
                raw=statement.raw,
            )
            if existing is None:
                session.add(
                    IncomeStatementModel(
                        ticker=statement.key.ticker,
                        fiscal_year=statement.key.fiscal_year,
                        fiscal_quarter=statement.key.fiscal_quarter,
                        period=statement.key.period.value,
                        **fields,
                    )
                )
            else:
                for name, value in fields.items():
                    setattr(existing, name, value)

    def save_balance_sheet(self, statement: BalanceSheet) -> None:
        with session_scope() as session:
            existing = session.execute(
                select(BalanceSheetModel).where(
                    BalanceSheetModel.ticker == statement.key.ticker,
                    BalanceSheetModel.fiscal_year == statement.key.fiscal_year,
                    BalanceSheetModel.fiscal_quarter == statement.key.fiscal_quarter,
                    BalanceSheetModel.period == statement.key.period.value,
                )
            ).scalar_one_or_none()

            fields = dict(
                fiscal_date_ending=statement.fiscal_date_ending,
                reported_currency=statement.reported_currency,
                total_assets=statement.total_assets,
                total_current_assets=statement.total_current_assets,
                cash_and_equivalents=statement.cash_and_equivalents,
                total_liabilities=statement.total_liabilities,
                total_current_liabilities=statement.total_current_liabilities,
                total_debt=statement.total_debt,
                total_equity=statement.total_equity,
                shares_outstanding=statement.shares_outstanding,
                raw=statement.raw,
            )
            if existing is None:
                session.add(
                    BalanceSheetModel(
                        ticker=statement.key.ticker,
                        fiscal_year=statement.key.fiscal_year,
                        fiscal_quarter=statement.key.fiscal_quarter,
                        period=statement.key.period.value,
                        **fields,
                    )
                )
            else:
                for name, value in fields.items():
                    setattr(existing, name, value)

    def save_cash_flow_statement(self, statement: CashFlowStatement) -> None:
        with session_scope() as session:
            existing = session.execute(
                select(CashFlowStatementModel).where(
                    CashFlowStatementModel.ticker == statement.key.ticker,
                    CashFlowStatementModel.fiscal_year == statement.key.fiscal_year,
                    CashFlowStatementModel.fiscal_quarter == statement.key.fiscal_quarter,
                    CashFlowStatementModel.period == statement.key.period.value,
                )
            ).scalar_one_or_none()

            fields = dict(
                fiscal_date_ending=statement.fiscal_date_ending,
                reported_currency=statement.reported_currency,
                operating_cash_flow=statement.operating_cash_flow,
                capital_expenditures=statement.capital_expenditures,
                free_cash_flow=statement.free_cash_flow,
                dividends_paid=statement.dividends_paid,
                net_change_in_cash=statement.net_change_in_cash,
                raw=statement.raw,
            )
            if existing is None:
                session.add(
                    CashFlowStatementModel(
                        ticker=statement.key.ticker,
                        fiscal_year=statement.key.fiscal_year,
                        fiscal_quarter=statement.key.fiscal_quarter,
                        period=statement.key.period.value,
                        **fields,
                    )
                )
            else:
                for name, value in fields.items():
                    setattr(existing, name, value)

    def get_income_statements(
        self, ticker: str, period: Period = Period.ANNUAL, limit: int = 5
    ) -> list[IncomeStatement]:
        with session_scope() as session:
            rows = session.execute(
                select(IncomeStatementModel)
                .where(
                    IncomeStatementModel.ticker == ticker.strip().upper(),
                    IncomeStatementModel.period == period.value,
                )
                .order_by(IncomeStatementModel.fiscal_date_ending.desc())
                .limit(limit)
            ).scalars().all()
            return [_income_to_domain(row) for row in rows]

    def get_balance_sheets(
        self, ticker: str, period: Period = Period.ANNUAL, limit: int = 5
    ) -> list[BalanceSheet]:
        with session_scope() as session:
            rows = session.execute(
                select(BalanceSheetModel)
                .where(
                    BalanceSheetModel.ticker == ticker.strip().upper(),
                    BalanceSheetModel.period == period.value,
                )
                .order_by(BalanceSheetModel.fiscal_date_ending.desc())
                .limit(limit)
            ).scalars().all()
            return [_balance_to_domain(row) for row in rows]

    def get_cash_flow_statements(
        self, ticker: str, period: Period = Period.ANNUAL, limit: int = 5
    ) -> list[CashFlowStatement]:
        with session_scope() as session:
            rows = session.execute(
                select(CashFlowStatementModel)
                .where(
                    CashFlowStatementModel.ticker == ticker.strip().upper(),
                    CashFlowStatementModel.period == period.value,
                )
                .order_by(CashFlowStatementModel.fiscal_date_ending.desc())
                .limit(limit)
            ).scalars().all()
            return [_cash_flow_to_domain(row) for row in rows]
