from datetime import datetime, timezone

import pytest

from src.application.use_cases.manage_portfolio import (
    AddHoldingUseCase,
    CreatePortfolioUseCase,
    PortfolioNotFoundError,
)
from src.application.use_cases.sync_filled_order_to_portfolio import (
    OrderAlreadySyncedError,
    OrderNotFilledError,
    SyncFilledOrderError,
    SyncFilledOrderToPortfolioUseCase,
    UnrecognizedProviderError,
)
from src.domain.entities.company import Company, Sector
from src.domain.entities.portfolio import Portfolio, PortfolioHolding
from src.domain.entities.brokerage import OrderStatus
from tests.unit.fakes import FakeCompanyRepository, FakePortfolioRepository, FakeSyncedOrderRepository


class FakeBrokerageProvider:
    def __init__(self, order_status: OrderStatus, raise_error=None):
        self._order_status = order_status
        self._raise_error = raise_error

    def get_order_status(self, order_id):
        if self._raise_error is not None:
            raise self._raise_error
        return self._order_status

    def place_order(self, request):
        raise NotImplementedError

    def resolve_ticker_to_contract_id(self, ticker):
        raise NotImplementedError

    def confirm_order(self, reply_id):
        raise NotImplementedError

    def get_account_summary(self):
        raise NotImplementedError

    def get_positions(self):
        raise NotImplementedError

    def cancel_order(self, order_id):
        raise NotImplementedError

    def get_order_history(self, limit=50):
        raise NotImplementedError


def _portfolio(portfolio_id="P1", holdings=None) -> Portfolio:
    return Portfolio(
        portfolio_id=portfolio_id, user_id="U1", name="Test", created_at=datetime.now(timezone.utc),
        holdings=holdings or [],
    )


def _build(order_status, portfolio=None, raise_error=None):
    company_repo = FakeCompanyRepository()
    company_repo.save(Company(ticker="AAPL", name="Apple", sector=Sector.TECHNOLOGY, industry="Tech",
                               exchange="NASDAQ", country="US"))
    portfolio_repo = FakePortfolioRepository()
    portfolio_repo.create(portfolio or _portfolio())
    provider = FakeBrokerageProvider(order_status, raise_error=raise_error)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    create_portfolio = CreatePortfolioUseCase(portfolio_repo)
    synced_order_repo = FakeSyncedOrderRepository()
    use_case = SyncFilledOrderToPortfolioUseCase(
        provider, portfolio_repo, add_holding, create_portfolio, synced_order_repo
    )
    return use_case, portfolio_repo, synced_order_repo


def test_buy_with_no_existing_holding_creates_a_new_one() -> None:
    order = OrderStatus(order_id="O1", status="filled", filled_quantity=10.0, filled_avg_price=150.0)
    use_case, portfolio_repo, synced_order_repo = _build(order)

    result = use_case.execute("O1", ticker="AAPL", side="buy", user_id="U1", provider_name="alpaca", portfolio_id="P1")

    assert result.shares == 10.0
    assert result.cost_basis_per_share == 150.0


def test_buy_adding_to_existing_holding_computes_a_real_weighted_average_cost_basis() -> None:
    """Hand-verified: 10 shares @ $100 existing + 10 shares @ $150 new
    = 20 shares @ a real, weighted $125 average, never a naive
    overwrite to just $150."""
    existing = PortfolioHolding(ticker="AAPL", shares=10.0, cost_basis_per_share=100.0)
    order = OrderStatus(order_id="O2", status="filled", filled_quantity=10.0, filled_avg_price=150.0)
    use_case, portfolio_repo, synced_order_repo = _build(order, portfolio=_portfolio(holdings=[existing]))

    result = use_case.execute("O2", ticker="AAPL", side="buy", user_id="U1", provider_name="alpaca", portfolio_id="P1")

    assert result.shares == 20.0
    assert result.cost_basis_per_share == 125.0


def test_sell_reduces_shares_and_keeps_the_existing_cost_basis() -> None:
    existing = PortfolioHolding(ticker="AAPL", shares=10.0, cost_basis_per_share=100.0)
    order = OrderStatus(order_id="O3", status="filled", filled_quantity=4.0, filled_avg_price=200.0)
    use_case, portfolio_repo, synced_order_repo = _build(order, portfolio=_portfolio(holdings=[existing]))

    result = use_case.execute("O3", ticker="AAPL", side="sell", user_id="U1", provider_name="alpaca", portfolio_id="P1")

    assert result.shares == 6.0
    assert result.cost_basis_per_share == 100.0  # unchanged by the sale price, standard partial-sale accounting


def test_sell_that_fully_closes_a_position_returns_none_and_removes_the_holding() -> None:
    existing = PortfolioHolding(ticker="AAPL", shares=10.0, cost_basis_per_share=100.0)
    order = OrderStatus(order_id="O4", status="filled", filled_quantity=10.0, filled_avg_price=200.0)
    use_case, portfolio_repo, synced_order_repo = _build(order, portfolio=_portfolio(holdings=[existing]))

    result = use_case.execute("O4", ticker="AAPL", side="sell", user_id="U1", provider_name="alpaca", portfolio_id="P1")

    assert result is None
    assert portfolio_repo.get_by_id("P1").holdings == []


def test_sell_exceeding_held_shares_raises_rather_than_going_negative() -> None:
    existing = PortfolioHolding(ticker="AAPL", shares=5.0, cost_basis_per_share=100.0)
    order = OrderStatus(order_id="O5", status="filled", filled_quantity=10.0, filled_avg_price=200.0)
    use_case, portfolio_repo, synced_order_repo = _build(order, portfolio=_portfolio(holdings=[existing]))

    with pytest.raises(SyncFilledOrderError):
        use_case.execute("O5", ticker="AAPL", side="sell", user_id="U1", provider_name="alpaca", portfolio_id="P1")

    # The existing holding must be genuinely untouched after a refused sync.
    assert portfolio_repo.get_by_id("P1").holdings[0].shares == 5.0


def test_a_genuinely_unfilled_order_raises_and_syncs_nothing() -> None:
    order = OrderStatus(order_id="O6", status="accepted", filled_quantity=0.0, filled_avg_price=None)
    use_case, portfolio_repo, synced_order_repo = _build(order)

    with pytest.raises(OrderNotFilledError):
        use_case.execute("O6", ticker="AAPL", side="buy", user_id="U1", provider_name="alpaca", portfolio_id="P1")

    assert portfolio_repo.get_by_id("P1").holdings == []


def test_a_missing_explicit_portfolio_raises_portfolio_not_found_error() -> None:
    order = OrderStatus(order_id="O7", status="filled", filled_quantity=1.0, filled_avg_price=150.0)
    use_case, _, _ = _build(order)

    with pytest.raises(PortfolioNotFoundError):
        use_case.execute("O7", ticker="AAPL", side="buy", user_id="U1", provider_name="alpaca", portfolio_id="NONEXISTENT")


def test_omitting_portfolio_id_auto_creates_a_dedicated_provider_portfolio() -> None:
    order = OrderStatus(order_id="O8", status="filled", filled_quantity=5.0, filled_avg_price=150.0)
    use_case, portfolio_repo, synced_order_repo = _build(order)

    result = use_case.execute("O8", ticker="AAPL", side="buy", user_id="U1", provider_name="alpaca")

    assert result.shares == 5.0
    portfolios = portfolio_repo.list_for_user("U1")
    names = [p.name for p in portfolios]
    assert "Alpaca (auto-synced)" in names


def test_omitting_portfolio_id_is_idempotent_and_reuses_the_same_dedicated_portfolio() -> None:
    """A second, separate sync for a DIFFERENT order (same user+provider)
    must land in the SAME dedicated portfolio, never create a second,
    duplicate one."""
    order1 = OrderStatus(order_id="O9", status="filled", filled_quantity=5.0, filled_avg_price=100.0)
    use_case, portfolio_repo, synced_order_repo = _build(order1)
    use_case.execute("O9", ticker="AAPL", side="buy", user_id="U1", provider_name="alpaca")

    order2 = OrderStatus(order_id="O10", status="filled", filled_quantity=5.0, filled_avg_price=200.0)
    use_case._provider = FakeBrokerageProvider(order2)
    result2 = use_case.execute("O10", ticker="AAPL", side="buy", user_id="U1", provider_name="alpaca")

    portfolios = portfolio_repo.list_for_user("U1")
    dedicated = [p for p in portfolios if p.name == "Alpaca (auto-synced)"]
    assert len(dedicated) == 1  # never a second, duplicate portfolio
    assert result2.shares == 10.0  # accumulated correctly within that one, shared dedicated portfolio


def test_different_providers_get_genuinely_separate_dedicated_portfolios() -> None:
    order = OrderStatus(order_id="O11", status="filled", filled_quantity=5.0, filled_avg_price=150.0)
    use_case, portfolio_repo, synced_order_repo = _build(order)
    use_case.execute("O11", ticker="AAPL", side="buy", user_id="U1", provider_name="alpaca")
    order_ibkr = OrderStatus(order_id="O11B", status="filled", filled_quantity=5.0, filled_avg_price=150.0)
    use_case._provider = FakeBrokerageProvider(order_ibkr)
    use_case.execute("O11B", ticker="AAPL", side="buy", user_id="U1", provider_name="ibkr")

    names = {p.name for p in portfolio_repo.list_for_user("U1")}
    assert "Alpaca (auto-synced)" in names
    assert "IBKR (auto-synced)" in names


def test_an_unrecognized_provider_name_is_refused_honestly() -> None:
    order = OrderStatus(order_id="O12", status="filled", filled_quantity=1.0, filled_avg_price=150.0)
    use_case, _, _ = _build(order)

    with pytest.raises(UnrecognizedProviderError):
        use_case.execute("O12", ticker="AAPL", side="buy", user_id="U1", provider_name="not_a_real_broker")


def test_a_real_double_sync_of_the_same_order_is_refused_not_double_counted() -> None:
    """The exact, real bug caught directly by the user tonight:
    calling execute() twice for the SAME order_id must never add the
    shares twice."""
    order = OrderStatus(order_id="O13", status="filled", filled_quantity=1.0, filled_avg_price=150.0)
    use_case, portfolio_repo, synced_order_repo = _build(order)

    first = use_case.execute("O13", ticker="AAPL", side="buy", user_id="U1", provider_name="alpaca", portfolio_id="P1")
    assert first.shares == 1.0

    with pytest.raises(OrderAlreadySyncedError):
        use_case.execute("O13", ticker="AAPL", side="buy", user_id="U1", provider_name="alpaca", portfolio_id="P1")

    # The real, definitive proof: the holding still shows exactly 1
    # share, not 2, after the refused, second sync attempt.
    assert portfolio_repo.get_by_id("P1").holdings[0].shares == 1.0


def test_a_successful_sync_is_genuinely_recorded() -> None:
    order = OrderStatus(order_id="O14", status="filled", filled_quantity=1.0, filled_avg_price=150.0)
    use_case, portfolio_repo, synced_order_repo = _build(order)

    use_case.execute("O14", ticker="AAPL", side="buy", user_id="U1", provider_name="alpaca", portfolio_id="P1")

    assert synced_order_repo.is_already_synced("O14") is True
    assert len(synced_order_repo.record_sync_calls) == 1


def test_a_genuine_full_close_sell_is_also_recorded_as_synced() -> None:
    """Even though a full-close sell returns None (no holding left to
    describe), the order itself genuinely was synced and must not be
    eligible for a second, duplicate sync attempt."""
    existing = PortfolioHolding(ticker="AAPL", shares=10.0, cost_basis_per_share=100.0)
    order = OrderStatus(order_id="O15", status="filled", filled_quantity=10.0, filled_avg_price=200.0)
    use_case, portfolio_repo, synced_order_repo = _build(order, portfolio=_portfolio(holdings=[existing]))

    result = use_case.execute("O15", ticker="AAPL", side="sell", user_id="U1", provider_name="alpaca", portfolio_id="P1")

    assert result is None
    assert synced_order_repo.is_already_synced("O15") is True


def test_a_failed_sync_attempt_is_never_recorded_as_synced() -> None:
    """A sell that's refused for exceeding held shares must NOT be
    recorded -- only a genuine, real success gets recorded, so a
    corrected, later retry of the same order_id can still succeed."""
    existing = PortfolioHolding(ticker="AAPL", shares=5.0, cost_basis_per_share=100.0)
    order = OrderStatus(order_id="O16", status="filled", filled_quantity=10.0, filled_avg_price=200.0)
    use_case, portfolio_repo, synced_order_repo = _build(order, portfolio=_portfolio(holdings=[existing]))

    with pytest.raises(SyncFilledOrderError):
        use_case.execute("O16", ticker="AAPL", side="sell", user_id="U1", provider_name="alpaca", portfolio_id="P1")

    assert synced_order_repo.is_already_synced("O16") is False
