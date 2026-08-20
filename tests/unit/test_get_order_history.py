import pytest

from src.application.interfaces.brokerage_provider import BrokerageProviderError
from src.application.use_cases.get_order_history import GetOrderHistoryError, GetOrderHistoryUseCase
from src.domain.entities.brokerage import OrderHistoryEntry


class FakeBrokerageProvider:
    def __init__(self, entries: list[OrderHistoryEntry] | None = None, raise_error=None):
        self._entries = entries if entries is not None else [
            OrderHistoryEntry(
                order_id="ORD-1", ticker="AAPL", side="buy", quantity=1.0, order_type="market",
                status="filled", filled_quantity=1.0, filled_avg_price=150.25, submitted_at="2026-08-20T13:30:00Z",
            ),
        ]
        self._raise_error = raise_error
        self.get_order_history_calls = []

    def get_order_history(self, limit=50):
        self.get_order_history_calls.append(limit)
        if self._raise_error is not None:
            raise self._raise_error
        return self._entries

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

    def get_order_status(self, order_id):
        raise NotImplementedError

    def cancel_order(self, order_id):
        raise NotImplementedError


def test_execute_returns_the_real_history_from_the_provider() -> None:
    provider = FakeBrokerageProvider()
    use_case = GetOrderHistoryUseCase(provider)

    result = use_case.execute()

    assert len(result.entries) == 1
    assert result.entries[0].order_id == "ORD-1"
    assert result.entries[0].ticker == "AAPL"
    assert provider.get_order_history_calls == [50]


def test_execute_passes_through_a_real_custom_limit() -> None:
    provider = FakeBrokerageProvider()
    use_case = GetOrderHistoryUseCase(provider)

    use_case.execute(limit=10)

    assert provider.get_order_history_calls == [10]


def test_execute_returns_an_honest_empty_result_for_a_genuinely_empty_history() -> None:
    provider = FakeBrokerageProvider(entries=[])
    use_case = GetOrderHistoryUseCase(provider)

    result = use_case.execute()

    assert result.entries == ()


def test_execute_surfaces_a_provider_error_as_get_order_history_error() -> None:
    provider = FakeBrokerageProvider(raise_error=BrokerageProviderError("IBKR request failed: network is down"))
    use_case = GetOrderHistoryUseCase(provider)

    with pytest.raises(GetOrderHistoryError) as exc_info:
        use_case.execute()
    assert "network is down" in str(exc_info.value)
