"""Daily Brief API route. Requires a valid API key."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import get_authenticated_user_id
from src.api.routers.alerts import get_alert_repository, get_snapshot_repository
from src.api.routers.companies import (
    get_analysis_use_case,
    get_company_repository,
    get_data_provider,
)
from src.api.routers.portfolios import get_portfolio_repository
from src.api.routers.watchlist import get_watchlist_repository
from src.api.schemas import (
    DailyBriefSchema,
    PortfolioBriefSummarySchema,
    WatchlistPriceMoveSchema,
)
from src.application.interfaces.brief_generator import BriefGenerationError
from src.application.interfaces.data_provider import DataProviderError
from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.generate_daily_brief import GenerateDailyBriefUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.llm_providers.anthropic_brief_generator import (
    AnthropicBriefGenerator,
)
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.financial_statement_repository_impl import (
    SqlAlchemyFinancialStatementRepository,
)
from src.infrastructure.persistence.portfolio_repository_impl import (
    SqlAlchemyPortfolioRepository,
)
from src.infrastructure.persistence.watchlist_repository_impl import (
    SqlAlchemyWatchlistRepository,
)

router = APIRouter(prefix="/brief", tags=["brief"])


def get_brief_generator() -> AnthropicBriefGenerator:
    return AnthropicBriefGenerator(settings=get_settings())


def get_daily_brief_use_case(
    watchlist_repo: SqlAlchemyWatchlistRepository = Depends(get_watchlist_repository),
    snapshot_repo=Depends(get_snapshot_repository),
    alert_repo=Depends(get_alert_repository),
    portfolio_repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
    analysis_use_case: ComputeFinancialAnalysisUseCase = Depends(get_analysis_use_case),
    brief_generator: AnthropicBriefGenerator = Depends(get_brief_generator),
) -> GenerateDailyBriefUseCase:
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_risk = ComputePortfolioRiskUseCase(compute_valuation, analysis_use_case, company_repo, provider)
    return GenerateDailyBriefUseCase(
        watchlist_repo, snapshot_repo, alert_repo, portfolio_repo, provider,
        compute_valuation, compute_risk, brief_generator,
    )


@router.get("", response_model=DailyBriefSchema)
def get_daily_brief(
    user_id: str = Depends(get_authenticated_user_id),
    use_case: GenerateDailyBriefUseCase = Depends(get_daily_brief_use_case),
) -> DailyBriefSchema:
    try:
        brief = use_case.execute(user_id)
    except BriefGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except DataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return DailyBriefSchema(
        user_id=brief.user_id,
        generated_at=brief.generated_at,
        narrative=brief.narrative,
        model_used=brief.model_used,
        unread_alert_count=brief.unread_alert_count,
        watchlist_moves=[
            WatchlistPriceMoveSchema(
                ticker=m.ticker, current_price=m.current_price,
                prior_price=m.prior_price, change_pct=m.change_pct,
            )
            for m in brief.watchlist_moves
        ],
        portfolio_summaries=[
            PortfolioBriefSummarySchema(
                portfolio_id=p.portfolio_id, name=p.name,
                total_market_value=p.total_market_value,
                total_unrealized_gain_pct=p.total_unrealized_gain_pct,
                largest_position_weight=p.largest_position_weight,
                herfindahl_index=p.herfindahl_index,
            )
            for p in brief.portfolio_summaries
        ],
    )
