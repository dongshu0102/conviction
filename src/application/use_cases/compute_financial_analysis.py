"""Use case: compute financial ratios and trends from ingested statements.

Deliberately deterministic Python arithmetic, not an LLM call. Margins,
growth rates, and leverage ratios have exact right answers — computing
them here means every downstream consumer (API, future Valuation Agent,
future Company Research Agent enhancements) reads the same correct
numbers, rather than each one asking an LLM to redo arithmetic and
risking a different, wrong answer each time.
"""
from __future__ import annotations

from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.domain.entities.financial_analysis import CompanyFinancialAnalysis, YearlyRatios
from src.domain.entities.financial_statement import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
)


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """Division that returns None rather than raising or fabricating a
    value — missing data or a zero denominator both mean "this ratio is
    not knowable," not "this ratio is zero."
    """
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


class ComputeFinancialAnalysisUseCase:
    def __init__(self, get_financials: GetCompanyFinancialsUseCase) -> None:
        self._get_financials = get_financials

    def execute(self, ticker: str, years: int = 5) -> CompanyFinancialAnalysis:
        ticker = ticker.strip().upper()

        try:
            financials = self._get_financials.execute(ticker, years=years)
        except CompanyNotFoundError:
            raise

        income_by_year: dict[int, IncomeStatement] = {
            s.key.fiscal_year: s for s in financials.income_statements
        }
        balance_by_year: dict[int, BalanceSheet] = {
            s.key.fiscal_year: s for s in financials.balance_sheets
        }
        cashflow_by_year: dict[int, CashFlowStatement] = {
            s.key.fiscal_year: s for s in financials.cash_flow_statements
        }

        # Union of years across all three statement types — a year with
        # only a balance sheet (or only a cash flow statement) ingested
        # must still be represented, not silently dropped because income
        # statements happen to be the first thing checked.
        fiscal_years = sorted(
            set(income_by_year) | set(balance_by_year) | set(cashflow_by_year)
        )

        yearly_ratios: list[YearlyRatios] = []
        prior_revenue: float | None = None

        for year in fiscal_years:
            income = income_by_year.get(year)
            balance = balance_by_year.get(year)
            cashflow = cashflow_by_year.get(year)

            revenue = income.revenue if income else None
            revenue_growth = (
                _safe_div(revenue - prior_revenue, prior_revenue)
                if revenue is not None and prior_revenue is not None
                else None
            )

            yearly_ratios.append(
                YearlyRatios(
                    fiscal_year=year,
                    revenue_growth_yoy=revenue_growth,
                    gross_margin=_safe_div(income.gross_profit, revenue) if income else None,
                    operating_margin=_safe_div(income.operating_income, revenue) if income else None,
                    net_margin=_safe_div(income.net_income, revenue) if income else None,
                    free_cash_flow_margin=(
                        _safe_div(cashflow.free_cash_flow, revenue) if cashflow else None
                    ),
                    return_on_equity=(
                        _safe_div(income.net_income, balance.total_equity)
                        if income and balance
                        else None
                    ),
                    return_on_assets=(
                        _safe_div(income.net_income, balance.total_assets)
                        if income and balance
                        else None
                    ),
                    debt_to_equity=(
                        _safe_div(balance.total_debt, balance.total_equity) if balance else None
                    ),
                    current_ratio=(
                        _safe_div(balance.total_current_assets, balance.total_current_liabilities)
                        if balance
                        else None
                    ),
                )
            )

            if revenue is not None:
                prior_revenue = revenue

        return CompanyFinancialAnalysis(ticker=ticker, yearly_ratios=yearly_ratios)
