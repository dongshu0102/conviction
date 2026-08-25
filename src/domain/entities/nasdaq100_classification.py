"""Domain entity for one ticker's stored, latest-computed row across
all six real screener dimensions -- a lightweight cache row, matching
the same "latest-only" pattern already established for the Conviction
Screener and factor scores.

Every field is deliberately nullable except ticker/as_of/industry:
some are genuinely None when the underlying computation couldn't
produce a real answer (e.g. market_structure_category is None when
too few real, ingested peers exist to compute a meaningful HHI) --
never a fabricated placeholder standing in for missing data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Nasdaq100Classification:
    ticker: str
    as_of: datetime
    industry: str  # GICS-style, from Company.industry
    market_structure_category: str | None  # Perfect Competition / Monopolistic Competition / Oligopoly / Monopoly
    hhi: float | None
    value_chain_position: str | None  # LLM-classified, e.g. "Designer", "Fabricator", "Platform", "Integrator"
    business_model: str | None  # LLM-classified, e.g. "Subscription/SaaS", "Advertising", "Hardware"
    market_cap_tier: str | None  # deterministic, from real market cap
    maturity_stage: str | None  # deterministic, from real market cap + revenue growth
    market_cap: float | None
    revenue_growth: float | None
