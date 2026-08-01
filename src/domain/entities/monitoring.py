"""Domain entities for continuous monitoring.

Monitoring is the first feature in this codebase that legitimately needs
to PERSIST a snapshot rather than recompute fresh every time — every
other agent (valuation, analysis, risk) is stateless by design because
"what is true right now" doesn't need history. Monitoring is different:
"did something change" is meaningless without a stored baseline to
compare the current state against.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AlertType(str, Enum):
    PRICE_MOVE = "PRICE_MOVE"
    TARGET_REACHED = "TARGET_REACHED"


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    """The last-known price for a ticker, as of the last monitoring run.
    This IS the baseline monitoring diffs against — intentionally
    separate from MarketQuote (which is always a fresh live fetch).
    """

    ticker: str
    price: float
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class Alert:
    user_id: str
    ticker: str
    alert_type: AlertType
    message: str
    created_at: datetime
    # Percent change that triggered this alert, e.g. 0.07 for a 7% move —
    # stored as a real number alongside the human-readable message so a
    # future UI can sort/filter/format without re-parsing text.
    change_pct: float
    is_read: bool = False
    # None before persistence (the use case constructs an Alert before
    # saving it); the repository assigns the real id on save.
    id: int | None = None
