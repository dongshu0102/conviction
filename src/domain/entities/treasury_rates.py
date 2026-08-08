"""The Treasury yield curve — the market's own real-time proxy for
the risk-free rate, and the closest thing this platform has to a
direct Fed-policy signal. Every rate here is a decimal (0.0469 for
4.69%), matching the convention every other rate in this codebase
uses (discount_rate, growth_rate, etc) — not the raw percentage FMP
itself returns.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class TreasuryRates:
    as_of: date
    month1: float | None
    month2: float | None
    month3: float | None
    month6: float | None
    year1: float | None
    year2: float | None
    year3: float | None
    year5: float | None
    year7: float | None
    year10: float | None
    year20: float | None
    year30: float | None
