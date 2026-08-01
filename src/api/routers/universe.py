"""Curated investment universe API routes — GLOBAL themes, shared across
every user. Not gated behind get_authenticated_user_id ownership checks
the way watchlists are, since themes are system-wide data, not personal.
API key auth still applies at the app level; there is simply no
per-user scoping to enforce here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.routers.companies import get_company_repository
from src.api.schemas import (
    ThemeTickersSchema,
    UniverseThemeListSchema,
    UniverseThemeSchema,
    UniverseThemeSummarySchema,
)
from src.application.use_cases.manage_universe_theme import (
    AddTickerToThemeUseCase,
    CreateUniverseThemeUseCase,
    GetThemeTickersUseCase,
    ListUniverseThemesUseCase,
    RemoveTickerFromThemeUseCase,
    ThemeNotFoundError,
    TickerNotIngestedForThemeError,
)
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.universe_theme_repository_impl import (
    SqlAlchemyUniverseThemeRepository,
)

router = APIRouter(prefix="/universe", tags=["universe"])


def get_theme_repository() -> SqlAlchemyUniverseThemeRepository:
    return SqlAlchemyUniverseThemeRepository()


def get_create_use_case(
    theme_repo: SqlAlchemyUniverseThemeRepository = Depends(get_theme_repository),
) -> CreateUniverseThemeUseCase:
    return CreateUniverseThemeUseCase(theme_repo)


def get_add_ticker_use_case(
    theme_repo: SqlAlchemyUniverseThemeRepository = Depends(get_theme_repository),
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
) -> AddTickerToThemeUseCase:
    return AddTickerToThemeUseCase(theme_repo, company_repo)


def get_remove_ticker_use_case(
    theme_repo: SqlAlchemyUniverseThemeRepository = Depends(get_theme_repository),
) -> RemoveTickerFromThemeUseCase:
    return RemoveTickerFromThemeUseCase(theme_repo)


def get_list_use_case(
    theme_repo: SqlAlchemyUniverseThemeRepository = Depends(get_theme_repository),
) -> ListUniverseThemesUseCase:
    return ListUniverseThemesUseCase(theme_repo)


def get_theme_tickers_use_case(
    theme_repo: SqlAlchemyUniverseThemeRepository = Depends(get_theme_repository),
) -> GetThemeTickersUseCase:
    return GetThemeTickersUseCase(theme_repo)


@router.post("/themes/{name}", response_model=UniverseThemeSchema)
def create_theme(
    name: str,
    description: str | None = None,
    use_case: CreateUniverseThemeUseCase = Depends(get_create_use_case),
) -> UniverseThemeSchema:
    theme = use_case.execute(name, description)
    return UniverseThemeSchema(
        name=theme.name, description=theme.description, created_at=theme.created_at
    )


@router.get("/themes", response_model=UniverseThemeListSchema)
def list_themes(
    use_case: ListUniverseThemesUseCase = Depends(get_list_use_case),
) -> UniverseThemeListSchema:
    summaries = use_case.execute()
    return UniverseThemeListSchema(
        themes=[
            UniverseThemeSummarySchema(
                theme=UniverseThemeSchema(
                    name=s.theme.name, description=s.theme.description, created_at=s.theme.created_at
                ),
                member_count=s.member_count,
            )
            for s in summaries
        ]
    )


@router.get("/themes/{name}/tickers", response_model=ThemeTickersSchema)
def get_theme_tickers(
    name: str,
    use_case: GetThemeTickersUseCase = Depends(get_theme_tickers_use_case),
) -> ThemeTickersSchema:
    try:
        tickers = use_case.execute(name)
    except ThemeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ThemeTickersSchema(theme_name=name, tickers=tickers)


@router.post("/themes/{name}/tickers/{ticker}")
def add_ticker(
    name: str,
    ticker: str,
    use_case: AddTickerToThemeUseCase = Depends(get_add_ticker_use_case),
) -> dict[str, str]:
    try:
        use_case.execute(name, ticker)
    except ThemeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TickerNotIngestedForThemeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"theme_name": name, "ticker": ticker.strip().upper(), "status": "added"}


@router.delete("/themes/{name}/tickers/{ticker}")
def remove_ticker(
    name: str,
    ticker: str,
    use_case: RemoveTickerFromThemeUseCase = Depends(get_remove_ticker_use_case),
) -> dict[str, bool]:
    removed = use_case.execute(name, ticker)
    if not removed:
        raise HTTPException(
            status_code=404, detail=f"'{ticker.upper()}' is not tagged into '{name}'."
        )
    return {"removed": True}
