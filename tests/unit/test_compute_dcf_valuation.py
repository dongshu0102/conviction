"""Tests for ComputeDcfUseCase and ComputeReverseDcfUseCase — real
financial data wired to the (separately, hand-verified) pure math."""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.compute_dcf_valuation import (
    ComputeDcfUseCase,
    ComputeReverseDcfUseCase,
    InsufficientDataError,
)
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import (
    BalanceSheet, CashFlowStatement, FiscalPeriodKey, IncomeStatement, Period,
)
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import FakeCompanyRepository, FakeDataProvider, FakeFinancialStatementRepository

TICKER = "ROCKET"


def _key(year: int) -> FiscalPeriodKey:
    return FiscalPeriodKey(ticker=TICKER, fiscal_year=year, period=Period.ANNUAL)


def _setup(
    fcf: float | None = 100_000_000,
    revenue_by_year: dict[int, float] | None = None,
    total_debt: float = 200_000_000,
    cash: float = 50_000_000,
    shares_outstanding: float = 10_000_000,
    quote_price: float = 50.0,
):
    company = Company(
        ticker=TICKER, name="Rocket Inc", sector=Sector.TECHNOLOGY,
        industry="Software", exchange="NASDAQ", country="US",
    )
    company_repo = FakeCompanyRepository()
    company_repo.save(company)

    statement_repo = FakeFinancialStatementRepository()
    if revenue_by_year:
        for year, revenue in revenue_by_year.items():
            statement_repo.save_income_statement(
                IncomeStatement(key=_key(year), fiscal_date_ending=date(year, 12, 31),
                                 reported_currency="USD", revenue=revenue)
            )
    if fcf is not None:
        statement_repo.save_cash_flow_statement(CashFlowStatement(
            key=_key(2025), fiscal_date_ending=date(2025, 12, 31),
            reported_currency="USD", free_cash_flow=fcf,
        ))
    statement_repo.save_balance_sheet(BalanceSheet(
        key=_key(2025), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        total_debt=total_debt, cash_and_equivalents=cash, shares_outstanding=shares_outstanding,
    ))

    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    provider = FakeDataProvider(
        company=company, income_statements=[], balance_sheets=[], cash_flow_statements=[],
        quote=MarketQuote(ticker=TICKER, price=quote_price, market_cap=quote_price * shares_outstanding,
                           as_of=datetime.now(timezone.utc)),
    )
    return get_financials, provider


def test_dcf_uses_the_most_recent_free_cash_flow_and_real_net_debt() -> None:
    get_financials, provider = _setup(fcf=100_000_000, total_debt=200_000_000, cash=50_000_000)
    use_case = ComputeDcfUseCase(get_financials, provider)

    assessment = use_case.execute(TICKER, growth_rate=0.08, years=5)

    assert assessment.assumptions.base_fcf == 100_000_000
    assert assessment.assumptions.net_debt == 150_000_000  # 200M debt - 50M cash
    assert assessment.assumptions.growth_rate_was_default is False
    assert assessment.result.enterprise_value > 0
    assert assessment.result.per_share_value is not None


def test_dcf_falls_back_to_operating_cash_flow_minus_capex_when_fcf_is_null() -> None:
    get_financials, _ = _setup(fcf=None)
    # Manually inject a cash flow statement without free_cash_flow set,
    # but with operating_cash_flow and capital_expenditures instead.
    company_repo = FakeCompanyRepository()
    company_repo.save(Company(ticker=TICKER, name="Rocket Inc", sector=Sector.TECHNOLOGY,
                               industry="Software", exchange="NASDAQ", country="US"))
    statement_repo = FakeFinancialStatementRepository()
    statement_repo.save_cash_flow_statement(CashFlowStatement(
        key=_key(2025), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        operating_cash_flow=120_000_000, capital_expenditures=-20_000_000,  # capex reported negative
    ))
    statement_repo.save_balance_sheet(BalanceSheet(
        key=_key(2025), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        total_debt=0, cash_and_equivalents=0, shares_outstanding=10_000_000,
    ))
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker(TICKER), income_statements=[], balance_sheets=[],
        cash_flow_statements=[],
        quote=MarketQuote(ticker=TICKER, price=10.0, market_cap=100_000_000, as_of=datetime.now(timezone.utc)),
    )
    use_case = ComputeDcfUseCase(GetCompanyFinancialsUseCase(company_repo, statement_repo), provider)

    assessment = use_case.execute(TICKER, growth_rate=0.05, years=3)

    assert assessment.assumptions.base_fcf == 100_000_000  # 120M - 20M


def test_dcf_derives_a_default_growth_rate_from_historical_revenue_cagr() -> None:
    get_financials, provider = _setup(revenue_by_year={2021: 100_000_000, 2025: 146_410_000})
    use_case = ComputeDcfUseCase(get_financials, provider)

    assessment = use_case.execute(TICKER)  # no growth_rate supplied

    assert assessment.assumptions.growth_rate_was_default is True
    # (146.41/100)^(1/4) - 1 = 0.10, a clean round-trip of the earlier hand-verified example
    assert abs(assessment.assumptions.growth_rate - 0.10) < 1e-6


def test_dcf_raises_insufficient_data_when_no_cash_flow_statement_exists() -> None:
    get_financials, provider = _setup(fcf=None)
    use_case = ComputeDcfUseCase(get_financials, provider)
    try:
        use_case.execute(TICKER, growth_rate=0.05)
        raise AssertionError("expected InsufficientDataError")
    except InsufficientDataError:
        pass


def test_dcf_propagates_company_not_found_for_a_non_ingested_ticker() -> None:
    company_repo = FakeCompanyRepository()
    statement_repo = FakeFinancialStatementRepository()
    provider = FakeDataProvider(
        company=None, income_statements=[], balance_sheets=[], cash_flow_statements=[],
    )
    use_case = ComputeDcfUseCase(GetCompanyFinancialsUseCase(company_repo, statement_repo), provider)
    try:
        use_case.execute("GHOST", growth_rate=0.05)
        raise AssertionError("expected CompanyNotFoundError")
    except CompanyNotFoundError:
        pass


def test_reverse_dcf_solves_against_the_real_live_quote_price() -> None:
    get_financials, provider = _setup(fcf=100_000_000, quote_price=25.0, shares_outstanding=10_000_000)
    use_case = ComputeReverseDcfUseCase(get_financials, provider)

    result = use_case.execute(TICKER)

    assert result.current_price == 25.0
    assert result.implied_growth_rate is not None


def test_reverse_dcf_requires_real_shares_outstanding() -> None:
    get_financials, provider = _setup(fcf=100_000_000, shares_outstanding=0)
    use_case = ComputeReverseDcfUseCase(get_financials, provider)
    try:
        use_case.execute(TICKER)
        raise AssertionError("expected InsufficientDataError")
    except InsufficientDataError:
        pass


def test_dcf_derives_shares_outstanding_from_market_cap_and_price_not_the_unreliable_balance_sheet_field() -> None:
    """Regression test for a real production bug: balance_sheet.shares_outstanding
    is mapped from FMP's "commonStock" line (a dollar value, not a share
    count) and was producing per-share values off by roughly 1000x.
    market_cap / price is exact and must be preferred whenever a quote
    is available."""
    company_repo = FakeCompanyRepository()
    company_repo.save(Company(ticker=TICKER, name="Rocket Inc", sector=Sector.TECHNOLOGY,
                               industry="Software", exchange="NASDAQ", country="US"))
    statement_repo = FakeFinancialStatementRepository()
    statement_repo.save_cash_flow_statement(CashFlowStatement(
        key=_key(2025), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        free_cash_flow=100_000_000,
    ))
    # Deliberately wrong balance-sheet figure, mimicking the real bug
    # (a dollar par value, not a share count) — must be ignored.
    statement_repo.save_balance_sheet(BalanceSheet(
        key=_key(2025), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        total_debt=0, cash_and_equivalents=0, shares_outstanding=24_000,
    ))
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker(TICKER), income_statements=[], balance_sheets=[],
        cash_flow_statements=[],
        # Real, exact relationship: market_cap = price x true share count.
        quote=MarketQuote(ticker=TICKER, price=180.0, market_cap=180.0 * 24_000_000_000,
                           as_of=datetime.now(timezone.utc)),
    )
    use_case = ComputeDcfUseCase(GetCompanyFinancialsUseCase(company_repo, statement_repo), provider)

    assessment = use_case.execute(TICKER, growth_rate=0.05, years=3)

    assert abs(assessment.assumptions.shares_outstanding - 24_000_000_000) < 1
    assert assessment.result.per_share_value < 1000  # sane, not the ~91,000 the bug produced
