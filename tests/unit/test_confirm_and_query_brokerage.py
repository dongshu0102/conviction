from src.application.interfaces.brokerage_provider import BrokerageProviderError
from src.application.use_cases.confirm_order import ConfirmOrderError, ConfirmOrderUseCase
from src.application.use_cases.get_brokerage_account_summary import (
    GetBrokerageAccountSummaryError,
    GetBrokerageAccountSummaryUseCase,
)
from src.application.use_cases.get_brokerage_positions import (
    GetBrokeragePositionsError,
    GetBrokeragePositionsUseCase,
)
from src.domain.entities.brokerage import BrokerageAccountSummary, BrokeragePosition, OrderResult


class FakeConfirmProvider:
    def __init__(self, result=None, raise_error=None):
        self._result = result or OrderResult(status="submitted", order_id="123")
        self._raise_error = raise_error
        self.confirm_order_calls = []

    def confirm_order(self, reply_id):
        self.confirm_order_calls.append(reply_id)
        if self._raise_error is not None:
            raise self._raise_error
        return self._result


class FakeAccountProvider:
    def __init__(self, summary=None, raise_error=None):
        self._summary = summary
        self._raise_error = raise_error

    def get_account_summary(self):
        if self._raise_error is not None:
            raise self._raise_error
        return self._summary


class FakePositionsProvider:
    def __init__(self, positions=None, raise_error=None):
        self._positions = positions or []
        self._raise_error = raise_error

    def get_positions(self):
        if self._raise_error is not None:
            raise self._raise_error
        return self._positions


def test_confirm_order_passes_the_reply_id_through_and_returns_the_result() -> None:
    provider = FakeConfirmProvider(result=OrderResult(status="submitted", order_id="ORD-2"))
    use_case = ConfirmOrderUseCase(provider)

    result = use_case.execute("reply-xyz")

    assert result.status == "submitted"
    assert result.order_id == "ORD-2"
    assert provider.confirm_order_calls == ["reply-xyz"]


def test_confirm_order_wraps_a_provider_error() -> None:
    provider = FakeConfirmProvider(raise_error=BrokerageProviderError("timeout"))
    use_case = ConfirmOrderUseCase(provider)

    try:
        use_case.execute("reply-xyz")
        assert False, "expected ConfirmOrderError"
    except ConfirmOrderError as exc:
        assert "timeout" in str(exc)


def test_get_account_summary_returns_the_real_summary() -> None:
    summary = BrokerageAccountSummary(account_id="DU123456", cash=10000.0, buying_power=20000.0, equity=15000.0, currency="USD")
    provider = FakeAccountProvider(summary=summary)
    use_case = GetBrokerageAccountSummaryUseCase(provider)

    result = use_case.execute()

    assert result.account_id == "DU123456"
    assert result.buying_power == 20000.0


def test_get_account_summary_wraps_a_provider_error() -> None:
    provider = FakeAccountProvider(raise_error=BrokerageProviderError("not authenticated"))
    use_case = GetBrokerageAccountSummaryUseCase(provider)

    try:
        use_case.execute()
        assert False, "expected GetBrokerageAccountSummaryError"
    except GetBrokerageAccountSummaryError as exc:
        assert "not authenticated" in str(exc)


def test_get_positions_returns_every_position() -> None:
    positions = [
        BrokeragePosition(ticker="AAPL", quantity=10, average_cost=150.0, market_value=1600.0, unrealized_pnl=100.0),
        BrokeragePosition(ticker="MSFT", quantity=5, average_cost=300.0, market_value=1550.0, unrealized_pnl=50.0),
    ]
    provider = FakePositionsProvider(positions=positions)
    use_case = GetBrokeragePositionsUseCase(provider)

    result = use_case.execute()

    assert len(result.positions) == 2
    assert result.positions[0].ticker == "AAPL"


def test_get_positions_returns_an_honest_empty_tuple_when_none_exist() -> None:
    provider = FakePositionsProvider(positions=[])
    use_case = GetBrokeragePositionsUseCase(provider)

    result = use_case.execute()

    assert result.positions == ()


def test_get_positions_wraps_a_provider_error() -> None:
    provider = FakePositionsProvider(raise_error=BrokerageProviderError("session expired"))
    use_case = GetBrokeragePositionsUseCase(provider)

    try:
        use_case.execute()
        assert False, "expected GetBrokeragePositionsError"
    except GetBrokeragePositionsError as exc:
        assert "session expired" in str(exc)
