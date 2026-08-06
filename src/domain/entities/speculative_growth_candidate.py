"""Domain entity for a tracked speculative-growth candidate.

A user explicitly adds a ticker here after Growth Hunter's assessment
shows the necessary conditions (accelerating growth, adequate runway,
still small-cap) are plausible. This entity's job is purely to track
WHICH tickers are being watched and their LAST-KNOWN condition state —
mirroring PriceSnapshot's role for price monitoring — so a later
periodic check can detect genuine CHANGES rather than re-alerting on
steady-state every run.

Deliberately does not store a verdict or a score. The three fields
below are the same ones AssessSpeculativeGrowthUseCase already treats
as meaningful signals, carried forward here only so the next check has
something to diff against.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SpeculativeGrowthCandidate:
    user_id: str
    ticker: str
    added_at: datetime

    # None until the first check runs — mirrors run_monitoring_check's
    # "no prior snapshot means no diff, not a change" principle. The
    # very first check after adding a candidate establishes this
    # baseline and fires no alert, same as price monitoring's first run.
    last_growth_trend: str | None = None
    last_cash_runway_months: float | None = None
    last_market_cap: float | None = None
    last_checked_at: datetime | None = None
