"""Contract for generating a thematic synthesis narrative across a
curated universe theme. Same pattern as ResearchGenerator/BriefGenerator
— the use case depends on this abstraction, never on the Anthropic SDK
directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TickerSynthesisInput:
    """Per-ticker grounding data. Fields are independently optional —
    a ticker with only screening data or only factor data still
    contributes what it has; only a ticker with NEITHER is excluded
    entirely (see ThemeSynthesisReport.tickers_excluded).

    NOTE ON SCALES — this matters enough to spell out for whoever
    writes the prompt: composite_screen_score is LOWER-IS-BETTER
    (rank 1 = best), while factor_composite_score is HIGHER-IS-BETTER
    (a positive z-score = more attractive). These are DIFFERENT SCALES
    with OPPOSITE polarity — conflating them would silently invert half
    the narrative's meaning, the exact class of bug this codebase has
    hit before (the screener scoring-inversion lesson). The generator's
    system prompt must state both polarities explicitly.
    """

    ticker: str
    price: float | None
    price_to_earnings: float | None
    composite_screen_score: float | None
    factor_composite_score: float | None
    value_z: float | None
    quality_z: float | None
    growth_z: float | None
    momentum_z: float | None
    size_z: float | None


@dataclass(frozen=True, slots=True)
class ThemeSynthesisGenerationResult:
    overview: str
    common_threads: str
    notable_divergences: str
    key_risks: str
    model_used: str
    raw_response: dict


class ThemeSynthesisGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        theme_name: str,
        theme_description: str | None,
        tickers: list[TickerSynthesisInput],
    ) -> ThemeSynthesisGenerationResult:
        """Produce a grounded thematic narrative from the exact
        structured per-ticker data passed in — no other data source,
        no unstated assumptions, no general knowledge about the
        theme's members beyond what's in `tickers`."""


class ThemeSynthesisGenerationError(Exception):
    pass
