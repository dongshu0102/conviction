"""Contract for generating an AI-suggested investment theme, grounded
in real general market news. Same pattern as ThemeSynthesisGenerator —
the use case depends on this abstraction, never the Anthropic SDK
directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.entities.general_news import GeneralNewsHeadline


@dataclass(frozen=True, slots=True)
class SuggestedTickerResult:
    ticker: str
    company_name: str
    reasoning: str


@dataclass(frozen=True, slots=True)
class ThemeSuggestionGenerationResult:
    theme_name: str
    rationale: str
    candidate_tickers: list[SuggestedTickerResult]
    model_used: str
    raw_response: dict


class ThemeSuggestionGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        headlines: list[GeneralNewsHeadline],
        user_hint: str | None,
    ) -> ThemeSuggestionGenerationResult:
        """Propose a theme grounded in the given headlines (and an
        optional user-supplied topic hint). Must not invent a trend
        unrelated to the actual headlines provided, and must only name
        real, actual public company ticker symbols — never a
        plausible-sounding fabrication."""


class ThemeSuggestionGenerationError(Exception):
    pass
