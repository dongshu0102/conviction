"""Use cases for the curated investment universe (global themes).

Membership requires the ticker already be an ingested Company —
same rationale as watchlist's TickerNotIngestedError: a theme
containing an unknown ticker would make every downstream consumer
(factor scoring, valuation) fail confusingly later instead of
rejecting clearly at the point of curation.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.domain.entities.universe_theme import UniverseTheme, UniverseThemeSummary
from src.domain.repositories.company_repository import CompanyRepository
from src.domain.repositories.universe_theme_repository import UniverseThemeRepository


class ThemeNotFoundError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"No universe theme named '{name}'. Create it first.")


class TickerNotIngestedForThemeError(Exception):
    def __init__(self, ticker: str) -> None:
        super().__init__(
            f"'{ticker}' has not been ingested yet — ingest it first via "
            f"POST /companies/{ticker}/ingest before adding it to a theme."
        )


class CreateUniverseThemeUseCase:
    def __init__(self, theme_repo: UniverseThemeRepository) -> None:
        self._theme_repo = theme_repo

    def execute(self, name: str, description: str | None = None) -> UniverseTheme:
        theme = UniverseTheme(
            name=name, description=description, created_at=datetime.now(timezone.utc)
        )
        self._theme_repo.create(theme)
        return theme


class AddTickerToThemeUseCase:
    def __init__(
        self, theme_repo: UniverseThemeRepository, company_repo: CompanyRepository
    ) -> None:
        self._theme_repo = theme_repo
        self._company_repo = company_repo

    def execute(self, theme_name: str, ticker: str) -> None:
        ticker = ticker.strip().upper()
        if self._theme_repo.get(theme_name) is None:
            raise ThemeNotFoundError(theme_name)
        if self._company_repo.get_by_ticker(ticker) is None:
            raise TickerNotIngestedForThemeError(ticker)
        self._theme_repo.add_ticker(theme_name, ticker)


class RemoveTickerFromThemeUseCase:
    def __init__(self, theme_repo: UniverseThemeRepository) -> None:
        self._theme_repo = theme_repo

    def execute(self, theme_name: str, ticker: str) -> bool:
        return self._theme_repo.remove_ticker(theme_name, ticker.strip().upper())


class ListUniverseThemesUseCase:
    def __init__(self, theme_repo: UniverseThemeRepository) -> None:
        self._theme_repo = theme_repo

    def execute(self) -> list[UniverseThemeSummary]:
        return self._theme_repo.list_all()


class GetThemeTickersUseCase:
    def __init__(self, theme_repo: UniverseThemeRepository) -> None:
        self._theme_repo = theme_repo

    def execute(self, theme_name: str) -> list[str]:
        if self._theme_repo.get(theme_name) is None:
            raise ThemeNotFoundError(theme_name)
        return self._theme_repo.get_tickers(theme_name)


class GetThemesForTickerUseCase:
    def __init__(self, theme_repo: UniverseThemeRepository) -> None:
        self._theme_repo = theme_repo

    def execute(self, ticker: str) -> list[str]:
        return self._theme_repo.get_themes_for_ticker(ticker)
