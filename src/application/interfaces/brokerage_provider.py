"""Contract for a real brokerage provider capable of placing real
orders with real money. Same Dependency Inversion pattern as
FinancialDataProvider / OptionsDataProvider -- the application layer
depends on this interface, never on a specific brokerage's wire
format directly.

Deliberately a narrower, more cautious interface than the read-only
data providers elsewhere in this codebase: every method that can move
real money is named and shaped to make the caller's intent explicit
and auditable, and warning replies from the brokerage are never
silently bypassed -- see OrderResult's own docstring.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.brokerage import (
    BrokerageAccountSummary,
    BrokeragePosition,
    OrderRequest,
    OrderResult,
    OrderStatus,
)


class BrokerageProviderError(Exception):
    """A real, visible failure -- authentication failure, network
    error, or a brokerage response this provider doesn't know how to
    parse -- never silently swallowed."""


class BrokerageProvider(ABC):
    @abstractmethod
    def resolve_ticker_to_contract_id(self, ticker: str) -> str | None:
        """Resolve a plain ticker symbol to this brokerage's own,
        internal contract identifier, required before an order can be
        placed. Returns None if no matching contract is found -- an
        honest, real outcome (e.g. a genuinely invalid ticker), not an
        error."""

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResult:
        """Submit a real order. May return status="needs_confirmation"
        if the brokerage raised a real, specific warning about this
        order -- the order has NOT been placed in that case, and the
        caller must call confirm_order(reply_id) explicitly to
        proceed. Never auto-confirms a warning on the caller's
        behalf."""

    @abstractmethod
    def confirm_order(self, reply_id: str) -> OrderResult:
        """Explicitly confirm a warning reply returned by place_order,
        allowing the order to actually be placed. Only ever call this
        after the warning has genuinely been surfaced to, and approved
        by, the person whose money is at stake."""

    @abstractmethod
    def get_account_summary(self) -> BrokerageAccountSummary:
        """Real, live cash and buying power for the connected
        account."""

    @abstractmethod
    def get_positions(self) -> list[BrokeragePosition]:
        """Every currently-held position in the connected account."""

    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderStatus:
        """The current, live state of an already-placed order --
        distinct from place_order's own return value, which reflects
        only the outcome of the placement call itself, not whether the
        order has since filled, partially filled, or been canceled or
        rejected downstream."""
