"""Portfolio API routes.

Every route requires a valid API key. Routes touching a SPECIFIC
portfolio (get/delete/holdings/valuation/risk) additionally verify the
authenticated user owns that portfolio — this was a real gap being
closed here, not just cosmetic: previously these routes took no user_id
at all, so anyone who obtained a portfolio_id (a UUID, hard to guess but
not verified against anything) could view, modify, or delete it. 404 is
returned for both "doesn't exist" and "exists but isn't yours" — this is
deliberate: a 403 would confirm the portfolio exists, leaking
information to someone who shouldn't have it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth import get_authenticated_user_id
from src.api.routers.companies import (
    get_analysis_use_case,
    get_company_repository,
    get_data_provider,
)
from src.api.schemas import (
    PortfolioHoldingSchema,
    PortfolioRiskAnalysisSchema,
    PortfolioSchema,
    PortfolioValuationSchema,
    PositionValueSchema,
    SectorExposureSchema,
)
from src.application.interfaces.data_provider import DataProviderError
from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.manage_portfolio import (
    AddHoldingUseCase,
    CreatePortfolioUseCase,
    DeletePortfolioUseCase,
    GetPortfolioUseCase,
    ListPortfoliosUseCase,
    PortfolioNotFoundError,
    RemoveHoldingUseCase,
    TickerNotIngestedError,
)
from src.domain.entities.portfolio import Portfolio
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.portfolio_repository_impl import (
    SqlAlchemyPortfolioRepository,
)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


def get_portfolio_repository() -> SqlAlchemyPortfolioRepository:
    return SqlAlchemyPortfolioRepository()


def get_create_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
) -> CreatePortfolioUseCase:
    return CreatePortfolioUseCase(repo)


def get_list_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
) -> ListPortfoliosUseCase:
    return ListPortfoliosUseCase(repo)


def get_get_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
) -> GetPortfolioUseCase:
    return GetPortfolioUseCase(repo)


def get_delete_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
) -> DeletePortfolioUseCase:
    return DeletePortfolioUseCase(repo)


def get_add_holding_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
) -> AddHoldingUseCase:
    return AddHoldingUseCase(repo, company_repo)


def get_remove_holding_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
) -> RemoveHoldingUseCase:
    return RemoveHoldingUseCase(repo)


def get_valuation_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> ComputePortfolioValuationUseCase:
    return ComputePortfolioValuationUseCase(repo, provider)


def get_risk_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
    analysis_use_case: ComputeFinancialAnalysisUseCase = Depends(get_analysis_use_case),
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
) -> ComputePortfolioRiskUseCase:
    valuation_use_case = ComputePortfolioValuationUseCase(repo, provider)
    return ComputePortfolioRiskUseCase(valuation_use_case, analysis_use_case, company_repo)


def _verify_ownership(
    portfolio_id: str, user_id: str, get_use_case: GetPortfolioUseCase
) -> Portfolio:
    """Fetches the portfolio and confirms the authenticated user owns it.
    Raises 404 (not 403) whether the portfolio doesn't exist OR belongs
    to someone else — see module docstring for why that's deliberate.
    """
    try:
        portfolio = get_use_case.execute(portfolio_id)
    except PortfolioNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if portfolio.user_id != user_id:
        raise HTTPException(
            status_code=404, detail=f"No portfolio found with id '{portfolio_id}'"
        )
    return portfolio


def _to_schema(portfolio) -> PortfolioSchema:
    return PortfolioSchema(
        portfolio_id=portfolio.portfolio_id,
        user_id=portfolio.user_id,
        name=portfolio.name,
        created_at=portfolio.created_at,
        holdings=[
            PortfolioHoldingSchema(
                ticker=h.ticker, shares=h.shares,
                cost_basis_per_share=h.cost_basis_per_share, acquired_at=h.acquired_at,
            )
            for h in portfolio.holdings
        ],
    )


@router.post("", response_model=PortfolioSchema)
def create_portfolio(
    name: str = Query(...),
    user_id: str = Depends(get_authenticated_user_id),
    use_case: CreatePortfolioUseCase = Depends(get_create_use_case),
) -> PortfolioSchema:
    return _to_schema(use_case.execute(user_id, name))


@router.get("", response_model=list[PortfolioSchema])
def list_portfolios(
    user_id: str = Depends(get_authenticated_user_id),
    use_case: ListPortfoliosUseCase = Depends(get_list_use_case),
) -> list[PortfolioSchema]:
    return [_to_schema(p) for p in use_case.execute(user_id)]


@router.get("/{portfolio_id}", response_model=PortfolioSchema)
def get_portfolio(
    portfolio_id: str,
    user_id: str = Depends(get_authenticated_user_id),
    use_case: GetPortfolioUseCase = Depends(get_get_use_case),
) -> PortfolioSchema:
    portfolio = _verify_ownership(portfolio_id, user_id, use_case)
    return _to_schema(portfolio)


@router.delete("/{portfolio_id}")
def delete_portfolio(
    portfolio_id: str,
    user_id: str = Depends(get_authenticated_user_id),
    get_use_case: GetPortfolioUseCase = Depends(get_get_use_case),
    delete_use_case: DeletePortfolioUseCase = Depends(get_delete_use_case),
) -> dict[str, bool]:
    _verify_ownership(portfolio_id, user_id, get_use_case)
    delete_use_case.execute(portfolio_id)
    return {"deleted": True}


@router.post("/{portfolio_id}/holdings/{ticker}", response_model=PortfolioHoldingSchema)
def add_holding(
    portfolio_id: str,
    ticker: str,
    shares: float = Query(..., gt=0),
    cost_basis_per_share: float = Query(..., ge=0),
    user_id: str = Depends(get_authenticated_user_id),
    get_use_case: GetPortfolioUseCase = Depends(get_get_use_case),
    use_case: AddHoldingUseCase = Depends(get_add_holding_use_case),
) -> PortfolioHoldingSchema:
    _verify_ownership(portfolio_id, user_id, get_use_case)
    try:
        holding = use_case.execute(portfolio_id, ticker, shares, cost_basis_per_share)
    except TickerNotIngestedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PortfolioHoldingSchema(
        ticker=holding.ticker, shares=holding.shares,
        cost_basis_per_share=holding.cost_basis_per_share, acquired_at=holding.acquired_at,
    )


@router.delete("/{portfolio_id}/holdings/{ticker}")
def remove_holding(
    portfolio_id: str,
    ticker: str,
    user_id: str = Depends(get_authenticated_user_id),
    get_use_case: GetPortfolioUseCase = Depends(get_get_use_case),
    remove_use_case: RemoveHoldingUseCase = Depends(get_remove_holding_use_case),
) -> dict[str, bool]:
    _verify_ownership(portfolio_id, user_id, get_use_case)
    removed = remove_use_case.execute(portfolio_id, ticker)
    if not removed:
        raise HTTPException(
            status_code=404, detail=f"'{ticker.upper()}' is not a holding in this portfolio"
        )
    return {"removed": True}


@router.get("/{portfolio_id}/valuation", response_model=PortfolioValuationSchema)
def get_portfolio_valuation(
    portfolio_id: str,
    user_id: str = Depends(get_authenticated_user_id),
    get_use_case: GetPortfolioUseCase = Depends(get_get_use_case),
    use_case: ComputePortfolioValuationUseCase = Depends(get_valuation_use_case),
) -> PortfolioValuationSchema:
    _verify_ownership(portfolio_id, user_id, get_use_case)
    try:
        result = use_case.execute(portfolio_id)
    except DataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return PortfolioValuationSchema(
        portfolio_id=result.portfolio_id,
        name=result.name,
        as_of=result.as_of,
        positions=[
            PositionValueSchema(
                ticker=p.ticker, shares=p.shares, cost_basis_per_share=p.cost_basis_per_share,
                current_price=p.current_price, market_value=p.market_value,
                cost_basis_total=p.cost_basis_total, unrealized_gain=p.unrealized_gain,
                unrealized_gain_pct=p.unrealized_gain_pct, weight=p.weight,
            )
            for p in result.positions
        ],
        total_market_value=result.total_market_value,
        total_cost_basis=result.total_cost_basis,
        total_unrealized_gain=result.total_unrealized_gain,
        total_unrealized_gain_pct=result.total_unrealized_gain_pct,
    )


@router.get("/{portfolio_id}/risk", response_model=PortfolioRiskAnalysisSchema)
def get_portfolio_risk(
    portfolio_id: str,
    user_id: str = Depends(get_authenticated_user_id),
    get_use_case: GetPortfolioUseCase = Depends(get_get_use_case),
    use_case: ComputePortfolioRiskUseCase = Depends(get_risk_use_case),
) -> PortfolioRiskAnalysisSchema:
    _verify_ownership(portfolio_id, user_id, get_use_case)
    try:
        result = use_case.execute(portfolio_id)
    except DataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return PortfolioRiskAnalysisSchema(
        portfolio_id=result.portfolio_id,
        as_of=result.as_of,
        largest_position_weight=result.largest_position_weight,
        herfindahl_index=result.herfindahl_index,
        sector_exposures=[
            SectorExposureSchema(sector=s.sector, weight=s.weight)
            for s in result.sector_exposures
        ],
        weighted_avg_debt_to_equity=result.weighted_avg_debt_to_equity,
        excluded_from_leverage_calc=result.excluded_from_leverage_calc,
    )
