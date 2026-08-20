"""Use case: the account's real order history, most recent first."""
from __future__ import annotations

from dataclasses import dataclass

from src.application.interfaces.brokerage_provider import (
    BrokerageProvider,
    BrokerageProviderError,
)
from src.domain.entities.brokerage import OrderHistoryEntry


class GetOrderHistoryError(Exception):
    """A real, visible failure — never silently swallowed."""


@dataclass(frozen=True, slots=True)
class GetOrderHistoryResult:
    entries: tuple[OrderHistoryEntry, ...]


class GetOrderHistoryUseCase:
    def __init__(self, provider: BrokerageProvider) -> None:
        self._provider = provider

    def execute(self, limit: int = 50) -> GetOrderHistoryResult:
        try:
            entries = self._provider.get_order_history(limit=limit)
        except BrokerageProviderError as exc:
            raise GetOrderHistoryError(str(exc)) from exc

        return GetOrderHistoryResult(entries=tuple(entries))
