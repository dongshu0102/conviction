"""Use case: the current, live status of an already-placed order --
distinct from PlaceOrderUseCase, whose own return value reflects only
the outcome of the placement call itself, not whether the order has
since filled, partially filled, or been canceled/rejected downstream.
"""
from __future__ import annotations

from src.application.interfaces.brokerage_provider import (
    BrokerageProvider,
    BrokerageProviderError,
)
from src.domain.entities.brokerage import OrderStatus


class GetOrderStatusError(Exception):
    """A real, visible failure — never silently swallowed."""


class GetOrderStatusUseCase:
    def __init__(self, provider: BrokerageProvider) -> None:
        self._provider = provider

    def execute(self, order_id: str) -> OrderStatus:
        try:
            return self._provider.get_order_status(order_id)
        except BrokerageProviderError as exc:
            raise GetOrderStatusError(str(exc)) from exc
