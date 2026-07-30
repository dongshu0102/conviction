"""Watchlist API routes. Requires a valid API key (X-Api-Key header) —
see src/api/auth.py. Create a key first via POST /api-keys.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth import get_authenticated_user_id
from src.api.routers.companies import get_company_repository
from src.api.schemas import WatchlistItemSchema
from src.application.use_cases.manage_watchlist import (
    AddToWatchlistUseCase,
    GetWatchlistUseCase,
    RemoveFromWatchlistUseCase,
    TickerNotIngestedError,
)
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.watchlist_repository_impl import (
    SqlAlchemyWatchlistRepository,
)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def get_watchlist_repository() -> SqlAlchemyWatchlistRepository:
    return SqlAlchemyWatchlistRepository()


def get_add_use_case(
    watchlist_repo: SqlAlchemyWatchlistRepository = Depends(get_watchlist_repository),
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
) -> AddToWatchlistUseCase:
    return AddToWatchlistUseCase(watchlist_repo, company_repo)


def get_remove_use_case(
    watchlist_repo: SqlAlchemyWatchlistRepository = Depends(get_watchlist_repository),
) -> RemoveFromWatchlistUseCase:
    return RemoveFromWatchlistUseCase(watchlist_repo)


def get_list_use_case(
    watchlist_repo: SqlAlchemyWatchlistRepository = Depends(get_watchlist_repository),
) -> GetWatchlistUseCase:
    return GetWatchlistUseCase(watchlist_repo)


def _to_schema(item) -> WatchlistItemSchema:
    return WatchlistItemSchema(
        user_id=item.user_id, ticker=item.ticker, added_at=item.added_at, notes=item.notes
    )


@router.post("/{ticker}", response_model=WatchlistItemSchema)
def add_to_watchlist(
    ticker: str,
    notes: str | None = Query(default=None),
    user_id: str = Depends(get_authenticated_user_id),
    use_case: AddToWatchlistUseCase = Depends(get_add_use_case),
) -> WatchlistItemSchema:
    try:
        item = use_case.execute(user_id, ticker, notes)
    except TickerNotIngestedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_schema(item)


@router.delete("/{ticker}")
def remove_from_watchlist(
    ticker: str,
    user_id: str = Depends(get_authenticated_user_id),
    use_case: RemoveFromWatchlistUseCase = Depends(get_remove_use_case),
) -> dict[str, bool]:
    removed = use_case.execute(user_id, ticker)
    if not removed:
        raise HTTPException(
            status_code=404, detail=f"'{ticker.upper()}' is not on your watchlist"
        )
    return {"removed": True}


@router.get("", response_model=list[WatchlistItemSchema])
def get_watchlist(
    user_id: str = Depends(get_authenticated_user_id),
    use_case: GetWatchlistUseCase = Depends(get_list_use_case),
) -> list[WatchlistItemSchema]:
    return [_to_schema(item) for item in use_case.execute(user_id)]
