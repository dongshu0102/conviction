from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """A request to place a real order at a real brokerage. side is
    "buy" or "sell"; order_type is "market" or "limit" (stop and
    stop_limit are not supported in this first version); time_in_force
    defaults to "day" (the safest, most conservative choice -- an
    unfilled order is automatically canceled at the end of the trading
    day, rather than persisting silently)."""

    ticker: str
    side: str  # "buy" or "sell"
    quantity: float
    order_type: str  # "market" or "limit"
    limit_price: float | None = None  # required if order_type == "limit"
    time_in_force: str = "day"


@dataclass(frozen=True, slots=True)
class OrderResult:
    """The result of submitting an order. status is one of:
    "submitted" (the order was accepted and is now live at the
    brokerage, no further action needed), "needs_confirmation" (the
    brokerage returned a real, specific warning -- e.g. the price is
    far from the current market price -- and is refusing to proceed
    until the caller explicitly confirms via confirm_order(reply_id);
    the order has NOT been placed yet), or "rejected" (the brokerage
    outright refused the order -- e.g. insufficient buying power --
    and it will never be placed no matter what).

    reply_id and warning_messages are only populated when status is
    "needs_confirmation". rejection_reason is only populated when
    status is "rejected". order_id is only populated when status is
    "submitted"."""

    status: str  # "submitted", "needs_confirmation", or "rejected"
    order_id: str | None = None
    reply_id: str | None = None
    warning_messages: tuple[str, ...] = ()
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class OrderStatus:
    """The current, live state of an already-placed order -- distinct
    from OrderResult, which represents the outcome of the PLACEMENT
    call itself. status here reflects the order's actual, real-time
    state at the brokerage (e.g. "new", "filled", "partially_filled",
    "canceled", "rejected", "expired") -- the exact vocabulary is
    brokerage-specific and passed through honestly, not forced into a
    fixed enum across all three providers, since they don't share one.

    filled_quantity and filled_avg_price are 0 (not None) for a fully
    unfilled order -- a genuine, honest zero, not a missing value. Both
    can also genuinely be 0 for an order that hasn't yet processed at
    all (e.g. submitted outside market hours), independent of whether
    the order will eventually fill.
    """

    order_id: str
    status: str
    filled_quantity: float
    filled_avg_price: float | None


@dataclass(frozen=True, slots=True)
class CancelOrderResult:
    """The outcome of attempting to cancel an already-placed order.
    success=False is a genuine, honest outcome, not a failure of this
    app -- an order that has already filled, or already been
    canceled/rejected, is no longer cancelable at any brokerage, and
    that fact needs to reach the caller with a real reason, not just a
    bare False."""

    success: bool
    reason: str | None = None  # populated when success is False


@dataclass(frozen=True, slots=True)
class OrderHistoryEntry:
    """One order in the account's real order history -- genuinely
    richer than OrderStatus alone, since a history view needs to say
    what the order actually was (ticker, side, quantity), not just
    its current state. submitted_at is a real ISO 8601 timestamp
    string, not a parsed datetime -- three genuinely different
    brokerages format this differently, and passing the raw, real
    string through honestly avoids silently misparsing one of them."""

    order_id: str
    ticker: str
    side: str
    quantity: float
    order_type: str
    status: str
    filled_quantity: float
    filled_avg_price: float | None
    submitted_at: str | None


@dataclass(frozen=True, slots=True)
class BrokeragePosition:
    """One currently-held position at the real brokerage account."""

    ticker: str
    quantity: float
    average_cost: float
    market_value: float
    unrealized_pnl: float


@dataclass(frozen=True, slots=True)
class BrokerageAccountSummary:
    """A snapshot of the real brokerage account's cash and buying
    power -- confirmed directly against IBKR's own documented Account
    fields."""

    account_id: str
    cash: float
    buying_power: float
    equity: float
    currency: str
