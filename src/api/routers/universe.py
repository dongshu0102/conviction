"""Curated investment universe API routes — GLOBAL themes, shared across
every user. Not gated behind get_authenticated_user_id ownership checks
the way watchlists are, since themes are system-wide data, not personal.
API key auth still applies at the app level; there is simply no
per-user scoping to enforce here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.routers.companies import get_company_repository, get_data_provider
from src.api.routers.companies import (
    get_analysis_use_case,
    get_valuation_use_case,
)
from src.api.schemas import (
    SuggestedTickerSchema,
    ThemeSuggestionSchema,
    ThemeSynthesisReportSchema,
    ThemeTickersSchema,
    UniverseThemeListSchema,
    UniverseThemeSchema,
    UniverseThemeSummarySchema,
)
from src.application.use_cases.generate_theme_synthesis import GenerateThemeSynthesisUseCase
from src.application.use_cases.get_factor_scores import (
    FactorSnapshotNotReadyError,
    GetFactorScoresUseCase,
)
from src.application.use_cases.compute_universe_factor_snapshot import (
    ComputeUniverseFactorSnapshotUseCase,
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
from src.application.use_cases.generate_theme_synthesis import (
    NoSynthesizableDataError,
    ThemeEmptyError,
)
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.application.use_cases.suggest_theme import (
    GeneralNewsUnavailableError,
    NoNewsAvailableError,
    SuggestThemeUseCase,
)
from src.infrastructure.llm_providers.anthropic_theme_suggestion_generator import (
    AnthropicThemeSuggestionGenerator,
)
from src.infrastructure.llm_providers.anthropic_theme_synthesis_generator import (
    AnthropicThemeSynthesisGenerator,
)
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.factor_score_repository_impl import (
    SqlAlchemyFactorScoreRepository,
)
from src.infrastructure.persistence.universe_theme_repository_impl import (
    SqlAlchemyUniverseThemeRepository,
)
from src.infrastructure.config import get_settings

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


def get_theme_synthesis_use_case(
    theme_repo: SqlAlchemyUniverseThemeRepository = Depends(get_theme_repository),
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
    data_provider=Depends(get_data_provider),
    valuation_use_case=Depends(get_valuation_use_case),
    analysis_use_case=Depends(get_analysis_use_case),
) -> GenerateThemeSynthesisUseCase:
    get_theme_tickers = GetThemeTickersUseCase(theme_repo)
    screen_stocks = ScreenStocksUseCase(valuation_use_case, analysis_use_case)
    factor_repo = SqlAlchemyFactorScoreRepository()
    get_factor_scores = GetFactorScoresUseCase(
        factor_repo,
        ComputeUniverseFactorSnapshotUseCase(
            data_provider, valuation_use_case, analysis_use_case, factor_repo
        ),
    )
    return GenerateThemeSynthesisUseCase(
        theme_repo, get_theme_tickers, screen_stocks, get_factor_scores,
        AnthropicThemeSynthesisGenerator(get_settings()),
    )


@router.post("/themes/{name}/synthesis", response_model=ThemeSynthesisReportSchema)
def generate_synthesis(
    name: str,
    use_case: GenerateThemeSynthesisUseCase = Depends(get_theme_synthesis_use_case),
) -> ThemeSynthesisReportSchema:
    try:
        report = use_case.execute(name)
    except FactorSnapshotNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ThemeNotFoundError, ThemeEmptyError, NoSynthesizableDataError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ThemeSynthesisReportSchema(
        theme_name=report.theme_name,
        generated_at=report.generated_at,
        tickers_covered=report.tickers_covered,
        tickers_excluded=report.tickers_excluded,
        overview=report.overview,
        common_threads=report.common_threads,
        notable_divergences=report.notable_divergences,
        key_risks=report.key_risks,
        model_used=report.model_used,
    )


def get_theme_suggestion_use_case(
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
    data_provider=Depends(get_data_provider),
) -> SuggestThemeUseCase:
    return SuggestThemeUseCase(
        data_provider, company_repo, AnthropicThemeSuggestionGenerator(get_settings())
    )


@router.post("/suggest-theme", response_model=ThemeSuggestionSchema)
def suggest_theme(
    user_hint: str | None = None,
    use_case: SuggestThemeUseCase = Depends(get_theme_suggestion_use_case),
) -> ThemeSuggestionSchema:
    try:
        suggestion = use_case.execute(user_hint)
    except (GeneralNewsUnavailableError, NoNewsAvailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ThemeSuggestionSchema(
        theme_name=suggestion.theme_name,
        rationale=suggestion.rationale,
        candidate_tickers=[
            SuggestedTickerSchema(
                ticker=t.ticker, company_name=t.company_name,
                reasoning=t.reasoning, already_ingested=t.already_ingested,
            )
            for t in suggestion.candidate_tickers
        ],
        sourced_headlines=suggestion.sourced_headlines,
        generated_at=suggestion.generated_at,
        model_used=suggestion.model_used,
    )
