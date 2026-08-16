from src.application.use_cases.place_order import (
    PlaceOrderError,
    PlaceOrderUseCase,
)
from src.domain.entities.brokerage import OrderRequest, OrderResult


class FakeBrokerageProvider:
    def __init__(self, order_result: OrderResult | None = None, raise_error=None):
        self._order_result = order_result or OrderResult(status="submitted", order_id="123")
        self._raise_error = raise_error
        self.place_order_calls = []

    def place_order(self, request):
        self.place_order_calls.append(request)
        if self._raise_error is not None:
            raise self._raise_error
        return self._order_result

    def resolve_ticker_to_contract_id(self, ticker):
        return "265598"

    def confirm_order(self, reply_id):
        raise NotImplementedError

    def get_account_summary(self):
        raise NotImplementedError

    def get_positions(self):
        raise NotImplementedError


def _market_buy(ticker="AAPL", quantity=10) -> OrderRequest:
    return OrderRequest(ticker=ticker, side="buy", quantity=quantity, order_type="market")


def test_execute_without_confirm_never_calls_the_provider() -> None:
    """The single most important safety test in this entire feature:
    a caller that forgets, or deliberately omits, confirm=True must
    never cause a real order to reach the brokerage."""
    provider = FakeBrokerageProvider()
    use_case = PlaceOrderUseCase(provider)

    result = use_case.execute(_market_buy())

    assert result.confirmed is False
    assert result.order_result is None
    assert provider.place_order_calls == [], "the provider must never be called without explicit confirm=True"


def test_execute_with_confirm_true_actually_calls_the_provider() -> None:
    provider = FakeBrokerageProvider(order_result=OrderResult(status="submitted", order_id="ORD-1"))
    use_case = PlaceOrderUseCase(provider)

    result = use_case.execute(_market_buy(), confirm=True)

    assert result.confirmed is True
    assert result.order_result.status == "submitted"
    assert result.order_result.order_id == "ORD-1"
    assert len(provider.place_order_calls) == 1


def test_execute_passes_through_a_needs_confirmation_result_honestly() -> None:
    """A real, confirmed IBKR scenario: the brokerage itself may still
    return needs_confirmation even after the use case's own confirm=True
    -- these are two genuinely different concepts (the caller's intent
    to place an order at all, vs. the brokerage's own warning about
    this specific order) and must not be conflated."""
    provider = FakeBrokerageProvider(order_result=OrderResult(
        status="needs_confirmation", reply_id="reply-abc",
        warning_messages=("price exceeds the 3% constraint",),
    ))
    use_case = PlaceOrderUseCase(provider)

    result = use_case.execute(_market_buy(), confirm=True)

    assert result.order_result.status == "needs_confirmation"
    assert result.order_result.reply_id == "reply-abc"


def test_execute_raises_for_an_unsupported_order_type() -> None:
    provider = FakeBrokerageProvider()
    use_case = PlaceOrderUseCase(provider)
    request = OrderRequest(ticker="AAPL", side="buy", quantity=10, order_type="stop")

    try:
        use_case.execute(request, confirm=True)
        assert False, "expected PlaceOrderError"
    except PlaceOrderError:
        pass
    assert provider.place_order_calls == [], "an invalid request must never reach the provider"


def test_execute_raises_for_a_limit_order_missing_a_limit_price() -> None:
    provider = FakeBrokerageProvider()
    use_case = PlaceOrderUseCase(provider)
    request = OrderRequest(ticker="AAPL", side="buy", quantity=10, order_type="limit", limit_price=None)

    try:
        use_case.execute(request, confirm=True)
        assert False, "expected PlaceOrderError"
    except PlaceOrderError:
        pass


def test_execute_raises_for_a_non_positive_quantity() -> None:
    provider = FakeBrokerageProvider()
    use_case = PlaceOrderUseCase(provider)
    request = OrderRequest(ticker="AAPL", side="buy", quantity=0, order_type="market")

    try:
        use_case.execute(request, confirm=True)
        assert False, "expected PlaceOrderError"
    except PlaceOrderError:
        pass


def test_execute_raises_for_an_invalid_side() -> None:
    provider = FakeBrokerageProvider()
    use_case = PlaceOrderUseCase(provider)
    request = OrderRequest(ticker="AAPL", side="hold", quantity=10, order_type="market")

    try:
        use_case.execute(request, confirm=True)
        assert False, "expected PlaceOrderError"
    except PlaceOrderError:
        pass


def test_execute_surfaces_a_provider_error_as_place_order_error() -> None:
    from src.application.interfaces.brokerage_provider import BrokerageProviderError

    provider = FakeBrokerageProvider(raise_error=BrokerageProviderError("IBKR request failed: network is down"))
    use_case = PlaceOrderUseCase(provider)

    try:
        use_case.execute(_market_buy(), confirm=True)
        assert False, "expected PlaceOrderError"
    except PlaceOrderError as exc:
        assert "network is down" in str(exc)
