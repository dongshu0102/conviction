import pytest

from src.application.interfaces.brokerage_provider import BrokerageProviderError
from src.application.use_cases.get_order_status import GetOrderStatusError, GetOrderStatusUseCase
from src.domain.entities.brokerage import OrderStatus


class FakeBrokerageProvider:
    def __init__(self, order_status: OrderStatus | None = None, raise_error=None):
        self._order_status = order_status or OrderStatus(
            order_id="ORD-1", status="filled", filled_quantity=1.0, filled_avg_price=150.25,
        )
        self._raise_error = raise_error
        self.get_order_status_calls = []

    def get_order_status(self, order_id):
        self.get_order_status_calls.append(order_id)
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


def test_execute_returns_the_real_status_from_the_provider() -> None:
    provider = FakeBrokerageProvider(order_status=OrderStatus(
        order_id="ORD-42", status="filled", filled_quantity=1.0, filled_avg_price=150.25,
    ))
    use_case = GetOrderStatusUseCase(provider)

    result = use_case.execute("ORD-42")

    assert result.order_id == "ORD-42"
    assert result.status == "filled"
    assert result.filled_quantity == 1.0
    assert result.filled_avg_price == 150.25
    assert provider.get_order_status_calls == ["ORD-42"]


def test_execute_reports_a_genuinely_unfilled_order_honestly() -> None:
    """An order submitted outside market hours, or otherwise not yet
    processed, has a real, honest filled_avg_price of None -- never a
    fabricated 0.0 that could be misread as a real fill at $0."""
    provider = FakeBrokerageProvider(order_status=OrderStatus(
        order_id="ORD-99", status="new", filled_quantity=0.0, filled_avg_price=None,
    ))
    use_case = GetOrderStatusUseCase(provider)

    result = use_case.execute("ORD-99")

    assert result.status == "new"
    assert result.filled_quantity == 0.0
    assert result.filled_avg_price is None


def test_execute_surfaces_a_provider_error_as_get_order_status_error() -> None:
    provider = FakeBrokerageProvider(raise_error=BrokerageProviderError("Alpaca request failed: network is down"))
    use_case = GetOrderStatusUseCase(provider)

    with pytest.raises(GetOrderStatusError) as exc_info:
        use_case.execute("ORD-1")
    assert "network is down" in str(exc_info.value)
