from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.compute_portfolio_greeks import ComputePortfolioGreeksUseCase
from src.application.use_cases.manage_option_holdings import AddOptionHoldingUseCase
from src.application.use_cases.manage_portfolio import CreatePortfolioUseCase
from src.domain.entities.option import OptionContract, OptionQuote
from tests.unit.fakes import FakeOptionsDataProvider, FakePortfolioRepository


def _quote(contract: OptionContract, delta, gamma, theta, vega) -> OptionQuote:
    return OptionQuote(
        contract=contract, bid=1.0, ask=1.1, last=1.05, implied_volatility=0.3,
        open_interest=100, volume=10, delta=delta, gamma=gamma, theta=theta, vega=vega,
        underlying_price=150.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_aggregates_greeks_with_correct_contract_multiplier() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 320.0
    )

    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "call"): _quote(contract, 0.5, 0.02, -0.03, 0.15)}
    )

    result = ComputePortfolioGreeksUseCase(portfolio_repo, options_provider).execute(
        portfolio.portfolio_id
    )

    assert result.positions_included == 1
    assert result.positions_excluded == []
    assert abs(result.total_delta - 250.0) < 1e-9   # 0.5 * 5 * 100
    assert abs(result.total_gamma - 10.0) < 1e-9     # 0.02 * 5 * 100
    assert abs(result.total_theta - (-15.0)) < 1e-9  # -0.03 * 5 * 100
    assert abs(result.total_vega - 75.0) < 1e-9      # 0.15 * 5 * 100


def test_short_position_contributes_negative_weight() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", -3, 320.0
    )

    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "call"): _quote(contract, 0.5, 0.02, -0.03, 0.15)}
    )

    result = ComputePortfolioGreeksUseCase(portfolio_repo, options_provider).execute(
        portfolio.portfolio_id
    )

    assert abs(result.total_delta - (-150.0)) < 1e-9


def test_missing_greek_excludes_whole_position_not_zeroed() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 320.0
    )

    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    incomplete_quote = _quote(contract, 0.5, None, -0.03, 0.15)  # gamma missing
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "call"): incomplete_quote}
    )

    result = ComputePortfolioGreeksUseCase(portfolio_repo, options_provider).execute(
        portfolio.portfolio_id
    )

    assert result.positions_included == 0
    assert len(result.positions_excluded) == 1
    assert result.total_delta == 0.0  # not 250 — the position was fully excluded


def test_no_live_quote_available_excludes_position() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 320.0
    )
    options_provider = FakeOptionsDataProvider({})  # no quotes available at all

    result = ComputePortfolioGreeksUseCase(portfolio_repo, options_provider).execute(
        portfolio.portfolio_id
    )

    assert result.positions_included == 0
    assert len(result.positions_excluded) == 1


def test_multiple_positions_sum_correctly() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 320.0
    )
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 160.0, date(2026, 12, 18), "call", 2, 280.0
    )

    c1 = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    c2 = OptionContract("AAPL", 160.0, date(2026, 12, 18), "call")
    options_provider = FakeOptionsDataProvider({
        ("AAPL", 150.0, date(2026, 12, 18), "call"): _quote(c1, 0.5, 0.02, -0.03, 0.15),
        ("AAPL", 160.0, date(2026, 12, 18), "call"): _quote(c2, 0.3, 0.015, -0.02, 0.10),
    })

    result = ComputePortfolioGreeksUseCase(portfolio_repo, options_provider).execute(
        portfolio.portfolio_id
    )

    assert result.positions_included == 2
    assert abs(result.total_delta - 310.0) < 1e-9
