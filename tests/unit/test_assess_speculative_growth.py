"""Tests for AssessSpeculativeGrowthUseCase — real logic verified with
fakes, no mocks needed."""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.assess_speculative_growth import (
    AssessSpeculativeGrowthUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
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
from tests.unit.fakes import (
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFinancialStatementRepository,
)

TICKER = "ROCKET"


def _key(year: int) -> FiscalPeriodKey:
    return FiscalPeriodKey(ticker=TICKER, fiscal_year=year, period=Period.ANNUAL)


def _income(year: int, revenue: float, net_income: float | None = -5_000_000) -> IncomeStatement:
    return IncomeStatement(
        key=_key(year), fiscal_date_ending=date(year, 12, 31), reported_currency="USD",
        revenue=revenue, net_income=net_income,
    )


def _build(
    income_statements, balance_sheets=None, cash_flow_statements=None, market_cap=1_000_000_000
):
    company = Company(
        ticker=TICKER, name="Rocket Inc", sector=Sector.TECHNOLOGY,
        industry="Software", exchange="NASDAQ", country="US",
    )
    company_repo = FakeCompanyRepository()
    company_repo.save(company)

    statement_repo = FakeFinancialStatementRepository()
    for s in income_statements:
        statement_repo.save_income_statement(s)
    for s in balance_sheets or []:
        statement_repo.save_balance_sheet(s)
    for s in cash_flow_statements or []:
        statement_repo.save_cash_flow_statement(s)

    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)

    provider = FakeDataProvider(
        company=company,
        income_statements=income_statements,
        balance_sheets=balance_sheets or [],
        cash_flow_statements=cash_flow_statements or [],
        quote=MarketQuote(ticker=TICKER, price=10.0, market_cap=market_cap, as_of=datetime.now(timezone.utc)),
    )
    compute_valuation = ComputeValuationUseCase(get_financials, provider)

    return AssessSpeculativeGrowthUseCase(get_financials, compute_valuation)


def test_detects_accelerating_growth() -> None:
    # 2023->2024: 50% growth. 2024->2025: 100% growth. Accelerating.
    statements = [_income(2023, 10_000_000), _income(2024, 15_000_000), _income(2025, 30_000_000)]
    use_case = _build(statements)

    result = use_case.execute(TICKER)

    assert result.growth_trend == "accelerating"
    assert abs(result.revenue_growth_latest_yoy - 1.0) < 0.01  # 100%
    assert abs(result.revenue_growth_prior_yoy - 0.5) < 0.01  # 50%


def test_detects_decelerating_growth() -> None:
    # 2023->2024: 100% growth. 2024->2025: 20% growth. Decelerating.
    statements = [_income(2023, 10_000_000), _income(2024, 20_000_000), _income(2025, 24_000_000)]
    use_case = _build(statements)

    result = use_case.execute(TICKER)

    assert result.growth_trend == "decelerating"
    assert "decelerating" in " ".join(result.risk_flags).lower()


def test_insufficient_data_with_only_one_year() -> None:
    use_case = _build([_income(2025, 10_000_000)])

    result = use_case.execute(TICKER)

    assert result.growth_trend == "insufficient_data"
    assert result.revenue_growth_latest_yoy is None
    assert any("limited operating history" in f.lower() for f in result.risk_flags)


def test_flags_unprofitable_company() -> None:
    statements = [_income(2024, 10_000_000, net_income=-2_000_000), _income(2025, 20_000_000, net_income=-3_000_000)]
    use_case = _build(statements)

    result = use_case.execute(TICKER)

    assert result.is_profitable is False
    assert any("unprofitable" in f.lower() for f in result.risk_flags)


def test_profitable_company_gets_no_unprofitable_flag() -> None:
    statements = [_income(2024, 10_000_000, net_income=1_000_000), _income(2025, 20_000_000, net_income=3_000_000)]
    use_case = _build(statements)

    result = use_case.execute(TICKER)

    assert result.is_profitable is True
    assert not any("unprofitable" in f.lower() for f in result.risk_flags)


def test_computes_cash_runway_when_burning_cash() -> None:
    statements = [_income(2024, 10_000_000), _income(2025, 15_000_000)]
    balance_sheets = [BalanceSheet(
        key=_key(2025), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        cash_and_equivalents=6_000_000,
    )]
    cash_flows = [CashFlowStatement(
        key=_key(2025), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        operating_cash_flow=-1_200_000,  # burning $100k/month
    )]
    use_case = _build(statements, balance_sheets, cash_flows)

    result = use_case.execute(TICKER)

    # $6M / $100k per month = 60 months — a healthy runway, correctly
    # computed but NOT itself a risk (see the separate short-runway
    # test below for when this DOES become a flag).
    assert result.cash_runway_months is not None
    assert abs(result.cash_runway_months - 60) < 1
    assert not any("runway" in f.lower() for f in result.risk_flags)


def test_flags_short_runway_as_a_risk() -> None:
    statements = [_income(2024, 10_000_000), _income(2025, 15_000_000)]
    balance_sheets = [BalanceSheet(
        key=_key(2025), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        cash_and_equivalents=500_000,
    )]
    cash_flows = [CashFlowStatement(
        key=_key(2025), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        operating_cash_flow=-1_200_000,  # burning $100k/month
    )]
    use_case = _build(statements, balance_sheets, cash_flows)

    result = use_case.execute(TICKER)

    # $500k / $100k per month = 5 months — genuinely short, should flag.
    assert result.cash_runway_months is not None
    assert abs(result.cash_runway_months - 5) < 1
    assert any("runway" in f.lower() for f in result.risk_flags)


def test_no_runway_flag_when_not_burning_cash() -> None:
    """Runway is only a meaningful concept when operating cash flow is
    negative — a profitable-on-a-cash-basis company shouldn't get an
    invented runway figure."""
    statements = [_income(2024, 10_000_000), _income(2025, 15_000_000)]
    balance_sheets = [BalanceSheet(
        key=_key(2025), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        cash_and_equivalents=6_000_000,
    )]
    cash_flows = [CashFlowStatement(
        key=_key(2025), fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        operating_cash_flow=500_000,  # positive — not burning cash
    )]
    use_case = _build(statements, balance_sheets, cash_flows)

    result = use_case.execute(TICKER)

    assert result.cash_runway_months is None
    assert not any("runway" in f.lower() for f in result.risk_flags)


def test_flags_small_market_cap() -> None:
    statements = [_income(2024, 10_000_000), _income(2025, 15_000_000)]
    use_case = _build(statements, market_cap=200_000_000)  # well under $2B threshold

    result = use_case.execute(TICKER)

    assert any("small market cap" in f.lower() for f in result.risk_flags)


def test_large_cap_gets_no_small_cap_flag() -> None:
    statements = [_income(2024, 10_000_000), _income(2025, 15_000_000)]
    use_case = _build(statements, market_cap=500_000_000_000)  # $500B

    result = use_case.execute(TICKER)

    assert not any("small market cap" in f.lower() for f in result.risk_flags)


def test_never_fabricates_growth_rate_when_revenue_is_none() -> None:
    """The honesty property this whole feature is built around: a
    missing revenue figure must produce None, never a guessed number."""
    statements = [
        IncomeStatement(key=_key(2024), fiscal_date_ending=date(2024, 12, 31), reported_currency="USD", revenue=None),
        _income(2025, 15_000_000),
    ]
    use_case = _build(statements)

    result = use_case.execute(TICKER)

    assert result.revenue_growth_latest_yoy is None
