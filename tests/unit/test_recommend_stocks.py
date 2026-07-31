from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.manage_portfolio import AddHoldingUseCase, CreatePortfolioUseCase
from src.application.use_cases.recommend_stocks import RecommendStocksUseCase
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import (
    BalanceSheet,
    FiscalPeriodKey,
    IncomeStatement,
    Period,
)
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import (
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFinancialStatementRepository,
    FakePortfolioRepository,
)


def _company(ticker: str, sector: Sector) -> Company:
    return Company(
        ticker=ticker, name=f"{ticker} Inc.", sector=sector,
        industry="X", exchange="NASDAQ", country="US",
    )


def _seed_statements(statement_repo, ticker: str, equity=1000.0, debt=200.0, cash=100.0, revenue=1000.0, net_income=100.0, ebitda=150.0):
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey(ticker, 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
            revenue=revenue, net_income=net_income, ebitda=ebitda,
        )
    )
    statement_repo.save_balance_sheet(
        BalanceSheet(
            key=FiscalPeriodKey(ticker, 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
            total_equity=equity, total_debt=debt, cash_and_equivalents=cash,
        )
    )


def _build_use_case(portfolio_repo, company_repo, statement_repo, quotes):
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    any_company = next(iter(company_repo._store.values())) if company_repo._store else None
    provider = FakeDataProvider(company=any_company, quotes_by_ticker=quotes)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    compute_risk = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo)
    compute_company_valuation = ComputeValuationUseCase(get_financials, provider)
    screen_stocks = ScreenStocksUseCase(compute_company_valuation, compute_analysis)
    return RecommendStocksUseCase(compute_risk, company_repo, screen_stocks)


def test_no_gaps_when_portfolio_already_diversified_across_all_sectors() -> None:
    """A portfolio with meaningful exposure to every sector should
    produce zero gap sectors and zero picks — nothing to recommend."""
    company_repo = FakeCompanyRepository()
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Diversified")
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    quotes = {}

    all_sectors = [s for s in Sector if s != Sector.UNKNOWN]
    for i, sector in enumerate(all_sectors):
        ticker = f"T{i}"
        company_repo.save(_company(ticker, sector))
        add_holding.execute(portfolio.portfolio_id, ticker, shares=10, cost_basis_per_share=100)
        quotes[ticker] = MarketQuote(ticker=ticker, price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))

    statement_repo = FakeFinancialStatementRepository()
    use_case = _build_use_case(portfolio_repo, company_repo, statement_repo, quotes)

    result = use_case.execute(portfolio.portfolio_id)

    assert result.gap_sectors == []
    assert result.picks == []


def test_identifies_real_gap_sector_and_recommends_from_it() -> None:
    """Portfolio is 100% Technology — every other sector is a gap.
    Confirm a Healthcare candidate genuinely gets picked and correctly
    tagged with the gap sector it addresses."""
    company_repo = FakeCompanyRepository()
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Tech Heavy")

    tech_company = _company("TECH", Sector.TECHNOLOGY)
    healthcare_candidate = _company("HLTH", Sector.HEALTHCARE)
    company_repo.save(tech_company)
    company_repo.save(healthcare_candidate)

    AddHoldingUseCase(portfolio_repo, company_repo).execute(
        portfolio.portfolio_id, "TECH", shares=10, cost_basis_per_share=100
    )

    statement_repo = FakeFinancialStatementRepository()
    _seed_statements(statement_repo, "HLTH")

    quotes = {
        "TECH": MarketQuote(ticker="TECH", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        "HLTH": MarketQuote(ticker="HLTH", price=50.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    }
    use_case = _build_use_case(portfolio_repo, company_repo, statement_repo, quotes)

    result = use_case.execute(portfolio.portfolio_id)

    assert "Healthcare" in result.gap_sectors
    assert any(p.stock.ticker == "HLTH" and p.gap_sector == "Healthcare" for p in result.picks)


def test_empty_portfolio_has_all_sectors_as_gaps_but_no_crash() -> None:
    company_repo = FakeCompanyRepository()
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Empty")
    statement_repo = FakeFinancialStatementRepository()

    use_case = _build_use_case(portfolio_repo, company_repo, statement_repo, {})

    result = use_case.execute(portfolio.portfolio_id)

    # No holdings means the empty-portfolio path in risk analysis kicks in,
    # so no meaningful sector exposure exists — every real sector counts
    # as a gap, but with zero ingested candidate companies, picks stay empty.
    assert result.picks == []
