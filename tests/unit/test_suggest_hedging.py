from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.manage_option_holdings import AddOptionHoldingUseCase
from src.application.use_cases.manage_portfolio import AddHoldingUseCase, CreatePortfolioUseCase
from src.application.use_cases.suggest_hedging import SuggestHedgingUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.option import OptionContract, OptionQuote
from tests.unit.fakes import FakeCompanyRepository, FakeOptionsDataProvider, FakePortfolioRepository


def _quote(contract: OptionContract, delta) -> OptionQuote:
    return OptionQuote(
        contract=contract, bid=1.0, ask=1.1, last=1.05, implied_volatility=0.3,
        open_interest=100, volume=10, delta=delta, gamma=0.02, theta=-0.03, vega=0.15,
        underlying_price=150.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc), mid=1.05,
    )


def _company_repo(*tickers: str) -> FakeCompanyRepository:
    repo = FakeCompanyRepository()
    for t in tickers:
        repo.save(Company(ticker=t, name=f"{t} Inc.", sector=Sector.TECHNOLOGY, industry="X", exchange="X", country="US"))
    return repo


def test_option_only_exposure_suggests_correct_hedge() -> None:
    company_repo = _company_repo("AAPL")
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 3.20
    )
    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "call"): _quote(contract, 0.5)}
    )

    plan = SuggestHedgingUseCase(portfolio_repo, options_provider).execute(portfolio.portfolio_id)

    assert len(plan.suggestions) == 1
    s = plan.suggestions[0]
    assert s.underlying_ticker == "AAPL"
    assert abs(s.net_delta - 250.0) < 1e-9
    assert abs(s.shares_to_trade - (-250.0)) < 1e-9
    assert abs(s.resulting_delta - 0.0) < 1e-9


def test_combined_stock_and_option_delta_computed_correctly() -> None:
    company_repo = _company_repo("AAPL")
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Mixed")
    AddHoldingUseCase(portfolio_repo, company_repo).execute(
        portfolio.portfolio_id, "AAPL", shares=100, cost_basis_per_share=140.0
    )
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 3.20
    )
    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "call"): _quote(contract, 0.5)}
    )

    plan = SuggestHedgingUseCase(portfolio_repo, options_provider).execute(portfolio.portfolio_id)

    assert len(plan.suggestions) == 1
    s = plan.suggestions[0]
    assert abs(s.net_delta - 350.0) < 1e-9  # 100 (stock) + 250 (options) = 350
    assert abs(s.shares_to_trade - (-350.0)) < 1e-9


def test_offsetting_positions_can_cancel_out_below_threshold() -> None:
    company_repo = _company_repo("AAPL")
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Hedged")
    AddHoldingUseCase(portfolio_repo, company_repo).execute(
        portfolio.portfolio_id, "AAPL", shares=100, cost_basis_per_share=140.0
    )
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "put", 2, 4.00
    )
    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "put")
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "put"): _quote(contract, -0.5)}
    )

    plan = SuggestHedgingUseCase(portfolio_repo, options_provider).execute(portfolio.portfolio_id)

    assert plan.suggestions == []


def test_exposure_below_threshold_is_not_suggested() -> None:
    company_repo = _company_repo("AAPL")
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Tiny")
    AddHoldingUseCase(portfolio_repo, company_repo).execute(
        portfolio.portfolio_id, "AAPL", shares=5, cost_basis_per_share=140.0
    )

    plan = SuggestHedgingUseCase(portfolio_repo, FakeOptionsDataProvider({})).execute(
        portfolio.portfolio_id
    )

    assert plan.suggestions == []


def test_missing_option_quote_excludes_that_contract_but_others_still_process() -> None:
    company_repo = _company_repo("AAPL", "MSFT")
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Test")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 3.20
    )
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "MSFT", 300.0, date(2026, 12, 18), "call", 3, 5.00
    )
    msft_contract = OptionContract("MSFT", 300.0, date(2026, 12, 18), "call")
    options_provider = FakeOptionsDataProvider(
        {("MSFT", 300.0, date(2026, 12, 18), "call"): _quote(msft_contract, 0.4)}
    )

    plan = SuggestHedgingUseCase(portfolio_repo, options_provider).execute(portfolio.portfolio_id)

    assert len(plan.positions_excluded) == 1
    assert len(plan.suggestions) == 1
    assert plan.suggestions[0].underlying_ticker == "MSFT"
