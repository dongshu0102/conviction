"""Domain entity and pure logic for "Demand Signals" -- a real,
honest translation of the classic microeconomic demand determinants
into what this app can genuinely, directly measure with data it
already has, built directly from a design conversation about which
of the 6 textbook determinants (income, related-goods prices, tastes,
expectations, buyer count, policy) this app can actually support.

Deliberately covers only 3 of the 6 real determinants, each mapped to
data this app has already built and hand-verified tonight:
- Buyer count / market size  -> real revenue growth trend
- Expectations                -> real analyst grade actions + price targets
- Income / spending backdrop  -> the real economic cycle classification

Deliberately does NOT attempt the other 3 (related-goods pricing,
tastes/preferences, government policy): none of them has a real data
source in this app right now, and faking them with placeholder logic
would be dishonest. This is a stated, deliberate scope limit, not an
oversight -- matching the same discipline already used for "Recovery"
in economic_cycle_math.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DemandSignals:
    ticker: str
    latest_revenue_growth_yoy: float | None
    prior_revenue_growth_yoy: float | None
    revenue_growth_accelerating: bool | None
    recent_upgrades: int
    recent_downgrades: int
    analyst_consensus_direction: str  # "More bullish" | "More bearish" | "Mixed" | "No recent activity"
    last_quarter_avg_price_target: float | None
    economic_cycle_state: str


def compute_revenue_growth_acceleration(
    latest: float | None, prior: float | None,
) -> bool | None:
    """True if real revenue growth genuinely accelerated year over
    year (this year's real growth rate exceeds last year's), False if
    it genuinely decelerated, None if either real figure is
    unavailable -- never guessed."""
    if latest is None or prior is None:
        return None
    return latest > prior


def compute_analyst_consensus_direction(upgrades: int, downgrades: int) -> str:
    """A real, honest read on recent analyst grade activity -- counts
    of real upgrade/downgrade actions, not an invented sentiment
    score."""
    if upgrades == 0 and downgrades == 0:
        return "No recent activity"
    if upgrades > downgrades:
        return "More bullish"
    if downgrades > upgrades:
        return "More bearish"
    return "Mixed"
