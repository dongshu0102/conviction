"""Use case: explicitly confirm a brokerage warning reply, allowing an
order that was held pending confirmation to actually be placed.

Only ever call this after the warning returned by PlaceOrderUseCase
has genuinely been surfaced to, and approved by, the person whose
money is at stake -- see OrderResult and BrokerageProvider's own
docstrings for why this is a genuinely separate, deliberate step
rather than something ever auto-triggered."""
from __future__ import annotations

from src.application.interfaces.brokerage_provider import (
    BrokerageProvider,
    BrokerageProviderError,
)
from src.domain.entities.brokerage import OrderResult


class ConfirmOrderError(Exception):
    """A real, visible failure — never silently swallowed."""


class ConfirmOrderUseCase:
    def __init__(self, provider: BrokerageProvider) -> None:
        self._provider = provider

    def execute(self, reply_id: str) -> OrderResult:
        try:
            return self._provider.confirm_order(reply_id)
        except BrokerageProviderError as exc:
            raise ConfirmOrderError(str(exc)) from exc
