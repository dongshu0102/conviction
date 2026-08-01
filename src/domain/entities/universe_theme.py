"""Domain entities for the curated investment universe.

A theme is a GLOBAL, system-wide grouping ("AI Infrastructure", "China",
"Fintech") — not a per-user list like watchlists. Membership is
many-to-many: one ticker can belong to several themes (NVDA is both
"AI Infrastructure" and "Semiconductors"), which is the actual gap this
fills — Company.sector is a rigid single value, themes are not.

ETFs are deliberately out of scope: every downstream consumer (factor
scoring, valuation) assumes an operating company with financial
statements. A theme can only reference tickers already ingested as
Company entities.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class UniverseTheme:
    name: str
    description: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("UniverseTheme.name must be a non-empty string")
        object.__setattr__(self, "name", self.name.strip())


@dataclass(frozen=True, slots=True)
class UniverseThemeSummary:
    """A theme plus its member count, for list views — avoids callers
    having to fetch full membership just to show "AI Infrastructure (12
    tickers)" in a listing."""

    theme: UniverseTheme
    member_count: int
