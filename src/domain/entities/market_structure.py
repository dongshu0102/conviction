"""Domain entity for classifying a company's real market structure
into one of the four classic microeconomic categories: Perfect
Competition, Monopolistic Competition, Oligopoly, Monopoly.

Deliberately grounded in a real, established methodology -- the
Herfindahl-Hirschman Index (HHI), the actual metric the U.S. DOJ and
FTC use for antitrust market-concentration analysis -- rather than an
invented scoring scheme, matching the same "real, deterministic
arithmetic before any narrative" discipline as Master Lens.

Honest, real limitation, stated here rather than hidden: HHI and
market share are computed only from this app's own ingested universe
(S&P 500 + Nasdaq-100 + Dow Jones, ~580 large-cap companies) as the
proxy for "the market" -- not the true, full real-world market
including every private and small-cap competitor. This tends to
OVERSTATE concentration, since real competitors outside this app's
ingested universe aren't counted. This is disclosed directly in the
result, not glossed over.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarketStructureClassification:
    ticker: str
    industry: str
    category: str  # "Perfect Competition" | "Monopolistic Competition" | "Oligopoly" | "Monopoly"
    hhi: float | None  # None if too few ingested peers to compute meaningfully
    company_market_share: float | None  # this company's own share of the group's total revenue, 0-1
    peer_count: int  # how many ingested companies (including this one) share the same industry
    narrative: str
    model_used: str
