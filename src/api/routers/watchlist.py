"""Watchlist API routes. Requires a valid API key (X-Api-Key header) —
see src/api/auth.py. Create a key first via POST /api-keys.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth import get_authenticated_user_id
from src.api.routers.companies import (
    get_company_repository,
    get_data_provider,
)
from src.api.routers.companies import get_valuation_use_case as get_company_valuation_use_case
from src.api.schemas import (
    NewsArticleSchema,
    TriageItemSchema,
    TriageResponseSchema,
    TriageSignalsSchema,
    WatchlistItemSchema,
    WatchlistNewsResponseSchema,
)
from src.application.use_cases.get_watchlist_news import GetWatchlistNewsUseCase
from src.application.use_cases.manage_watchlist import (
    AddToWatchlistUseCase,
    GetWatchlistUseCase,
    RemoveFromWatchlistUseCase,
    TickerNotIngestedError,
)
from src.application.use_cases.triage_watchlist import TriageWatchlistUseCase
from src.infrastructure.persistence.monitoring_repository_impl import (
    SqlAlchemyPriceSnapshotRepository,
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
    data_provider=Depends(get_data_provider),
    valuation_use_case=Depends(get_company_valuation_use_case),
) -> AddToWatchlistUseCase:
    # data_provider + valuation wired so add-time baselines (added_price,
    # added_pe) get captured — best effort, never blocks the add.
    return AddToWatchlistUseCase(
        watchlist_repo, company_repo,
        data_provider=data_provider, valuation_use_case=valuation_use_case,
    )


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
        user_id=item.user_id,
        ticker=item.ticker,
        added_at=item.added_at,
        notes=item.notes,
        list_name=item.list_name,
        target_price=item.target_price,
        alert_threshold_pct=item.alert_threshold_pct,
        added_price=item.added_price,
        added_pe=item.added_pe,
    )


@router.post("/{ticker}", response_model=WatchlistItemSchema)
def add_to_watchlist(
    ticker: str,
    notes: str | None = Query(default=None),
    list_name: str = Query(default="Default"),
    target_price: float | None = Query(default=None),
    alert_threshold_pct: float | None = Query(default=None),
    user_id: str = Depends(get_authenticated_user_id),
    use_case: AddToWatchlistUseCase = Depends(get_add_use_case),
) -> WatchlistItemSchema:
    try:
        item = use_case.execute(
            user_id, ticker, notes,
            list_name=list_name,
            target_price=target_price,
            alert_threshold_pct=alert_threshold_pct,
        )
    except TickerNotIngestedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_schema(item)


@router.delete("/{ticker}")
def remove_from_watchlist(
    ticker: str,
    list_name: str | None = Query(default=None),
    user_id: str = Depends(get_authenticated_user_id),
    use_case: RemoveFromWatchlistUseCase = Depends(get_remove_use_case),
) -> dict[str, bool]:
    removed = use_case.execute(user_id, ticker, list_name)
    if not removed:
        raise HTTPException(
            status_code=404, detail=f"'{ticker.upper()}' is not on your watchlist"
        )
    return {"removed": True}


@router.get("", response_model=list[WatchlistItemSchema])
def get_watchlist(
    list_name: str | None = Query(default=None),
    user_id: str = Depends(get_authenticated_user_id),
    use_case: GetWatchlistUseCase = Depends(get_list_use_case),
) -> list[WatchlistItemSchema]:
    return [_to_schema(item) for item in use_case.execute(user_id, list_name)]


def get_triage_use_case(
    watchlist_repo: SqlAlchemyWatchlistRepository = Depends(get_watchlist_repository),
    data_provider=Depends(get_data_provider),
    valuation_use_case=Depends(get_company_valuation_use_case),
) -> TriageWatchlistUseCase:
    return TriageWatchlistUseCase(
        watchlist_repo,
        data_provider,
        SqlAlchemyPriceSnapshotRepository(),
        valuation_use_case=valuation_use_case,
    )


def get_news_use_case(
    watchlist_repo: SqlAlchemyWatchlistRepository = Depends(get_watchlist_repository),
    data_provider=Depends(get_data_provider),
) -> GetWatchlistNewsUseCase:
    return GetWatchlistNewsUseCase(watchlist_repo, data_provider)


@router.get("/triage", response_model=TriageResponseSchema)
def triage_watchlist(
    list_name: str | None = Query(default=None),
    user_id: str = Depends(get_authenticated_user_id),
    use_case: TriageWatchlistUseCase = Depends(get_triage_use_case),
) -> TriageResponseSchema:
    result = use_case.execute(user_id, list_name)
    return TriageResponseSchema(
        as_of=result.as_of,
        scoring_note=(
            "triage_score is an ATTENTION ranking — higher means more "
            "attention-worthy, not better quality or a buy signal."
        ),
        items=[
            TriageItemSchema(
                ticker=t.ticker,
                list_name=t.list_name,
                triage_score=round(t.triage_score, 2),
                signals=TriageSignalsSchema(
                    day_move_pct=t.signals.day_move_pct,
                    move_since_added_pct=t.signals.move_since_added_pct,
                    momentum_1m_pct=t.signals.momentum_1m_pct,
                    pe_drift_pct=t.signals.pe_drift_pct,
                    target_crossed=t.signals.target_crossed,
                    current_price=t.signals.current_price,
                    current_pe=t.signals.current_pe,
                ),
                notes=t.notes,
            )
            for t in result.items
        ],
        tickers_excluded=result.tickers_excluded,
    )


@router.get("/news", response_model=WatchlistNewsResponseSchema)
def watchlist_news(
    list_name: str | None = Query(default=None),
    limit_per_ticker: int = Query(default=5, ge=1, le=20),
    user_id: str = Depends(get_authenticated_user_id),
    use_case: GetWatchlistNewsUseCase = Depends(get_news_use_case),
) -> WatchlistNewsResponseSchema:
    by_ticker, failed = use_case.execute(
        user_id, list_name=list_name, limit_per_ticker=limit_per_ticker
    )
    return WatchlistNewsResponseSchema(
        news={
            t: [
                NewsArticleSchema(
                    ticker=a.ticker, title=a.title, published_at=a.published_at,
                    source=a.source, url=a.url, snippet=a.snippet,
                )
                for a in articles
            ]
            for t, articles in by_ticker.items()
        },
        tickers_failed=failed,
    )
