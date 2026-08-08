"""A single economic indicator reading (GDP, CPI, unemployment rate,
etc) — one real, structured macro data point, distinct from the
qualitative/news-driven macro factors (geopolitical events,
regulatory change, foreign central bank policy) that don't have a
clean numeric API and aren't represented as this entity at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class EconomicIndicatorReading:
    name: str
    as_of: date
    value: float
