"""Use case: real, live cash and buying power for the connected
brokerage account."""
from __future__ import annotations

from src.application.interfaces.brokerage_provider import (
    BrokerageProvider,
    BrokerageProviderError,
)
from src.domain.entities.brokerage import BrokerageAccountSummary


class GetBrokerageAccountSummaryError(Exception):
    """A real, visible failure — never silently swallowed."""


class GetBrokerageAccountSummaryUseCase:
    def __init__(self, provider: BrokerageProvider) -> None:
        self._provider = provider

    def execute(self) -> BrokerageAccountSummary:
        try:
            return self._provider.get_account_summary()
        except BrokerageProviderError as exc:
            raise GetBrokerageAccountSummaryError(str(exc)) from exc
