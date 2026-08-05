from __future__ import annotations

from sqlalchemy import func, select

from src.domain.entities.universe_theme import UniverseTheme, UniverseThemeSummary
from src.domain.repositories.universe_theme_repository import UniverseThemeRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import (
    UniverseThemeMembershipModel,
    UniverseThemeModel,
)


def _to_domain(row: UniverseThemeModel) -> UniverseTheme:
    return UniverseTheme(name=row.name, description=row.description, created_at=row.created_at)


class SqlAlchemyUniverseThemeRepository(UniverseThemeRepository):
    def create(self, theme: UniverseTheme) -> None:
        with session_scope() as session:
            existing = session.get(UniverseThemeModel, theme.name)
            if existing is None:
                session.add(
                    UniverseThemeModel(
                        name=theme.name,
                        description=theme.description,
                        created_at=theme.created_at,
                    )
                )

    def get(self, name: str) -> UniverseTheme | None:
        with session_scope() as session:
            row = session.get(UniverseThemeModel, name.strip())
            return _to_domain(row) if row else None

    def list_all(self) -> list[UniverseThemeSummary]:
        with session_scope() as session:
            themes = session.execute(select(UniverseThemeModel)).scalars().all()
            counts = dict(
                session.execute(
                    select(
                        UniverseThemeMembershipModel.theme_name,
                        func.count(UniverseThemeMembershipModel.id),
                    ).group_by(UniverseThemeMembershipModel.theme_name)
                ).all()
            )
            return [
                UniverseThemeSummary(theme=_to_domain(t), member_count=counts.get(t.name, 0))
                for t in themes
            ]

    def add_ticker(self, theme_name: str, ticker: str) -> None:
        ticker = ticker.strip().upper()
        with session_scope() as session:
            existing = session.execute(
                select(UniverseThemeMembershipModel).where(
                    UniverseThemeMembershipModel.theme_name == theme_name,
                    UniverseThemeMembershipModel.ticker == ticker,
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    UniverseThemeMembershipModel(theme_name=theme_name, ticker=ticker)
                )

    def remove_ticker(self, theme_name: str, ticker: str) -> bool:
        ticker = ticker.strip().upper()
        with session_scope() as session:
            existing = session.execute(
                select(UniverseThemeMembershipModel).where(
                    UniverseThemeMembershipModel.theme_name == theme_name,
                    UniverseThemeMembershipModel.ticker == ticker,
                )
            ).scalar_one_or_none()
            if existing is None:
                return False
            session.delete(existing)
            return True

    def get_tickers(self, theme_name: str) -> list[str]:
        with session_scope() as session:
            rows = session.execute(
                select(UniverseThemeMembershipModel.ticker).where(
                    UniverseThemeMembershipModel.theme_name == theme_name
                )
            ).scalars().all()
            return sorted(rows)

    def get_themes_for_ticker(self, ticker: str) -> list[str]:
        with session_scope() as session:
            rows = session.execute(
                select(UniverseThemeMembershipModel.theme_name).where(
                    UniverseThemeMembershipModel.ticker == ticker.strip().upper()
                )
            ).scalars().all()
            return sorted(rows)

    def delete(self, name: str) -> bool:
        with session_scope() as session:
            theme = session.get(UniverseThemeModel, name.strip())
            if theme is None:
                return False
            memberships = session.execute(
                select(UniverseThemeMembershipModel).where(
                    UniverseThemeMembershipModel.theme_name == theme.name
                )
            ).scalars().all()
            for m in memberships:
                session.delete(m)
            session.delete(theme)
            return True
