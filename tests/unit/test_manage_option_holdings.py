from __future__ import annotations

from datetime import date

from src.application.use_cases.manage_option_holdings import (
    AddOptionHoldingUseCase,
    InvalidOptionTypeError,
    RemoveOptionHoldingUseCase,
)
from src.application.use_cases.manage_portfolio import CreatePortfolioUseCase, PortfolioNotFoundError
from tests.unit.fakes import FakePortfolioRepository


def test_add_option_holding_persists_correctly() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options Test")

    use_case = AddOptionHoldingUseCase(portfolio_repo)
    holding = use_case.execute(
        portfolio.portfolio_id,
        underlying_ticker="aapl",  # lowercase — should be normalized
        strike=150.0,
        expiration=date(2026, 12, 18),
        option_type="CALL",  # uppercase — should be normalized
        contracts_held=5,
        cost_basis_per_contract=320.0,
    )

    assert holding.contract.underlying_ticker == "AAPL"
    assert holding.contract.option_type == "call"
    assert holding.contracts_held == 5

    stored = portfolio_repo.get_by_id(portfolio.portfolio_id)
    assert len(stored.option_holdings) == 1
    assert stored.option_holdings[0].contract.strike == 150.0


def test_add_option_holding_raises_for_missing_portfolio() -> None:
    portfolio_repo = FakePortfolioRepository()
    use_case = AddOptionHoldingUseCase(portfolio_repo)

    try:
        use_case.execute("nonexistent", "AAPL", 150.0, date(2026, 12, 18), "call", 5, 320.0)
        assert False, "expected PortfolioNotFoundError"
    except PortfolioNotFoundError:
        pass


def test_add_option_holding_rejects_invalid_option_type() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Test")
    use_case = AddOptionHoldingUseCase(portfolio_repo)

    try:
        use_case.execute(
            portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "straddle", 5, 320.0
        )
        assert False, "expected InvalidOptionTypeError"
    except InvalidOptionTypeError:
        pass


def test_upsert_replaces_existing_position_for_same_contract() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Test")
    use_case = AddOptionHoldingUseCase(portfolio_repo)

    use_case.execute(portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 320.0)
    use_case.execute(portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 10, 350.0)

    stored = portfolio_repo.get_by_id(portfolio.portfolio_id)
    assert len(stored.option_holdings) == 1
    assert stored.option_holdings[0].contracts_held == 10
    assert stored.option_holdings[0].cost_basis_per_contract == 350.0


def test_different_strike_is_a_different_position() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Test")
    use_case = AddOptionHoldingUseCase(portfolio_repo)

    use_case.execute(portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 320.0)
    use_case.execute(portfolio.portfolio_id, "AAPL", 160.0, date(2026, 12, 18), "call", 3, 280.0)

    stored = portfolio_repo.get_by_id(portfolio.portfolio_id)
    assert len(stored.option_holdings) == 2


def test_remove_option_holding_returns_false_when_not_present() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Test")
    use_case = RemoveOptionHoldingUseCase(portfolio_repo)

    removed = use_case.execute(portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call")

    assert removed is False


def test_remove_option_holding_actually_removes_it() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Test")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 320.0
    )

    removed = RemoveOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call"
    )

    assert removed is True
    stored = portfolio_repo.get_by_id(portfolio.portfolio_id)
    assert stored.option_holdings == []
