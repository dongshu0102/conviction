"""Pure functions for the two fully-deterministic screener dimensions:
market cap tier and maturity stage. No LLM involved at all -- both
are computed directly from real, already-ingested market cap and
revenue growth figures.

Kept free of any repository/provider/LLM imports -- same principle as
valuation_math.py and master_lens_scoring.py.
"""
from __future__ import annotations

# Thresholds deliberately scoped to the Nasdaq-100's own, real size
# range (roughly $10B-$3T+), not the broader market -- a company here
# genuinely called "Mid-Cap" would be large-cap in the wider market,
# but these tiers are honestly relative to this specific universe, not
# a claim about market-wide cap conventions.
_MEGA_CAP_THRESHOLD = 500_000_000_000.0
_LARGE_CAP_THRESHOLD = 100_000_000_000.0


def classify_market_cap_tier(market_cap: float | None) -> str | None:
    if market_cap is None or market_cap <= 0:
        return None
    if market_cap >= _MEGA_CAP_THRESHOLD:
        return "Mega-Cap"
    if market_cap >= _LARGE_CAP_THRESHOLD:
        return "Large-Cap"
    return "Mid-Cap"


def classify_maturity_stage(revenue_growth: float | None) -> str | None:
    """Revenue growth is the real, direct proxy used here -- a mature
    business's own growth naturally slows as its addressable market
    saturates, while a hyper-growth business's own revenue expands
    fast precisely because it hasn't yet."""
    if revenue_growth is None:
        return None
    if revenue_growth >= 0.25:
        return "Hyper-Growth"
    if revenue_growth >= 0.10:
        return "Growth"
    return "Mature"
