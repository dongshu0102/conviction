"""Contract for generating a Daily Brief narrative from structured data.

Same pattern as ResearchGenerator: the use case depends on this
abstraction, never on the Anthropic SDK directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.entities.daily_brief import PortfolioBriefSummary, WatchlistPriceMove


@dataclass(frozen=True, slots=True)
class BriefGenerationResult:
    narrative: str
    model_used: str


class BriefGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        watchlist_moves: list[WatchlistPriceMove],
        portfolio_summaries: list[PortfolioBriefSummary],
        unread_alert_count: int,
    ) -> BriefGenerationResult:
        """Produce a short narrative grounded in the exact structured data
        passed in — no other data source, no unstated assumptions."""


class BriefGenerationError(Exception):
    pass
