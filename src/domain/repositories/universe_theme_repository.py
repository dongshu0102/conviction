from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.universe_theme import UniverseTheme, UniverseThemeSummary


class UniverseThemeRepository(ABC):
    @abstractmethod
    def create(self, theme: UniverseTheme) -> None:
        """Idempotent on name — creating an existing theme is a no-op,
        not an error, so re-running a setup script is always safe."""

    @abstractmethod
    def get(self, name: str) -> UniverseTheme | None:
        ...

    @abstractmethod
    def list_all(self) -> list[UniverseThemeSummary]:
        ...

    @abstractmethod
    def add_ticker(self, theme_name: str, ticker: str) -> None:
        """Idempotent — adding an already-member ticker is a no-op."""

    @abstractmethod
    def remove_ticker(self, theme_name: str, ticker: str) -> bool:
        """Returns True if the ticker was actually a member."""

    @abstractmethod
    def get_tickers(self, theme_name: str) -> list[str]:
        ...

    @abstractmethod
    def get_themes_for_ticker(self, ticker: str) -> list[str]:
        ...

    @abstractmethod
    def delete(self, name: str) -> bool:
        """Returns True if the theme existed and was deleted. Removes
        every membership row too — a theme with lingering orphaned
        memberships would make list_all()'s member_count and every
        downstream ranking silently wrong."""
