from __future__ import annotations

import pytest
from datetime import date

from src.application.use_cases.compute_bond_portfolio_valuation import (
    ComputeBondPortfolioValuationUseCase,
)
from src.application.use_cases.manage_bond_holdings import AddBondHoldingUseCase
from src.application.use_cases.manage_portfolio import CreatePortfolioUseCase, PortfolioNotFoundError
from tests.unit.fakes import FakePortfolioRepository


def test_raises_when_portfolio_does_not_exist() -> None:
    portfolio_repo = FakePortfolioRepository()
    use_case = ComputeBondPortfolioValuationUseCase(portfolio_repo)

    with pytest.raises(PortfolioNotFoundError):
        use_case.execute("nonexistent")


def test_empty_portfolio_returns_a_genuinely_empty_valuation() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Bonds Test")
    use_case = ComputeBondPortfolioValuationUseCase(portfolio_repo)

    result = use_case.execute(portfolio.portfolio_id)

    assert result.positions == []
    assert result.total_face_value == 0.0
    assert result.total_cost_basis == 0.0


def test_computes_real_yield_analytics_for_a_par_bond() -> None:
    """A bond bought exactly at par (100) with coupon=YTM (a real,
    well-known bond-math identity) should have both current_yield and
    yield_to_maturity equal to the coupon rate."""
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Bonds Test")
    AddBondHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "Apple Inc.", coupon_rate=0.05,
        maturity_date=date(2036, 1, 1), quantity=10, cost_basis_price=100.0,
    )
    use_case = ComputeBondPortfolioValuationUseCase(portfolio_repo)

    result = use_case.execute(portfolio.portfolio_id, as_of_date=date(2026, 1, 1))

    assert len(result.positions) == 1
    position = result.positions[0]
    assert round(position.current_yield, 4) == 0.0500
    assert position.yield_to_maturity is not None
    assert round(position.yield_to_maturity, 3) == 0.050


def test_computes_real_total_face_value_and_cost_basis_across_multiple_holdings() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Bonds Test")
    add = AddBondHoldingUseCase(portfolio_repo)
    add.execute(portfolio.portfolio_id, "Apple Inc.", 0.05, date(2036, 1, 1), 10, 100.0)  # 10 * $1000 = $10,000 face
    add.execute(portfolio.portfolio_id, "Microsoft Corp.", 0.04, date(2031, 1, 1), 5, 95.0)  # 5 * $1000 * 0.95 = $4,750 cost

    use_case = ComputeBondPortfolioValuationUseCase(portfolio_repo)
    result = use_case.execute(portfolio.portfolio_id, as_of_date=date(2026, 1, 1))

    assert result.total_face_value == 15_000.0  # 10,000 + 5,000
    assert result.total_cost_basis == 14_750.0  # 10,000 (at par) + 4,750 (at 95% of face)


def test_current_price_is_the_honest_cost_basis_estimate_never_a_fabricated_live_quote() -> None:
    """No live bond price source exists in this app -- current_price
    must always, honestly reflect that by using the real cost basis,
    never something that looks like a live market quote."""
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Bonds Test")
    AddBondHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "Apple Inc.", 0.05, date(2036, 1, 1), 10, 97.25,
    )

    result = ComputeBondPortfolioValuationUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, as_of_date=date(2026, 1, 1),
    )

    assert result.positions[0].current_price == 97.25
