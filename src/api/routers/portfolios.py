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
    HedgingPlanSchema,
    HedgingSuggestionSchema,
    OptionHoldingRemoveRequestSchema,
    OptionHoldingRequestSchema,
    OptionHoldingResultSchema,
    OptionPortfolioValuationSchema,
    OptionPositionSchema,
    PairwiseCorrelationSchema,
    PortfolioGreeksSchema,
    RebalancePlanSchema,
    RebalanceSuggestionSchema,
    RecommendationPickSchema,
    RecommendationsSchema,
    RiskParityAllocationSchema,
    RiskParityRequestSchema,
    RiskParityConstructionResponseSchema,
    PortfolioHoldingSchema,
    PortfolioRiskAnalysisSchema,
    PortfolioSchema,
    PortfolioValuationSchema,
    PositionValueSchema,
    SectorExposureSchema,
)
from src.application.interfaces.data_provider import DataProviderError
from src.application.interfaces.options_data_provider import OptionsDataProviderError
from src.application.use_cases.compute_option_portfolio_valuation import (
    ComputeOptionPortfolioValuationUseCase,
)
from src.application.use_cases.compute_portfolio_greeks import ComputePortfolioGreeksUseCase
from src.application.use_cases.manage_option_holdings import (
    AddOptionHoldingUseCase,
    InvalidOptionTypeError,
    RemoveOptionHoldingUseCase,
)
from src.application.use_cases.recommend_stocks import RecommendStocksUseCase
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.application.use_cases.suggest_hedging import SuggestHedgingUseCase
from src.application.use_cases.suggest_rebalancing import SuggestRebalancingUseCase
from src.application.use_cases.construct_risk_parity_portfolio import (
    ConstructRiskParityPortfolioUseCase,
    InvalidInvestmentAmountError,
    NoAllocatableTickersError,
    NoTickersProvidedError,
)
from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
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
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.data_providers.marketdata_app_provider import MarketDataAppProvider
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.financial_statement_repository_impl import (
    SqlAlchemyFinancialStatementRepository,
)
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
    return ComputePortfolioRiskUseCase(valuation_use_case, analysis_use_case, company_repo, provider)


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
        portfolio_daily_volatility=result.portfolio_daily_volatility,
        portfolio_annualized_volatility=result.portfolio_annualized_volatility,
        parametric_var_95_1day_dollar=result.parametric_var_95_1day_dollar,
        volatility_covered_weight=result.volatility_covered_weight,
        volatility_lookback_days_used=result.volatility_lookback_days_used,
        pairwise_correlations=[
            PairwiseCorrelationSchema(ticker_a=c.ticker_a, ticker_b=c.ticker_b, correlation=c.correlation)
            for c in result.pairwise_correlations
        ],
        excluded_from_volatility_calc=result.excluded_from_volatility_calc,
    )


def get_risk_parity_use_case(
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> ConstructRiskParityPortfolioUseCase:
    return ConstructRiskParityPortfolioUseCase(provider)


@router.post("/construct-risk-parity", response_model=RiskParityConstructionResponseSchema)
def construct_risk_parity(
    body: RiskParityRequestSchema,
    user_id: str = Depends(get_authenticated_user_id),
    use_case: ConstructRiskParityPortfolioUseCase = Depends(get_risk_parity_use_case),
) -> RiskParityConstructionResponseSchema:
    try:
        result = use_case.execute(body.tickers, body.total_investment)
    except (NoTickersProvidedError, InvalidInvestmentAmountError, NoAllocatableTickersError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RiskParityConstructionResponseSchema(
        as_of=result.as_of,
        total_investment=result.total_investment,
        allocations=[
            RiskParityAllocationSchema(
                ticker=a.ticker,
                daily_volatility=a.daily_volatility,
                target_weight=a.target_weight,
                target_dollar_amount=a.target_dollar_amount,
                current_price=a.current_price,
                suggested_shares=a.suggested_shares,
            )
            for a in result.allocations
        ],
        excluded=result.excluded,
        methodology_note=result.methodology_note,
    )


# --- Options subsystem -------------------------------------------------------

def get_options_provider() -> MarketDataAppProvider:
    return MarketDataAppProvider(settings=get_settings())


def get_add_option_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
) -> AddOptionHoldingUseCase:
    return AddOptionHoldingUseCase(repo)


def get_remove_option_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
) -> RemoveOptionHoldingUseCase:
    return RemoveOptionHoldingUseCase(repo)


def get_greeks_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    options_provider: MarketDataAppProvider = Depends(get_options_provider),
) -> ComputePortfolioGreeksUseCase:
    return ComputePortfolioGreeksUseCase(repo, options_provider)


def get_option_valuation_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    options_provider: MarketDataAppProvider = Depends(get_options_provider),
) -> ComputeOptionPortfolioValuationUseCase:
    return ComputeOptionPortfolioValuationUseCase(repo, options_provider)


def get_hedging_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    options_provider: MarketDataAppProvider = Depends(get_options_provider),
) -> SuggestHedgingUseCase:
    return SuggestHedgingUseCase(repo, options_provider)


@router.post("/{portfolio_id}/options", response_model=OptionHoldingResultSchema)
def add_option_holding(
    portfolio_id: str,
    body: OptionHoldingRequestSchema,
    user_id: str = Depends(get_authenticated_user_id),
    get_use_case: GetPortfolioUseCase = Depends(get_get_use_case),
    use_case: AddOptionHoldingUseCase = Depends(get_add_option_use_case),
) -> OptionHoldingResultSchema:
    _verify_ownership(portfolio_id, user_id, get_use_case)
    try:
        holding = use_case.execute(
            portfolio_id, body.underlying_ticker, body.strike, body.expiration,
            body.option_type, body.contracts_held, body.cost_basis_per_contract,
        )
    except InvalidOptionTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OptionHoldingResultSchema(
        underlying_ticker=holding.contract.underlying_ticker,
        strike=holding.contract.strike,
        expiration=holding.contract.expiration,
        option_type=holding.contract.option_type,
        contracts_held=holding.contracts_held,
        status="added",
    )


@router.delete("/{portfolio_id}/options")
def remove_option_holding(
    portfolio_id: str,
    body: OptionHoldingRemoveRequestSchema,
    user_id: str = Depends(get_authenticated_user_id),
    get_use_case: GetPortfolioUseCase = Depends(get_get_use_case),
    use_case: RemoveOptionHoldingUseCase = Depends(get_remove_option_use_case),
) -> dict[str, str]:
    _verify_ownership(portfolio_id, user_id, get_use_case)
    try:
        removed = use_case.execute(
            portfolio_id, body.underlying_ticker, body.strike, body.expiration, body.option_type,
        )
    except InvalidOptionTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="No matching option position found to remove.")
    return {"status": "removed"}


@router.get("/{portfolio_id}/options/greeks", response_model=PortfolioGreeksSchema)
def get_portfolio_greeks(
    portfolio_id: str,
    user_id: str = Depends(get_authenticated_user_id),
    get_use_case: GetPortfolioUseCase = Depends(get_get_use_case),
    use_case: ComputePortfolioGreeksUseCase = Depends(get_greeks_use_case),
) -> PortfolioGreeksSchema:
    _verify_ownership(portfolio_id, user_id, get_use_case)
    try:
        result = use_case.execute(portfolio_id)
    except OptionsDataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PortfolioGreeksSchema(
        total_delta=result.total_delta, total_gamma=result.total_gamma,
        total_theta=result.total_theta, total_vega=result.total_vega,
        positions_included=result.positions_included, positions_excluded=result.positions_excluded,
    )


@router.get("/{portfolio_id}/options/valuation", response_model=OptionPortfolioValuationSchema)
def get_option_portfolio_valuation(
    portfolio_id: str,
    user_id: str = Depends(get_authenticated_user_id),
    get_use_case: GetPortfolioUseCase = Depends(get_get_use_case),
    use_case: ComputeOptionPortfolioValuationUseCase = Depends(get_option_valuation_use_case),
) -> OptionPortfolioValuationSchema:
    _verify_ownership(portfolio_id, user_id, get_use_case)
    try:
        result = use_case.execute(portfolio_id)
    except OptionsDataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return OptionPortfolioValuationSchema(
        total_market_value=result.total_market_value,
        total_cost_basis=result.total_cost_basis,
        total_unrealized_gain=result.total_unrealized_gain,
        total_unrealized_gain_pct=result.total_unrealized_gain_pct,
        positions=[
            OptionPositionSchema(
                contract=p.contract.occ_symbol_fragment, contracts_held=p.contracts_held,
                current_price=p.current_price, market_value=p.market_value,
                unrealized_gain=p.unrealized_gain, unrealized_gain_pct=p.unrealized_gain_pct,
            )
            for p in result.positions
        ],
        positions_excluded=result.positions_excluded,
    )


@router.get("/{portfolio_id}/options/hedging-suggestion", response_model=HedgingPlanSchema)
def get_hedging_suggestion(
    portfolio_id: str,
    user_id: str = Depends(get_authenticated_user_id),
    get_use_case: GetPortfolioUseCase = Depends(get_get_use_case),
    use_case: SuggestHedgingUseCase = Depends(get_hedging_use_case),
) -> HedgingPlanSchema:
    _verify_ownership(portfolio_id, user_id, get_use_case)
    try:
        plan = use_case.execute(portfolio_id)
    except OptionsDataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not plan.suggestions:
        return HedgingPlanSchema(
            suggestions=[], positions_excluded=plan.positions_excluded,
            note="No underlying has meaningful net delta exposure — nothing to hedge.",
        )
    return HedgingPlanSchema(
        suggestions=[
            HedgingSuggestionSchema(
                underlying_ticker=s.underlying_ticker, net_delta=s.net_delta,
                shares_to_trade=s.shares_to_trade, resulting_delta=s.resulting_delta,
            )
            for s in plan.suggestions
        ],
        positions_excluded=plan.positions_excluded,
    )


# --- Recommendations / rebalancing ------------------------------------------

def get_recommend_use_case(
    portfolio_repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
    analysis_use_case: ComputeFinancialAnalysisUseCase = Depends(get_analysis_use_case),
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
) -> RecommendStocksUseCase:
    valuation_use_case = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_risk = ComputePortfolioRiskUseCase(valuation_use_case, analysis_use_case, company_repo, provider)
    compute_company_valuation = ComputeValuationUseCase(
        GetCompanyFinancialsUseCase(company_repo, SqlAlchemyFinancialStatementRepository()), provider
    )
    screen_stocks = ScreenStocksUseCase(compute_company_valuation, analysis_use_case)
    return RecommendStocksUseCase(compute_risk, company_repo, screen_stocks)


def get_rebalance_use_case(
    repo: SqlAlchemyPortfolioRepository = Depends(get_portfolio_repository),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> SuggestRebalancingUseCase:
    valuation_use_case = ComputePortfolioValuationUseCase(repo, provider)
    return SuggestRebalancingUseCase(valuation_use_case)


@router.get("/{portfolio_id}/recommendations", response_model=RecommendationsSchema)
def get_recommendations(
    portfolio_id: str,
    max_recommendations: int = Query(default=5, ge=1, le=15),
    user_id: str = Depends(get_authenticated_user_id),
    get_use_case: GetPortfolioUseCase = Depends(get_get_use_case),
    use_case: RecommendStocksUseCase = Depends(get_recommend_use_case),
) -> RecommendationsSchema:
    _verify_ownership(portfolio_id, user_id, get_use_case)
    result = use_case.execute(portfolio_id, max_recommendations)
    if not result.gap_sectors:
        return RecommendationsSchema(
            gap_sectors=[], picks=[],
            note="Portfolio already has meaningful exposure across all sectors — no gaps to fill.",
        )
    return RecommendationsSchema(
        gap_sectors=result.gap_sectors,
        scoring_note="Within picks, lower value_score/quality_score/composite_score is better.",
        picks=[
            RecommendationPickSchema(
                ticker=p.stock.ticker, gap_sector=p.gap_sector,
                current_sector_weight=p.current_sector_weight, price=p.stock.price,
                price_to_earnings=p.stock.price_to_earnings, return_on_equity=p.stock.return_on_equity,
                composite_score=p.stock.composite_score,
            )
            for p in result.picks
        ],
    )


@router.get("/{portfolio_id}/rebalance-suggestion", response_model=RebalancePlanSchema)
def get_rebalance_suggestion(
    portfolio_id: str,
    target_max_weight: float = Query(default=0.30, gt=0, le=1),
    user_id: str = Depends(get_authenticated_user_id),
    get_use_case: GetPortfolioUseCase = Depends(get_get_use_case),
    use_case: SuggestRebalancingUseCase = Depends(get_rebalance_use_case),
) -> RebalancePlanSchema:
    _verify_ownership(portfolio_id, user_id, get_use_case)
    plan = use_case.execute(portfolio_id, target_max_weight)
    if not plan.suggestions:
        return RebalancePlanSchema(
            target_max_weight=plan.target_max_weight, suggestions=[],
            note="No position exceeds the target weight — nothing to suggest.",
        )
    return RebalancePlanSchema(
        target_max_weight=plan.target_max_weight,
        suggestions=[
            RebalanceSuggestionSchema(
                ticker=s.ticker, current_weight=s.current_weight, target_weight=s.target_weight,
                shares_to_trim=s.shares_to_trim, estimated_proceeds=s.estimated_proceeds,
            )
            for s in plan.suggestions
        ],
    )
