from __future__ import annotations

from datetime import date

from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import (
    BalanceSheet,
    CashFlowStatement,
    FiscalPeriodKey,
    IncomeStatement,
    Period,
)
from tests.unit.fakes import FakeCompanyRepository, FakeFinancialStatementRepository


def _build_use_case():
    company_repo = FakeCompanyRepository()
    company_repo.save(
        Company(
            ticker="TEST", name="Test Co", sector=Sector.TECHNOLOGY,
            industry="Software", exchange="NASDAQ", country="US",
        )
    )
    statement_repo = FakeFinancialStatementRepository()
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    return ComputeFinancialAnalysisUseCase(get_financials), statement_repo


def test_margins_computed_correctly_with_exact_values() -> None:
    use_case, statement_repo = _build_use_case()
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("TEST", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31),
            reported_currency="USD",
            revenue=1000.0,
            gross_profit=400.0,   # 40% gross margin
            operating_income=200.0,  # 20% operating margin
            net_income=100.0,     # 10% net margin
        )
    )

    result = use_case.execute("TEST", years=1)

    ratios = result.yearly_ratios[0]
    assert ratios.gross_margin == 0.4
    assert ratios.operating_margin == 0.2
    assert ratios.net_margin == 0.1


def test_revenue_growth_requires_two_years_and_computes_exactly() -> None:
    use_case, statement_repo = _build_use_case()
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("TEST", 2023, Period.ANNUAL),
            fiscal_date_ending=date(2023, 12, 31),
            reported_currency="USD", revenue=1000.0,
        )
    )
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("TEST", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31),
            reported_currency="USD", revenue=1100.0,  # exactly 10% growth
        )
    )

    result = use_case.execute("TEST", years=2)

    # Ascending order: 2023 first (no prior year), then 2024
    assert result.yearly_ratios[0].fiscal_year == 2023
    assert result.yearly_ratios[0].revenue_growth_yoy is None
    assert result.yearly_ratios[1].fiscal_year == 2024
    assert result.yearly_ratios[1].revenue_growth_yoy == 0.1


def test_missing_balance_sheet_yields_none_not_zero_or_error() -> None:
    """A ratio needing balance sheet data must be None when no balance
    sheet was ingested for that year — never silently 0, which would
    look like a real (very bad) financial result."""
    use_case, statement_repo = _build_use_case()
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("TEST", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31),
            reported_currency="USD", revenue=1000.0, net_income=100.0,
        )
    )
    # Deliberately no balance sheet saved for this year.

    result = use_case.execute("TEST", years=1)

    ratios = result.yearly_ratios[0]
    assert ratios.return_on_equity is None
    assert ratios.return_on_assets is None
    assert ratios.debt_to_equity is None
    assert ratios.current_ratio is None


def test_zero_denominator_yields_none_not_a_crash() -> None:
    use_case, statement_repo = _build_use_case()
    statement_repo.save_balance_sheet(
        BalanceSheet(
            key=FiscalPeriodKey("TEST", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31),
            reported_currency="USD",
            total_equity=0.0,  # zero equity — division would raise ZeroDivisionError if unguarded
        )
    )
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("TEST", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31),
            reported_currency="USD", net_income=50.0,
        )
    )

    result = use_case.execute("TEST", years=1)

    assert result.yearly_ratios[0].return_on_equity is None


def test_free_cash_flow_margin_uses_cashflow_statement() -> None:
    use_case, statement_repo = _build_use_case()
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("TEST", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31),
            reported_currency="USD", revenue=1000.0,
        )
    )
    statement_repo.save_cash_flow_statement(
        CashFlowStatement(
            key=FiscalPeriodKey("TEST", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31),
            reported_currency="USD", free_cash_flow=250.0,  # 25% FCF margin
        )
    )

    result = use_case.execute("TEST", years=1)

    assert result.yearly_ratios[0].free_cash_flow_margin == 0.25
