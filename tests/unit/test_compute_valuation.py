from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.compute_valuation import (
    ComputeValuationUseCase,
    NoFinancialDataError,
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
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import FakeCompanyRepository, FakeDataProvider, FakeFinancialStatementRepository


def _company() -> Company:
    return Company(
        ticker="TEST", name="Test Co", sector=Sector.TECHNOLOGY,
        industry="Software", exchange="NASDAQ", country="US",
    )


def test_pe_and_ps_computed_correctly_against_market_cap() -> None:
    company_repo = FakeCompanyRepository()
    company_repo.save(_company())
    statement_repo = FakeFinancialStatementRepository()
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("TEST", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31),
            reported_currency="USD",
            revenue=1000.0,
            net_income=100.0,
        )
    )
    provider = FakeDataProvider(
        company=_company(),
        quote=MarketQuote(
            ticker="TEST", price=50.0, market_cap=2000.0,
            as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    use_case = ComputeValuationUseCase(get_financials, provider)

    result = use_case.execute("TEST")

    assert result.price_to_earnings == 20.0  # 2000 / 100
    assert result.price_to_sales == 2.0      # 2000 / 1000
    assert result.fundamentals_fiscal_year == 2024


def test_raises_when_no_financial_data() -> None:
    company_repo = FakeCompanyRepository()
    company_repo.save(_company())
    statement_repo = FakeFinancialStatementRepository()
    provider = FakeDataProvider(company=_company())
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    use_case = ComputeValuationUseCase(get_financials, provider)

    try:
        use_case.execute("TEST")
        raise AssertionError("expected NoFinancialDataError")
    except NoFinancialDataError:
        pass


def test_enterprise_value_and_ev_to_ebitda_computed_correctly() -> None:
    company_repo = FakeCompanyRepository()
    company_repo.save(_company())
    statement_repo = FakeFinancialStatementRepository()
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("TEST", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31),
            reported_currency="USD", ebitda=500.0,
        )
    )
    statement_repo.save_balance_sheet(
        BalanceSheet(
            key=FiscalPeriodKey("TEST", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31),
            reported_currency="USD", total_debt=300.0, cash_and_equivalents=100.0,
        )
    )
    provider = FakeDataProvider(
        company=_company(),
        quote=MarketQuote(
            ticker="TEST", price=10.0, market_cap=5000.0,
            as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    use_case = ComputeValuationUseCase(get_financials, provider)

    result = use_case.execute("TEST")

    # EV = market_cap + debt - cash = 5000 + 300 - 100 = 5200
    assert result.enterprise_value == 5200.0
    # EV/EBITDA = 5200 / 500 = 10.4
    assert result.ev_to_ebitda == 10.4


def test_missing_balance_sheet_yields_none_ev_not_a_crash() -> None:
    company_repo = FakeCompanyRepository()
    company_repo.save(_company())
    statement_repo = FakeFinancialStatementRepository()
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("TEST", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31),
            reported_currency="USD", net_income=100.0,
        )
    )
    provider = FakeDataProvider(
        company=_company(),
        quote=MarketQuote(
            ticker="TEST", price=10.0, market_cap=1000.0,
            as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    use_case = ComputeValuationUseCase(get_financials, provider)

    result = use_case.execute("TEST")

    assert result.enterprise_value is None
    assert result.ev_to_ebitda is None
    assert result.price_to_book is None
    assert result.price_to_earnings == 10.0  # still computable — doesn't need balance sheet
