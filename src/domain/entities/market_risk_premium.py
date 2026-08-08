"""A country's equity risk premium — the extra return investors
demand for holding that country's stocks over its own risk-free rate.
Genuinely different shape from Treasury rates or economic indicators:
this isn't a time series, it's a single current reading per country.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarketRiskPremium:
    country: str
    country_risk_premium: float
    total_equity_risk_premium: float
