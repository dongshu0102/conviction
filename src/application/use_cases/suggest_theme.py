"""Use case: suggest a new investment theme, grounded in real general
market news.

Structurally enforces grounding the same way GenerateThemeSynthesis
does: real headlines are fetched FIRST, and the only way to reach the
LLM is by passing them into ThemeSuggestionGenerator.generate() — no
code path here reaches the model with zero real news behind it.

This is a SUGGESTION, not an action — it never creates a theme or
tags a ticker itself. The caller reviews the result and, if they like
it, uses the existing create_universe_theme / add_ticker_to_theme /
ingest_company / ingest_etf tools to actually act on it. That's the
deliberate boundary that keeps this from being the first fully
autonomous "AI decided and did it" surface in this platform.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.application.interfaces.theme_suggestion_generator import (
    ThemeSuggestionGenerationError,
    ThemeSuggestionGenerator,
)
from src.domain.entities.theme_suggestion import SuggestedTicker, ThemeSuggestion
from src.domain.repositories.company_repository import CompanyRepository

logger = logging.getLogger(__name__)

DEFAULT_HEADLINE_LIMIT = 20


class GeneralNewsUnavailableError(Exception):
    def __init__(self) -> None:
        super().__init__("This data provider does not support general market news.")


class NoNewsAvailableError(Exception):
    def __init__(self) -> None:
        super().__init__("No recent general news was returned to ground a suggestion on.")


class SuggestThemeUseCase:
    def __init__(
        self,
        data_provider: FinancialDataProvider,
        company_repo: CompanyRepository,
        generator: ThemeSuggestionGenerator,
    ) -> None:
        self._data_provider = data_provider
        self._company_repo = company_repo
        self._generator = generator

    def execute(
        self, user_hint: str | None = None, headline_limit: int = DEFAULT_HEADLINE_LIMIT
    ) -> ThemeSuggestion:
        if not hasattr(self._data_provider, "get_general_news"):
            raise GeneralNewsUnavailableError()

        try:
            headlines = self._data_provider.get_general_news(limit=headline_limit)
        except (NotImplementedError, DataProviderError) as exc:
            logger.warning("General news fetch failed: %s", exc)
            raise GeneralNewsUnavailableError() from exc

        if not headlines:
            raise NoNewsAvailableError()

        try:
            result = self._generator.generate(headlines, user_hint)
        except ThemeSuggestionGenerationError:
            logger.exception("Theme suggestion generation failed")
            raise

        already_ingested = {c.ticker for c in self._company_repo.list_all()}
        candidates = [
            SuggestedTicker(
                ticker=t.ticker,
                company_name=t.company_name,
                reasoning=t.reasoning,
                already_ingested=t.ticker in already_ingested,
            )
            for t in result.candidate_tickers
        ]

        return ThemeSuggestion(
            theme_name=result.theme_name,
            rationale=result.rationale,
            candidate_tickers=candidates,
            sourced_headlines=[h.title for h in headlines[:5]],
            generated_at=datetime.now(timezone.utc),
            model_used=result.model_used,
        )
