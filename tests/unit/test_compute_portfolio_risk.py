from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.manage_portfolio import AddHoldingUseCase, CreatePortfolioUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import BalanceSheet, FiscalPeriodKey, Period
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import (
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFinancialStatementRepository,
    FakePortfolioRepository,
)


def _setup(companies_and_sectors: dict[str, Sector]):
    company_repo = FakeCompanyRepository()
    for ticker, sector in companies_and_sectors.items():
        company_repo.save(
            Company(
                ticker=ticker, name=f"{ticker} Inc.", sector=sector,
                industry="X", exchange="NASDAQ", country="US",
            )
        )
    return company_repo


def test_two_equal_positions_give_expected_hhi_and_no_dominant_position() -> None:
    company_repo = _setup({"AAPL": Sector.TECHNOLOGY, "MSFT": Sector.TECHNOLOGY})
    statement_repo = FakeFinancialStatementRepository()
    portfolio_repo = FakePortfolioRepository()

    create = CreatePortfolioUseCase(portfolio_repo)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    portfolio = create.execute("alice", "Test")
    # Equal dollar amounts: 10 shares @ $100 each = $1000 each position
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)
    add_holding.execute(portfolio.portfolio_id, "MSFT", shares=10, cost_basis_per_share=100)

    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            "MSFT": MarketQuote(ticker="MSFT", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    risk_use_case = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo)

    result = risk_use_case.execute(portfolio.portfolio_id)

    # Two exactly-equal positions: weight = 0.5 each
    # HHI = 0.5^2 + 0.5^2 = 0.5 (the maximum diversification for 2 positions)
    assert result.largest_position_weight == 0.5
    assert abs(result.herfindahl_index - 0.5) < 1e-9

    # Both in Technology -> 100% sector concentration in one sector
    assert len(result.sector_exposures) == 1
    assert result.sector_exposures[0].sector == "Technology"
    assert abs(result.sector_exposures[0].weight - 1.0) < 1e-9


def test_concentrated_single_position_gives_hhi_of_one() -> None:
    company_repo = _setup({"AAPL": Sector.TECHNOLOGY})
    statement_repo = FakeFinancialStatementRepository()
    portfolio_repo = FakePortfolioRepository()

    create = CreatePortfolioUseCase(portfolio_repo)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    portfolio = create.execute("alice", "Test")
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)

    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    risk_use_case = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo)

    result = risk_use_case.execute(portfolio.portfolio_id)

    assert result.largest_position_weight == 1.0
    assert result.herfindahl_index == 1.0  # maximum concentration


def test_weighted_average_leverage_computed_correctly() -> None:
    company_repo = _setup({"AAPL": Sector.TECHNOLOGY, "MSFT": Sector.TECHNOLOGY})
    statement_repo = FakeFinancialStatementRepository()
    portfolio_repo = FakePortfolioRepository()

    # AAPL: debt/equity = 2.0 (300/150), 75% of portfolio by market value
    statement_repo.save_balance_sheet(
        BalanceSheet(
            key=FiscalPeriodKey("AAPL", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
            total_debt=300.0, total_equity=150.0,
        )
    )
    # MSFT: debt/equity = 0.5 (50/100), 25% of portfolio by market value
    statement_repo.save_balance_sheet(
        BalanceSheet(
            key=FiscalPeriodKey("MSFT", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
            total_debt=50.0, total_equity=100.0,
        )
    )

    create = CreatePortfolioUseCase(portfolio_repo)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    portfolio = create.execute("alice", "Test")
    # 30 shares @ $100 = $3000 (75% of $4000 total)
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=30, cost_basis_per_share=100)
    # 10 shares @ $100 = $1000 (25% of $4000 total)
    add_holding.execute(portfolio.portfolio_id, "MSFT", shares=10, cost_basis_per_share=100)

    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            "MSFT": MarketQuote(ticker="MSFT", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    risk_use_case = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo)

    result = risk_use_case.execute(portfolio.portfolio_id)

    # Weighted avg D/E = 2.0*0.75 + 0.5*0.25 = 1.5 + 0.125 = 1.625
    assert abs(result.weighted_avg_debt_to_equity - 1.625) < 1e-9
    assert result.excluded_from_leverage_calc == []


def test_holding_missing_balance_sheet_is_excluded_not_silently_dropped() -> None:
    company_repo = _setup({"AAPL": Sector.TECHNOLOGY})
    statement_repo = FakeFinancialStatementRepository()  # no balance sheet saved
    portfolio_repo = FakePortfolioRepository()

    create = CreatePortfolioUseCase(portfolio_repo)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    portfolio = create.execute("alice", "Test")
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)

    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    risk_use_case = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo)

    result = risk_use_case.execute(portfolio.portfolio_id)

    assert result.weighted_avg_debt_to_equity is None
    assert result.excluded_from_leverage_calc == ["AAPL"]
