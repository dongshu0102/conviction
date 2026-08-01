from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.compute_option_portfolio_valuation import (
    ComputeOptionPortfolioValuationUseCase,
)
from src.application.use_cases.manage_option_holdings import AddOptionHoldingUseCase
from src.application.use_cases.manage_portfolio import CreatePortfolioUseCase
from src.domain.entities.option import OptionContract, OptionQuote
from tests.unit.fakes import FakeOptionsDataProvider, FakePortfolioRepository


def _quote(contract: OptionContract, mid=None, last=None) -> OptionQuote:
    return OptionQuote(
        contract=contract, bid=mid, ask=mid, last=last, implied_volatility=0.3,
        open_interest=100, volume=10, delta=0.5, gamma=0.02, theta=-0.03, vega=0.15,
        underlying_price=150.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc), mid=mid,
    )


def test_uses_mid_price_and_computes_exact_pnl() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 3.20
    )
    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "call"): _quote(contract, mid=4.50, last=4.45)}
    )

    result = ComputeOptionPortfolioValuationUseCase(portfolio_repo, options_provider).execute(
        portfolio.portfolio_id
    )

    assert len(result.positions) == 1
    position = result.positions[0]
    assert position.current_price == 4.50  # used mid, not last
    assert abs(position.market_value - 2250.0) < 1e-9
    assert abs(position.cost_basis_total - 1600.0) < 1e-9
    assert abs(position.unrealized_gain - 650.0) < 1e-9
    assert abs(position.unrealized_gain_pct - 0.40625) < 1e-9
    assert abs(result.total_market_value - 2250.0) < 1e-9


def test_falls_back_to_last_when_mid_unavailable() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 3.20
    )
    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "call"): _quote(contract, mid=None, last=4.45)}
    )

    result = ComputeOptionPortfolioValuationUseCase(portfolio_repo, options_provider).execute(
        portfolio.portfolio_id
    )

    assert result.positions[0].current_price == 4.45


def test_short_position_pnl_computed_correctly() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", -3, 5.00
    )
    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "call"): _quote(contract, mid=3.00, last=3.00)}
    )

    result = ComputeOptionPortfolioValuationUseCase(portfolio_repo, options_provider).execute(
        portfolio.portfolio_id
    )

    position = result.positions[0]
    assert abs(position.market_value - (-900.0)) < 1e-9
    assert abs(position.cost_basis_total - (-1500.0)) < 1e-9
    assert abs(position.unrealized_gain - 600.0) < 1e-9  # correctly a GAIN despite negative values


def test_no_quote_available_excludes_position() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 3.20
    )
    options_provider = FakeOptionsDataProvider({})

    result = ComputeOptionPortfolioValuationUseCase(portfolio_repo, options_provider).execute(
        portfolio.portfolio_id
    )

    assert result.positions == []
    assert len(result.positions_excluded) == 1
    assert result.total_market_value == 0.0


def test_neither_mid_nor_last_available_excludes_position() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 3.20
    )
    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "call"): _quote(contract, mid=None, last=None)}
    )

    result = ComputeOptionPortfolioValuationUseCase(portfolio_repo, options_provider).execute(
        portfolio.portfolio_id
    )

    assert result.positions == []
    assert len(result.positions_excluded) == 1
