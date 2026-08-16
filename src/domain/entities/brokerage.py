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
