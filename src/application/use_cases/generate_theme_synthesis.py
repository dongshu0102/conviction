"""Use case: generate an AI thematic synthesis across a curated
universe theme.

Structurally enforces grounding the same way GenerateCompanyResearch
does: real screening and factor-scoring data is gathered FIRST, and the
only way to reach the LLM is by passing that data into
ThemeSynthesisGenerator.generate(). A ticker with neither screening nor
factor data available contributes nothing and is listed in
tickers_excluded — never silently narrated around.

Factor scores are FILTERED from the full-universe ranking, not
re-standardized within the theme — same "filter, don't re-standardize"
choice already made for rank_universe_by_factors, for the same reason
(recomputing a theme-scoped z-score would be a materially different,
more expensive feature). The generator's system prompt is told this
explicitly via the *_HIGHER_IS_BETTER labels on those fields.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.application.interfaces.theme_synthesis_generator import (
    ThemeSynthesisGenerationError,
    ThemeSynthesisGenerator,
    TickerSynthesisInput,
)
from src.application.use_cases.get_factor_scores import GetFactorScoresUseCase
from src.application.use_cases.manage_universe_theme import (
    GetThemeTickersUseCase,
    ThemeNotFoundError,
)
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.domain.entities.theme_synthesis import ThemeSynthesisReport
from src.domain.repositories.universe_theme_repository import UniverseThemeRepository

logger = logging.getLogger(__name__)

MAX_THEME_TICKERS = 40  # same cap as screen_stocks' theme-scoped path


class ThemeEmptyError(Exception):
    def __init__(self, theme_name: str) -> None:
        super().__init__(
            f"Theme '{theme_name}' has no tickers yet — add some before synthesizing."
        )


class NoSynthesizableDataError(Exception):
    def __init__(self, theme_name: str) -> None:
        super().__init__(
            f"None of the tickers in '{theme_name}' have screening or factor "
            f"data available — ingest and factor-score them first."
        )


class GenerateThemeSynthesisUseCase:
    def __init__(
        self,
        theme_repo: UniverseThemeRepository,
        get_theme_tickers: GetThemeTickersUseCase,
        screen_stocks: ScreenStocksUseCase,
        get_factor_scores: GetFactorScoresUseCase,
        synthesis_generator: ThemeSynthesisGenerator,
    ) -> None:
        self._theme_repo = theme_repo
        self._get_theme_tickers = get_theme_tickers
        self._screen_stocks = screen_stocks
        self._get_factor_scores = get_factor_scores
        self._synthesis_generator = synthesis_generator

    def execute(self, theme_name: str) -> ThemeSynthesisReport:
        theme = self._theme_repo.get(theme_name)
        if theme is None:
            raise ThemeNotFoundError(theme_name)

        tickers = self._get_theme_tickers.execute(theme_name)[:MAX_THEME_TICKERS]
        if not tickers:
            raise ThemeEmptyError(theme_name)

        screen_result = self._screen_stocks.execute(tickers)
        screen_by_ticker = {r.ticker: r for r in screen_result.results}

        all_ranked = self._get_factor_scores.execute()
        factor_by_ticker = {r.ticker: r for r in all_ranked if r.ticker in tickers}

        inputs: list[TickerSynthesisInput] = []
        excluded: list[str] = []

        for ticker in tickers:
            screen = screen_by_ticker.get(ticker)
            factor = factor_by_ticker.get(ticker)
            if screen is None and factor is None:
                excluded.append(ticker)
                continue

            z = factor.score.z_scores if factor else None
            inputs.append(
                TickerSynthesisInput(
                    ticker=ticker,
                    # factor scores don't carry a price field (only market
                    # cap, which isn't the same thing without shares
                    # outstanding) — price is only known via the screen.
                    price=screen.price if screen else None,
                    price_to_earnings=(
                        screen.price_to_earnings if screen
                        else (factor.score.raw.price_to_earnings if factor else None)
                    ),
                    composite_screen_score=screen.composite_score if screen else None,
                    factor_composite_score=factor.composite_score if factor else None,
                    value_z=z.value if z else None,
                    quality_z=z.quality if z else None,
                    growth_z=z.growth if z else None,
                    momentum_z=z.momentum if z else None,
                    size_z=z.size if z else None,
                )
            )

        if not inputs:
            raise NoSynthesizableDataError(theme_name)

        try:
            result = self._synthesis_generator.generate(theme_name, theme.description, inputs)
        except ThemeSynthesisGenerationError:
            logger.exception("Theme synthesis generation failed for %s", theme_name)
            raise

        return ThemeSynthesisReport(
            theme_name=theme_name,
            generated_at=datetime.now(timezone.utc),
            tickers_covered=[i.ticker for i in inputs],
            tickers_excluded=excluded,
            overview=result.overview,
            common_threads=result.common_threads,
            notable_divergences=result.notable_divergences,
            key_risks=result.key_risks,
            model_used=result.model_used,
            raw_response=result.raw_response,
        )
