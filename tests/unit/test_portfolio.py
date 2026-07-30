from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.manage_portfolio import (
    AddHoldingUseCase,
    CreatePortfolioUseCase,
    PortfolioNotFoundError,
    RemoveHoldingUseCase,
    TickerNotIngestedError,
)
from src.domain.entities.company import Company, Sector
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import FakeCompanyRepository, FakeDataProvider, FakePortfolioRepository


def _company_repo(*tickers: str) -> FakeCompanyRepository:
    repo = FakeCompanyRepository()
    for ticker in tickers:
        repo.save(
            Company(
                ticker=ticker, name=f"{ticker} Inc.", sector=Sector.TECHNOLOGY,
                industry="Software", exchange="NASDAQ", country="US",
            )
        )
    return repo


def test_cannot_add_holding_for_never_ingested_ticker() -> None:
    portfolio_repo = FakePortfolioRepository()
    company_repo = _company_repo()  # empty — nothing ingested
    create_use_case = CreatePortfolioUseCase(portfolio_repo)
    add_use_case = AddHoldingUseCase(portfolio_repo, company_repo)

    portfolio = create_use_case.execute("alice", "My Portfolio")

    try:
        add_use_case.execute(portfolio.portfolio_id, "NOTINGESTED", shares=10, cost_basis_per_share=100)
        raise AssertionError("expected TickerNotIngestedError")
    except TickerNotIngestedError:
        pass


def test_cannot_add_holding_to_nonexistent_portfolio() -> None:
    portfolio_repo = FakePortfolioRepository()
    company_repo = _company_repo("AAPL")
    add_use_case = AddHoldingUseCase(portfolio_repo, company_repo)

    try:
        add_use_case.execute("fake-id", "AAPL", shares=10, cost_basis_per_share=100)
        raise AssertionError("expected PortfolioNotFoundError")
    except PortfolioNotFoundError:
        pass


def test_adding_same_ticker_twice_replaces_position_not_duplicates() -> None:
    portfolio_repo = FakePortfolioRepository()
    company_repo = _company_repo("AAPL")
    create_use_case = CreatePortfolioUseCase(portfolio_repo)
    add_use_case = AddHoldingUseCase(portfolio_repo, company_repo)

    portfolio = create_use_case.execute("alice", "My Portfolio")
    add_use_case.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)
    add_use_case.execute(portfolio.portfolio_id, "AAPL", shares=20, cost_basis_per_share=150)

    updated = portfolio_repo.get_by_id(portfolio.portfolio_id)
    assert len(updated.holdings) == 1
    assert updated.holdings[0].shares == 20
    assert updated.holdings[0].cost_basis_per_share == 150


def test_portfolio_valuation_computes_exact_totals_across_positions() -> None:
    portfolio_repo = FakePortfolioRepository()
    company_repo = _company_repo("AAPL", "MSFT")
    create_use_case = CreatePortfolioUseCase(portfolio_repo)
    add_use_case = AddHoldingUseCase(portfolio_repo, company_repo)

    portfolio = create_use_case.execute("alice", "My Portfolio")
    # 10 shares AAPL bought at $100, now worth $150 -> $500 gain
    add_use_case.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)
    # 5 shares MSFT bought at $200, now worth $180 -> -$100 loss
    add_use_case.execute(portfolio.portfolio_id, "MSFT", shares=5, cost_basis_per_share=200)

    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=150.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            "MSFT": MarketQuote(ticker="MSFT", price=180.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
    )
    valuation_use_case = ComputePortfolioValuationUseCase(portfolio_repo, provider)

    result = valuation_use_case.execute(portfolio.portfolio_id)

    # AAPL: market_value = 10*150 = 1500, cost_basis = 10*100 = 1000, gain = 500
    # MSFT: market_value = 5*180 = 900,  cost_basis = 5*200 = 1000,  gain = -100
    assert result.total_market_value == 2400.0   # 1500 + 900
    assert result.total_cost_basis == 2000.0      # 1000 + 1000
    assert result.total_unrealized_gain == 400.0  # 500 + (-100)

    aapl_position = next(p for p in result.positions if p.ticker == "AAPL")
    assert aapl_position.market_value == 1500.0
    assert aapl_position.unrealized_gain == 500.0
    assert aapl_position.weight == 1500.0 / 2400.0  # 62.5% of portfolio

    msft_position = next(p for p in result.positions if p.ticker == "MSFT")
    assert msft_position.unrealized_gain == -100.0


def test_remove_holding_returns_true_when_existed() -> None:
    portfolio_repo = FakePortfolioRepository()
    company_repo = _company_repo("AAPL")
    create_use_case = CreatePortfolioUseCase(portfolio_repo)
    add_use_case = AddHoldingUseCase(portfolio_repo, company_repo)
    remove_use_case = RemoveHoldingUseCase(portfolio_repo)

    portfolio = create_use_case.execute("alice", "My Portfolio")
    add_use_case.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)

    assert remove_use_case.execute(portfolio.portfolio_id, "AAPL") is True
    assert remove_use_case.execute(portfolio.portfolio_id, "AAPL") is False
