"""Contract any LLM-backed market structure narrative generator must
satisfy. Same pattern as MasterLensNarrativeGenerator: the use case
depends on this abstraction, never on the Anthropic SDK directly, and
the LLM's job is to explain an already-computed, deterministic
classification through the real economic theory involved -- never to
invent or override the classification itself.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarketStructureNarrativeResult:
    narrative: str
    model_used: str


class MarketStructureNarrativeGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        ticker: str,
        industry: str,
        category: str,
        hhi: float | None,
        company_share: float | None,
        peer_count: int,
        peer_tickers: list[str],
    ) -> MarketStructureNarrativeResult:
        """Produce a narrative explaining the ALREADY-COMPUTED category,
        hhi, and company_share through the real economic theory of that
        specific market structure -- never re-deriving or contradicting
        the given classification."""


class MarketStructureGenerationError(Exception):
    """Raised on any LLM provider failure — use cases catch this,
    never a provider-specific exception."""
