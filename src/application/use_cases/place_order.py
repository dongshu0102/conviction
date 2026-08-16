"""Use case: place a real order at a real, connected brokerage --
real money at stake once configured with real credentials.

Deliberately requires an explicit, separate confirm=True argument
that defaults to False -- the same "explicit permission required"
principle applied to every other high-stakes action, pushed down into
the use case itself rather than trusted entirely to whatever caller
happens to invoke this (a chat tool, an API route, a script). A
caller that doesn't pass confirm=True gets a clear, honest preview of
what WOULD be submitted, and nothing is actually sent to the
brokerage. This is a genuine, real safeguard, not a formality: it
means a bug in a caller that accidentally invokes this use case
without an explicit, real user confirmation cannot silently place a
real order.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.application.interfaces.brokerage_provider import (
    BrokerageProvider,
    BrokerageProviderError,
)
from src.domain.entities.brokerage import OrderRequest, OrderResult


class PlaceOrderError(Exception):
    """A real, visible failure — never silently swallowed."""


@dataclass(frozen=True, slots=True)
class PlaceOrderResult:
    confirmed: bool
    request: OrderRequest
    order_result: OrderResult | None  # None when confirmed=False (preview only)


class PlaceOrderUseCase:
    def __init__(self, provider: BrokerageProvider) -> None:
        self._provider = provider

    def execute(self, request: OrderRequest, confirm: bool = False) -> PlaceOrderResult:
        if request.order_type not in ("market", "limit"):
            raise PlaceOrderError(
                f"Unsupported order_type '{request.order_type}' — only 'market' and 'limit' are supported."
            )
        if request.order_type == "limit" and request.limit_price is None:
            raise PlaceOrderError("limit_price is required for a limit order.")
        if request.quantity <= 0:
            raise PlaceOrderError(f"quantity must be positive, got {request.quantity}.")
        if request.side not in ("buy", "sell"):
            raise PlaceOrderError(f"side must be 'buy' or 'sell', got '{request.side}'.")

        if not confirm:
            return PlaceOrderResult(confirmed=False, request=request, order_result=None)

        try:
            result = self._provider.place_order(request)
        except BrokerageProviderError as exc:
            raise PlaceOrderError(str(exc)) from exc

        return PlaceOrderResult(confirmed=True, request=request, order_result=result)
