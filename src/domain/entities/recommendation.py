"""Domain entities for portfolio-gap-aware stock recommendations.

Deliberately different from ScreenedStock/ScreenResult: this is about
FINDING candidates from a real gap in the portfolio, not ranking
candidates the caller already named. The gap-finding logic (which
sectors are under-represented) is what's new here; the actual
value/quality ranking of candidates reuses ScreenStocksUseCase as-is.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.domain.entities.stock_screen import ScreenedStock


@dataclass(frozen=True, slots=True)
class SectorGapPick:
    """A screened stock, tagged with which portfolio gap it addresses."""

    stock: ScreenedStock
    gap_sector: str
    current_sector_weight: float


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    portfolio_id: str
    as_of: datetime
    gap_sectors: list[str] = field(default_factory=list)
    picks: list[SectorGapPick] = field(default_factory=list)
