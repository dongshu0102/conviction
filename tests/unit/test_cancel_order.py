import pytest

from src.application.interfaces.brokerage_provider import BrokerageProviderError
from src.application.use_cases.cancel_order import CancelOrderError, CancelOrderUseCase
from src.domain.entities.brokerage import CancelOrderResult


class FakeBrokerageProvider:
    def __init__(self, cancel_result: CancelOrderResult | None = None, raise_error=None):
        self._cancel_result = cancel_result or CancelOrderResult(success=True)
        self._raise_error = raise_error
        self.cancel_order_calls = []

    def cancel_order(self, order_id):
        self.cancel_order_calls.append(order_id)
        if self._raise_error is not None:
            raise self._raise_error
        return self._cancel_result

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


def test_execute_returns_a_genuine_success() -> None:
    provider = FakeBrokerageProvider(cancel_result=CancelOrderResult(success=True))
    use_case = CancelOrderUseCase(provider)

    result = use_case.execute("ORD-1")

    assert result.success is True
    assert result.reason is None
    assert provider.cancel_order_calls == ["ORD-1"]


def test_execute_reports_a_genuine_no_longer_cancelable_outcome_honestly() -> None:
    """An order that's already filled genuinely cannot be canceled at
    any real brokerage -- this must come back as an honest
    success=False with a real reason, not raise as if this app itself
    failed."""
    provider = FakeBrokerageProvider(cancel_result=CancelOrderResult(
        success=False, reason="Order is no longer cancelable (e.g. already filled).",
    ))
    use_case = CancelOrderUseCase(provider)

    result = use_case.execute("ORD-2")

    assert result.success is False
    assert "no longer cancelable" in result.reason


def test_execute_surfaces_a_provider_error_as_cancel_order_error() -> None:
    """Distinct from a genuine success=False outcome: this is for when
    the cancellation attempt couldn't even be made at all (e.g. a real
    network failure), not a valid, honest "already filled" case."""
    provider = FakeBrokerageProvider(raise_error=BrokerageProviderError("Tradier request failed: network is down"))
    use_case = CancelOrderUseCase(provider)

    with pytest.raises(CancelOrderError) as exc_info:
        use_case.execute("ORD-1")
    assert "network is down" in str(exc_info.value)
