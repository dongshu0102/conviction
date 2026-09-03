from __future__ import annotations

import pytest
from datetime import date

from src.application.use_cases.manage_bond_holdings import (
    AddBondHoldingUseCase,
    RemoveBondHoldingUseCase,
)
from src.application.use_cases.manage_portfolio import CreatePortfolioUseCase, PortfolioNotFoundError
from tests.unit.fakes import FakePortfolioRepository


def test_add_bond_holding_persists_correctly() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Bonds Test")

    use_case = AddBondHoldingUseCase(portfolio_repo)
    holding = use_case.execute(
        portfolio.portfolio_id,
        issuer_name="Apple Inc.",
        coupon_rate=0.045,
        maturity_date=date(2033, 5, 1),
        quantity=10,
        cost_basis_price=98.5,
        cusip="037833dt4",  # lowercase — should be normalized
    )

    assert holding.bond.issuer_name == "Apple Inc."
    assert holding.bond.cusip == "037833DT4"
    assert holding.quantity == 10

    stored = portfolio_repo.get_by_id(portfolio.portfolio_id)
    assert len(stored.bond_holdings) == 1
    assert stored.bond_holdings[0].cost_basis_price == 98.5


def test_add_bond_holding_raises_for_missing_portfolio() -> None:
    portfolio_repo = FakePortfolioRepository()
    use_case = AddBondHoldingUseCase(portfolio_repo)

    with pytest.raises(PortfolioNotFoundError):
        use_case.execute("nonexistent", "Apple Inc.", 0.045, date(2033, 5, 1), 10, 98.5)


def test_add_bond_holding_defaults_face_value_to_1000() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Bonds Test")
    use_case = AddBondHoldingUseCase(portfolio_repo)

    holding = use_case.execute(
        portfolio.portfolio_id, "Apple Inc.", 0.045, date(2033, 5, 1), 10, 98.5,
    )

    assert holding.bond.face_value == 1000.0


def test_adding_the_same_bond_again_updates_the_existing_position_not_a_new_one() -> None:
    """Same 'state, not a transaction log' principle already
    established for equities and options."""
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Bonds Test")
    use_case = AddBondHoldingUseCase(portfolio_repo)

    use_case.execute(portfolio.portfolio_id, "Apple Inc.", 0.045, date(2033, 5, 1), 10, 98.5)
    use_case.execute(portfolio.portfolio_id, "Apple Inc.", 0.045, date(2033, 5, 1), 20, 99.0)

    stored = portfolio_repo.get_by_id(portfolio.portfolio_id)
    assert len(stored.bond_holdings) == 1  # never a second, duplicate row for the same bond
    assert stored.bond_holdings[0].quantity == 20
    assert stored.bond_holdings[0].cost_basis_price == 99.0


def test_different_maturity_dates_are_genuinely_different_bonds() -> None:
    """Same issuer, same coupon, different maturity -- a genuinely
    different, real bond, not the same position."""
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Bonds Test")
    use_case = AddBondHoldingUseCase(portfolio_repo)

    use_case.execute(portfolio.portfolio_id, "Apple Inc.", 0.045, date(2033, 5, 1), 10, 98.5)
    use_case.execute(portfolio.portfolio_id, "Apple Inc.", 0.045, date(2028, 5, 1), 5, 101.0)

    stored = portfolio_repo.get_by_id(portfolio.portfolio_id)
    assert len(stored.bond_holdings) == 2


def test_remove_bond_holding_removes_the_real_position() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Bonds Test")
    AddBondHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "Apple Inc.", 0.045, date(2033, 5, 1), 10, 98.5,
    )

    removed = RemoveBondHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "Apple Inc.", 0.045, date(2033, 5, 1),
    )

    assert removed is True
    stored = portfolio_repo.get_by_id(portfolio.portfolio_id)
    assert stored.bond_holdings == []


def test_remove_bond_holding_returns_false_for_a_genuinely_nonexistent_holding() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Bonds Test")

    removed = RemoveBondHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "Nonexistent Corp", 0.05, date(2030, 1, 1),
    )

    assert removed is False
