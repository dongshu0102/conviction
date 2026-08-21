from dataclasses import dataclass

from src.application.use_cases.sync_filled_order_to_portfolio import SyncFilledOrderError
from src.application.use_cases.sync_multiple_filled_orders import SyncMultipleFilledOrdersUseCase
from src.domain.entities.portfolio import PortfolioHolding


@dataclass(frozen=True, slots=True)
class _FakeHistoryEntry:
    order_id: str
    ticker: str
    side: str


@dataclass(frozen=True, slots=True)
class _FakeHistoryResult:
    entries: tuple


class FakeGetOrderHistoryUseCase:
    def __init__(self, entries):
        self._entries = entries

    def execute(self, limit=50):
        return _FakeHistoryResult(entries=tuple(self._entries))


class FakeSyncFilledOrderUseCase:
    """Maps order_id -> either a PortfolioHolding (success), None
    (a genuine, successful full-close sell), or a raised
    SyncFilledOrderError (a real, honest failure)."""

    def __init__(self, results: dict):
        self._results = results
        self.calls = []

    def execute(self, order_id, ticker, side, user_id, provider_name, portfolio_id=None):
        self.calls.append(order_id)
        outcome = self._results[order_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_all_orders_succeed() -> None:
    history = FakeGetOrderHistoryUseCase([
        _FakeHistoryEntry("O1", "AAPL", "buy"),
        _FakeHistoryEntry("O2", "MSFT", "buy"),
    ])
    sync = FakeSyncFilledOrderUseCase({
        "O1": PortfolioHolding(ticker="AAPL", shares=1.0, cost_basis_per_share=150.0),
        "O2": PortfolioHolding(ticker="MSFT", shares=2.0, cost_basis_per_share=300.0),
    })
    use_case = SyncMultipleFilledOrdersUseCase(history, sync)

    results = use_case.execute(["O1", "O2"], user_id="U1", provider_name="alpaca")

    assert all(r.succeeded for r in results)
    assert results[0].holding.ticker == "AAPL"
    assert results[1].holding.ticker == "MSFT"
    assert sync.calls == ["O1", "O2"]


def test_one_orders_real_failure_does_not_abort_the_rest_of_the_batch() -> None:
    history = FakeGetOrderHistoryUseCase([
        _FakeHistoryEntry("O1", "AAPL", "sell"),
        _FakeHistoryEntry("O2", "MSFT", "buy"),
    ])
    sync = FakeSyncFilledOrderUseCase({
        "O1": SyncFilledOrderError("sold more shares than held"),
        "O2": PortfolioHolding(ticker="MSFT", shares=2.0, cost_basis_per_share=300.0),
    })
    use_case = SyncMultipleFilledOrdersUseCase(history, sync)

    results = use_case.execute(["O1", "O2"], user_id="U1", provider_name="alpaca")

    assert results[0].succeeded is False
    assert "sold more shares than held" in results[0].error
    assert results[1].succeeded is True  # the second order still, genuinely processed
    assert sync.calls == ["O1", "O2"]  # both were genuinely attempted, not stopped after the first failure


def test_an_order_id_not_found_in_history_is_reported_honestly() -> None:
    history = FakeGetOrderHistoryUseCase([_FakeHistoryEntry("O1", "AAPL", "buy")])
    sync = FakeSyncFilledOrderUseCase({"O1": PortfolioHolding(ticker="AAPL", shares=1.0, cost_basis_per_share=150.0)})
    use_case = SyncMultipleFilledOrdersUseCase(history, sync)

    results = use_case.execute(["O1", "MISSING"], user_id="U1", provider_name="alpaca")

    assert results[0].succeeded is True
    assert results[1].succeeded is False
    assert "not found in recent order history" in results[1].error
    assert sync.calls == ["O1"]  # the missing order was never even attempted against sync


def test_a_genuine_full_close_sell_reports_position_closed_as_a_real_success() -> None:
    history = FakeGetOrderHistoryUseCase([_FakeHistoryEntry("O1", "AAPL", "sell")])
    sync = FakeSyncFilledOrderUseCase({"O1": None})  # a genuine full-close returns None, not an error
    use_case = SyncMultipleFilledOrdersUseCase(history, sync)

    results = use_case.execute(["O1"], user_id="U1", provider_name="alpaca")

    assert results[0].succeeded is True
    assert results[0].holding is None
    assert results[0].position_closed is True
