"""Use case: cancel an already-placed, still-open order."""
from __future__ import annotations

from src.application.interfaces.brokerage_provider import (
    BrokerageProvider,
    BrokerageProviderError,
)
from src.domain.entities.brokerage import CancelOrderResult


class CancelOrderError(Exception):
    """A real, visible failure — never silently swallowed. Distinct
    from a genuine, honest CancelOrderResult(success=False) -- this is
    for cases where the cancellation attempt itself couldn't even be
    made (e.g. a network error, an auth failure), not for a real,
    valid "no longer cancelable" outcome."""


class CancelOrderUseCase:
    def __init__(self, provider: BrokerageProvider) -> None:
        self._provider = provider

    def execute(self, order_id: str) -> CancelOrderResult:
        try:
            return self._provider.cancel_order(order_id)
        except BrokerageProviderError as exc:
            raise CancelOrderError(str(exc)) from exc
