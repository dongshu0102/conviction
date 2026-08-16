from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.schemas import (
    BalanceSheetSchema,
    CompsResponseSchema,
    DcfAssumptionsSchema,
    DcfProjectionYearSchema,
    DcfResponseSchema,
    EconomicIndicatorSchema,
    EtfIngestResultSchema,
    FactorRankingResponseSchema,
    FactorRawMetricsSchema,
    FactorScoreResponseSchema,
    GeneralNewsHeadlineSchema,
    IrrResponseSchema,
    IrrScenarioSchema,
    MacroSnapshotSchema,
    MarketRiskPremiumSchema,
    RankedFactorScoreSchema,
    RateSignalsSchema,
    SahmRuleResultSchema,
    CashFlowStatementSchema,
    CompanyFinancialAnalysisSchema,
    CompanyFinancialsSchema,
    CompanyListItemSchema,
    CompanyListResponseSchema,
    CompanySchema,
    IncomeStatementSchema,
    IngestResultSchema,
    NewsArticleSchema,
    ReverseDcfAssumptionsSchema,
    ReverseDcfResponseSchema,
    ScreenedStockSchema,
    ScreenRequestSchema,
    ScreenResultSchema,
    SP500ConstituentsSchema,
    TaylorRuleResultSchema,
    TreasuryRatesSchema,
    ValuationSnapshotSchema,
    YearlyRatiosSchema,
    YieldCurveReadingSchema,
)
from src.application.interfaces.data_provider import DataProviderError
from src.application.use_cases.compute_comps_valuation import (
    CompsMetric,
    ComputeCompsValuationUseCase,
    InsufficientPeerDataError,
    InsufficientTargetDataError,
)
from src.application.use_cases.compute_dcf_valuation import (
    ComputeDcfUseCase,
    ComputeReverseDcfUseCase,
    InsufficientDataError,
)
from src.application.use_cases.compute_investment_irr import (
    ComputeInvestmentIrrUseCase,
    InvalidIrrScenarioError,
)
from src.application.use_cases.get_macro_snapshot import GetMacroSnapshotUseCase
from src.application.use_cases.get_rate_signals import GetRateSignalsUseCase
from src.application.use_cases.get_risk_free_rate import GetRiskFreeRateUseCase
from src.domain.services.valuation_math import DcfAssumptionError
from src.application.use_cases.manage_universe_theme import GetThemeTickersUseCase
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.infrastructure.persistence.universe_theme_repository_impl import (
    SqlAlchemyUniverseThemeRepository,
)
from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_universe_factor_snapshot import (
    ComputeUniverseFactorSnapshotUseCase,
)
from src.application.use_cases.compute_valuation import (
    ComputeValuationUseCase,
    NoFinancialDataError as NoValuationDataError,
)
from src.application.use_cases.get_factor_scores import (
    FactorSnapshotNotReadyError,
    GetFactorScoresUseCase,
)
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.application.use_cases.ingest_company_data import IngestCompanyDataUseCase
from src.application.use_cases.ingest_etf_data import (
    EtfLookupUnavailableError,
    EtfNotFoundError,
    IngestEtfDataUseCase,
)
from src.domain.entities.financial_statement import Period
from src.infrastructure.config import get_settings
from src.domain.entities.factor_scores import FactorWeights
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.data_providers.fred_provider import FredProvider
from src.infrastructure.persistence.company_repository_impl import (
    SqlAlchemyCompanyRepository,
)
from src.infrastructure.persistence.factor_score_repository_impl import (
    SqlAlchemyFactorScoreRepository,
)
from src.infrastructure.persistence.financial_statement_repository_impl import (
    SqlAlchemyFinancialStatementRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/companies", tags=["companies"])


# --- Dependency wiring -------------------------------------------------
# Simple factory functions, not a DI framework. At MVP scale this is the
# right amount of ceremony; if wiring grows complex (Phase 2+, once agents
# depend on many use cases) we introduce a proper container.

def get_company_repository() -> SqlAlchemyCompanyRepository:
    return SqlAlchemyCompanyRepository()


def get_statement_repository() -> SqlAlchemyFinancialStatementRepository:
    return SqlAlchemyFinancialStatementRepository()


def get_data_provider() -> FinancialModelingPrepProvider:
    return FinancialModelingPrepProvider(settings=get_settings())


def get_fred_provider() -> FredProvider:
    return FredProvider(settings=get_settings())


def get_ingest_use_case(
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
    statement_repo: SqlAlchemyFinancialStatementRepository = Depends(get_statement_repository),
) -> IngestCompanyDataUseCase:
    return IngestCompanyDataUseCase(provider, company_repo, statement_repo)


def get_financials_use_case(
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
    statement_repo: SqlAlchemyFinancialStatementRepository = Depends(get_statement_repository),
) -> GetCompanyFinancialsUseCase:
    return GetCompanyFinancialsUseCase(company_repo, statement_repo)


def get_analysis_use_case(
    get_financials: GetCompanyFinancialsUseCase = Depends(get_financials_use_case),
) -> ComputeFinancialAnalysisUseCase:
    return ComputeFinancialAnalysisUseCase(get_financials)


def get_valuation_use_case(
    get_financials: GetCompanyFinancialsUseCase = Depends(get_financials_use_case),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> ComputeValuationUseCase:
    return ComputeValuationUseCase(get_financials, provider)


def get_dcf_use_case(
    get_financials: GetCompanyFinancialsUseCase = Depends(get_financials_use_case),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> ComputeDcfUseCase:
    return ComputeDcfUseCase(get_financials, provider)


def get_reverse_dcf_use_case(
    get_financials: GetCompanyFinancialsUseCase = Depends(get_financials_use_case),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> ComputeReverseDcfUseCase:
    return ComputeReverseDcfUseCase(get_financials, provider)


def get_irr_use_case(
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> ComputeInvestmentIrrUseCase:
    return ComputeInvestmentIrrUseCase(provider)


def get_comps_use_case(
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
    get_financials: GetCompanyFinancialsUseCase = Depends(get_financials_use_case),
    valuation: ComputeValuationUseCase = Depends(get_valuation_use_case),
) -> ComputeCompsValuationUseCase:
    return ComputeCompsValuationUseCase(company_repo, get_financials, valuation)


def get_risk_free_rate_use_case(
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> GetRiskFreeRateUseCase:
    return GetRiskFreeRateUseCase(provider)


def get_macro_snapshot_use_case(
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> GetMacroSnapshotUseCase:
    return GetMacroSnapshotUseCase(provider)


def get_rate_signals_use_case(
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
    fred: FredProvider = Depends(get_fred_provider),
) -> GetRateSignalsUseCase:
    return GetRateSignalsUseCase(provider, macro_history_provider=fred)


def get_factor_score_use_case(
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
    valuation: ComputeValuationUseCase = Depends(get_valuation_use_case),
    analysis: ComputeFinancialAnalysisUseCase = Depends(get_analysis_use_case),
) -> GetFactorScoresUseCase:
    factor_repo = SqlAlchemyFactorScoreRepository()
    return GetFactorScoresUseCase(
        factor_repo,
        ComputeUniverseFactorSnapshotUseCase(provider, valuation, analysis, factor_repo),
    )


def _weights_from_query(
    weight_value: float | None,
    weight_quality: float | None,
    weight_growth: float | None,
    weight_momentum: float | None,
    weight_size: float | None,
) -> FactorWeights:
    defaults = FactorWeights()
    return FactorWeights(
        value=weight_value if weight_value is not None else defaults.value,
        quality=weight_quality if weight_quality is not None else defaults.quality,
        growth=weight_growth if weight_growth is not None else defaults.growth,
        momentum=weight_momentum if weight_momentum is not None else defaults.momentum,
        size=weight_size if weight_size is not None else defaults.size,
    )


_FACTOR_SCORING_NOTE = (
    "Every z-score is standardized against the S&P 500 universe at the same "
    "point in time — positive always means 'more attractive than the "
    "universe average' on that factor. A null z-score means the underlying "
    "data was unavailable for this ticker, not that it scored exactly "
    "average."
)


def _to_ranked_schema(ranked) -> RankedFactorScoreSchema:
    return RankedFactorScoreSchema(
        ticker=ranked.ticker,
        as_of=ranked.score.as_of,
        composite_score=ranked.composite_score,
        factors_used=ranked.factors_used,
        value_z=ranked.score.z_scores.value,
        quality_z=ranked.score.z_scores.quality,
        growth_z=ranked.score.z_scores.growth,
        momentum_z=ranked.score.z_scores.momentum,
        size_z=ranked.score.z_scores.size,
        raw=FactorRawMetricsSchema(
            price_to_earnings=ranked.score.raw.price_to_earnings,
            return_on_equity=ranked.score.raw.return_on_equity,
            revenue_growth_yoy=ranked.score.raw.revenue_growth_yoy,
            momentum_1m_pct=ranked.score.raw.momentum_1m_pct,
            market_cap=ranked.score.raw.market_cap,
        ),
    )


@router.get("/{ticker}/factor-score", response_model=FactorScoreResponseSchema)
def get_factor_score(
    ticker: str,
    weight_value: float | None = Query(default=None),
    weight_quality: float | None = Query(default=None),
    weight_growth: float | None = Query(default=None),
    weight_momentum: float | None = Query(default=None),
    weight_size: float | None = Query(default=None),
    use_case: GetFactorScoresUseCase = Depends(get_factor_score_use_case),
) -> FactorScoreResponseSchema:
    weights = _weights_from_query(
        weight_value, weight_quality, weight_growth, weight_momentum, weight_size
    )
    try:
        ranked = use_case.execute_for_ticker(ticker, weights)
    except FactorSnapshotNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if ranked is None:
        raise HTTPException(
            status_code=404, detail=f"No factor score available for '{ticker.upper()}'."
        )
    return FactorScoreResponseSchema(scoring_note=_FACTOR_SCORING_NOTE, result=_to_ranked_schema(ranked))


@router.get("/factor-rankings", response_model=FactorRankingResponseSchema)
def rank_by_factors(
    top_n: int = Query(default=25, ge=1, le=503),
    weight_value: float | None = Query(default=None),
    weight_quality: float | None = Query(default=None),
    weight_growth: float | None = Query(default=None),
    weight_momentum: float | None = Query(default=None),
    weight_size: float | None = Query(default=None),
    use_case: GetFactorScoresUseCase = Depends(get_factor_score_use_case),
) -> FactorRankingResponseSchema:
    weights = _weights_from_query(
        weight_value, weight_quality, weight_growth, weight_momentum, weight_size
    )
    try:
        results = use_case.execute(weights)[:top_n]
    except FactorSnapshotNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FactorRankingResponseSchema(
        scoring_note=_FACTOR_SCORING_NOTE,
        results=[_to_ranked_schema(r) for r in results],
    )


# --- Routes --------------------------------------------------------------

@router.post("/{ticker}/ingest", response_model=IngestResultSchema)
def ingest_company(
    ticker: str,
    years: int = Query(default=5, ge=1, le=10),
    use_case: IngestCompanyDataUseCase = Depends(get_ingest_use_case),
) -> IngestResultSchema:
    try:
        result = use_case.execute(ticker, years=years)
    except DataProviderError as exc:
        logger.warning("Ingestion failed for %s: %s", ticker, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return IngestResultSchema(**asdict(result))


@router.post("/{ticker}/ingest-etf", response_model=EtfIngestResultSchema)
def ingest_etf(
    ticker: str,
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> EtfIngestResultSchema:
    use_case = IngestEtfDataUseCase(company_repo, provider)
    try:
        company = use_case.execute(ticker)
    except EtfNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EtfLookupUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return EtfIngestResultSchema(
        ticker=company.ticker, name=company.name,
        expense_ratio=company.expense_ratio, aum=company.aum,
    )


@router.get("/list-all", response_model=CompanyListResponseSchema)
def list_all_companies(
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
) -> CompanyListResponseSchema:
    """Every locally-ingested company's ticker and name -- deliberately
    NOT a live API call (unlike /sp500-constituents), since this is
    meant to back cheap, repeated frontend autocomplete, not to be a
    source of truth for current index membership. Registered before
    the dynamic /{ticker} route on purpose, same reasoning as
    /sp500-constituents's own comment."""
    companies = company_repo.list_all()
    return CompanyListResponseSchema(
        companies=[CompanyListItemSchema(ticker=c.ticker, name=c.name) for c in companies],
    )


@router.get("/sp500-constituents", response_model=SP500ConstituentsSchema)
def get_sp500_constituents(
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> SP500ConstituentsSchema:
    """Live, authoritative S&P 500 membership from FMP — deliberately NOT
    a static list, so index rebalances are reflected automatically rather
    than requiring a manual file update. Registered before the dynamic
    /{ticker} route on purpose: FastAPI matches routes in registration
    order, and without this ordering, a request to this exact path would
    incorrectly be captured by /{ticker} with ticker='sp500-constituents'.
    """
    try:
        tickers = provider.get_sp500_constituent_tickers()
    except DataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SP500ConstituentsSchema(tickers=tickers, count=len(tickers))


@router.get("/treasury-rates", response_model=TreasuryRatesSchema)
def get_treasury_rates(
    use_case: GetRiskFreeRateUseCase = Depends(get_risk_free_rate_use_case),
) -> TreasuryRatesSchema:
    """The real, current Treasury yield curve — the market's own
    proxy for the risk-free rate. Registered before /{ticker} for the
    same routing-order reason as /sp500-constituents above."""
    try:
        rates = use_case.execute()
    except (DataProviderError, NotImplementedError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    suggested_discount_rate = use_case.get_default_discount_rate()
    return TreasuryRatesSchema(
        as_of=rates.as_of, month1=rates.month1, month2=rates.month2, month3=rates.month3,
        month6=rates.month6, year1=rates.year1, year2=rates.year2, year3=rates.year3,
        year5=rates.year5, year7=rates.year7, year10=rates.year10, year20=rates.year20,
        year30=rates.year30, suggested_discount_rate=suggested_discount_rate,
    )


@router.get("/macro-snapshot", response_model=MacroSnapshotSchema)
def get_macro_snapshot(
    news_limit: int = Query(default=5),
    use_case: GetMacroSnapshotUseCase = Depends(get_macro_snapshot_use_case),
) -> MacroSnapshotSchema:
    """A combined macro picture — GDP, CPI, unemployment, the real US
    equity risk premium, and recent macro news, in one call. Every
    piece is fetched independently; a missing indicator or a down
    news feed returns null/empty for that piece rather than failing
    the whole request. Registered before /{ticker} for the same
    routing-order reason as /sp500-constituents above."""
    snapshot = use_case.execute(news_limit=news_limit)
    return MacroSnapshotSchema(
        as_of=snapshot.as_of,
        gdp=EconomicIndicatorSchema(name=snapshot.gdp.name, as_of=snapshot.gdp.as_of, value=snapshot.gdp.value) if snapshot.gdp else None,
        cpi=EconomicIndicatorSchema(name=snapshot.cpi.name, as_of=snapshot.cpi.as_of, value=snapshot.cpi.value) if snapshot.cpi else None,
        inflation_rate=(
            EconomicIndicatorSchema(name=snapshot.inflation_rate.name, as_of=snapshot.inflation_rate.as_of, value=snapshot.inflation_rate.value)
            if snapshot.inflation_rate else None
        ),
        unemployment_rate=(
            EconomicIndicatorSchema(name=snapshot.unemployment_rate.name, as_of=snapshot.unemployment_rate.as_of, value=snapshot.unemployment_rate.value)
            if snapshot.unemployment_rate else None
        ),
        risk_premium=(
            MarketRiskPremiumSchema(
                country=snapshot.risk_premium.country,
                country_risk_premium=snapshot.risk_premium.country_risk_premium,
                total_equity_risk_premium=snapshot.risk_premium.total_equity_risk_premium,
            ) if snapshot.risk_premium else None
        ),
        recent_news=[
            GeneralNewsHeadlineSchema(
                title=h.title, published_at=h.published_at, publisher=h.publisher,
                url=h.url, snippet=h.snippet,
            )
            for h in snapshot.recent_news
        ],
    )


@router.get("/rate-signals", response_model=RateSignalsSchema)
def get_rate_signals(
    neutral_real_rate: float | None = Query(default=None),
    target_inflation: float | None = Query(default=None),
    use_case: GetRateSignalsUseCase = Depends(get_rate_signals_use_case),
) -> RateSignalsSchema:
    """Three real, standard rate-direction/recession signals — yield
    curve inversion, the Taylor Rule, and the Sahm Rule — applied to
    real, live data. None of them predicts anything; all are tools
    professional economists and the Fed itself weigh as one input
    among several. Registered before /{ticker} for the same
    routing-order reason as /sp500-constituents above."""
    signals = use_case.execute(neutral_real_rate=neutral_real_rate, target_inflation=target_inflation)
    yc = signals.yield_curve
    tr = signals.taylor_rule
    sr = signals.sahm_rule
    return RateSignalsSchema(
        as_of=signals.as_of,
        yield_curve=YieldCurveReadingSchema(
            spread_10y_2y=yc.spread_10y_2y, spread_10y_3m=yc.spread_10y_3m,
            is_inverted=yc.is_inverted, interpretation=yc.interpretation,
        ),
        taylor_rule=(
            TaylorRuleResultSchema(
                target_rate=tr.target_rate, current_rate=tr.current_rate, gap=tr.gap,
                inflation_rate=tr.inflation_rate, output_gap_pct=tr.output_gap_pct,
                interpretation=tr.interpretation,
            ) if tr else None
        ),
        taylor_rule_unavailable_reason=signals.taylor_rule_unavailable_reason,
        sahm_rule=(
            SahmRuleResultSchema(
                current_3mo_avg=sr.current_3mo_avg, trailing_12mo_min_3mo_avg=sr.trailing_12mo_min_3mo_avg,
                gap=sr.gap, is_triggered=sr.is_triggered, interpretation=sr.interpretation,
            ) if sr else None
        ),
        sahm_rule_unavailable_reason=signals.sahm_rule_unavailable_reason,
    )


@router.get("/{ticker}", response_model=CompanyFinancialsSchema)
def get_company_financials(
    ticker: str,
    period: Period = Period.ANNUAL,
    years: int = Query(default=5, ge=1, le=10),
    use_case: GetCompanyFinancialsUseCase = Depends(get_financials_use_case),
) -> CompanyFinancialsSchema:
    try:
        financials = use_case.execute(ticker, period=period, years=years)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return CompanyFinancialsSchema(
        company=CompanySchema(
            ticker=financials.company.ticker,
            name=financials.company.name,
            sector=financials.company.sector.value,
            industry=financials.company.industry,
            exchange=financials.company.exchange,
            country=financials.company.country,
            ipo_date=financials.company.ipo_date,
            description=financials.company.description,
            website=financials.company.website,
            is_active=financials.company.is_active,
        ),
        income_statements=[
            IncomeStatementSchema(
                fiscal_year=s.key.fiscal_year,
                fiscal_quarter=s.key.fiscal_quarter,
                period=s.key.period.value,
                fiscal_date_ending=s.fiscal_date_ending,
                reported_currency=s.reported_currency,
                revenue=s.revenue,
                gross_profit=s.gross_profit,
                operating_income=s.operating_income,
                net_income=s.net_income,
                eps_diluted=s.eps_diluted,
                ebitda=s.ebitda,
            )
            for s in financials.income_statements
        ],
        balance_sheets=[
            BalanceSheetSchema(
                fiscal_year=s.key.fiscal_year,
                fiscal_quarter=s.key.fiscal_quarter,
                period=s.key.period.value,
                fiscal_date_ending=s.fiscal_date_ending,
                reported_currency=s.reported_currency,
                total_assets=s.total_assets,
                total_liabilities=s.total_liabilities,
                total_equity=s.total_equity,
                cash_and_equivalents=s.cash_and_equivalents,
                total_debt=s.total_debt,
            )
            for s in financials.balance_sheets
        ],
        cash_flow_statements=[
            CashFlowStatementSchema(
                fiscal_year=s.key.fiscal_year,
                fiscal_quarter=s.key.fiscal_quarter,
                period=s.key.period.value,
                fiscal_date_ending=s.fiscal_date_ending,
                reported_currency=s.reported_currency,
                operating_cash_flow=s.operating_cash_flow,
                capital_expenditures=s.capital_expenditures,
                free_cash_flow=s.free_cash_flow,
            )
            for s in financials.cash_flow_statements
        ],
    )


@router.get("/{ticker}/analysis", response_model=CompanyFinancialAnalysisSchema)
def get_financial_analysis(
    ticker: str,
    years: int = Query(default=5, ge=1, le=10),
    use_case: ComputeFinancialAnalysisUseCase = Depends(get_analysis_use_case),
) -> CompanyFinancialAnalysisSchema:
    try:
        analysis = use_case.execute(ticker, years=years)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return CompanyFinancialAnalysisSchema(
        ticker=analysis.ticker,
        yearly_ratios=[
            YearlyRatiosSchema(
                fiscal_year=r.fiscal_year,
                revenue_growth_yoy=r.revenue_growth_yoy,
                gross_margin=r.gross_margin,
                operating_margin=r.operating_margin,
                net_margin=r.net_margin,
                free_cash_flow_margin=r.free_cash_flow_margin,
                return_on_equity=r.return_on_equity,
                return_on_assets=r.return_on_assets,
                debt_to_equity=r.debt_to_equity,
                current_ratio=r.current_ratio,
            )
            for r in analysis.yearly_ratios
        ],
    )


@router.get("/{ticker}/valuation", response_model=ValuationSnapshotSchema)
def get_valuation(
    ticker: str,
    use_case: ComputeValuationUseCase = Depends(get_valuation_use_case),
) -> ValuationSnapshotSchema:
    try:
        result = use_case.execute(ticker)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoValuationDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ValuationSnapshotSchema(
        ticker=result.ticker,
        as_of=result.as_of,
        price=result.price,
        market_cap=result.market_cap,
        enterprise_value=result.enterprise_value,
        fundamentals_fiscal_year=result.fundamentals_fiscal_year,
        price_to_earnings=result.price_to_earnings,
        price_to_sales=result.price_to_sales,
        price_to_book=result.price_to_book,
        price_to_free_cash_flow=result.price_to_free_cash_flow,
        ev_to_ebitda=result.ev_to_ebitda,
    )


@router.get("/{ticker}/dcf", response_model=DcfResponseSchema)
def get_dcf(
    ticker: str,
    growth_rate: float | None = Query(default=None),
    discount_rate: float = Query(default=0.10),
    terminal_growth_rate: float = Query(default=0.025),
    years: int = Query(default=5),
    use_case: ComputeDcfUseCase = Depends(get_dcf_use_case),
) -> DcfResponseSchema:
    try:
        assessment = use_case.execute(
            ticker, growth_rate=growth_rate, discount_rate=discount_rate,
            terminal_growth_rate=terminal_growth_rate, years=years,
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DcfAssumptionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    a, r = assessment.assumptions, assessment.result
    return DcfResponseSchema(
        ticker=assessment.ticker, as_of=assessment.as_of,
        assumptions=DcfAssumptionsSchema(
            base_fcf=a.base_fcf, growth_rate=a.growth_rate,
            growth_rate_was_default=a.growth_rate_was_default,
            discount_rate=a.discount_rate, terminal_growth_rate=a.terminal_growth_rate,
            years=a.years, net_debt=a.net_debt, shares_outstanding=a.shares_outstanding,
        ),
        enterprise_value=r.enterprise_value, equity_value=r.equity_value,
        per_share_value=r.per_share_value, terminal_value=r.terminal_value,
        present_value_of_terminal_value=r.present_value_of_terminal_value,
        projections=[
            DcfProjectionYearSchema(year=p.year, projected_fcf=p.projected_fcf, present_value=p.present_value)
            for p in r.projections
        ],
    )


@router.get("/{ticker}/reverse-dcf", response_model=ReverseDcfResponseSchema)
def get_reverse_dcf(
    ticker: str,
    discount_rate: float = Query(default=0.10),
    terminal_growth_rate: float = Query(default=0.025),
    years: int = Query(default=5),
    use_case: ComputeReverseDcfUseCase = Depends(get_reverse_dcf_use_case),
) -> ReverseDcfResponseSchema:
    try:
        result = use_case.execute(
            ticker, discount_rate=discount_rate,
            terminal_growth_rate=terminal_growth_rate, years=years,
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DcfAssumptionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    a = result.assumptions
    return ReverseDcfResponseSchema(
        ticker=result.ticker, as_of=result.as_of, current_price=result.current_price,
        implied_growth_rate=result.implied_growth_rate,
        assumptions=ReverseDcfAssumptionsSchema(
            base_fcf=a.base_fcf, discount_rate=a.discount_rate,
            terminal_growth_rate=a.terminal_growth_rate, years=a.years,
            net_debt=a.net_debt, shares_outstanding=a.shares_outstanding,
        ),
    )


@router.get("/{ticker}/irr", response_model=IrrResponseSchema)
def get_irr(
    ticker: str,
    exit_price: float = Query(...),
    years: int = Query(...),
    entry_price: float | None = Query(default=None),
    annual_dividend_per_share: float = Query(default=0.0),
    use_case: ComputeInvestmentIrrUseCase = Depends(get_irr_use_case),
) -> IrrResponseSchema:
    try:
        result = use_case.execute(
            exit_price=exit_price, years=years, ticker=ticker,
            entry_price=entry_price, annual_dividend_per_share=annual_dividend_per_share,
        )
    except InvalidIrrScenarioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    s = result.scenario
    return IrrResponseSchema(
        ticker=result.ticker, as_of=result.as_of, irr=result.irr,
        scenario=IrrScenarioSchema(
            entry_price=s.entry_price, exit_price=s.exit_price, years=s.years,
            annual_dividend_per_share=s.annual_dividend_per_share, cash_flows=s.cash_flows,
        ),
    )


@router.get("/{ticker}/comps", response_model=CompsResponseSchema)
def get_comps(
    ticker: str,
    metric: CompsMetric = Query(default=CompsMetric.PE),
    use_case: ComputeCompsValuationUseCase = Depends(get_comps_use_case),
) -> CompsResponseSchema:
    try:
        assessment = use_case.execute(ticker, metric)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InsufficientPeerDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientTargetDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    r = assessment.result
    return CompsResponseSchema(
        ticker=assessment.ticker, as_of=assessment.as_of, metric=assessment.metric.value,
        peer_match_level=assessment.peer_match_level,
        peers_considered=assessment.peers_considered, peers_used=assessment.peers_used,
        peers_skipped=assessment.peers_skipped, peer_count=r.peer_count,
        median_multiple=r.median_multiple, mean_multiple=r.mean_multiple,
        implied_enterprise_value=r.implied_enterprise_value,
        implied_equity_value=r.implied_equity_value,
        implied_per_share_value=r.implied_per_share_value,
    )


# --- Screening ---------------------------------------------------------------

def get_screen_use_case(
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
    analysis_use_case: ComputeFinancialAnalysisUseCase = Depends(get_analysis_use_case),
) -> ScreenStocksUseCase:
    compute_valuation = ComputeValuationUseCase(
        GetCompanyFinancialsUseCase(company_repo, SqlAlchemyFinancialStatementRepository()), provider
    )
    return ScreenStocksUseCase(compute_valuation, analysis_use_case)


def get_theme_repository_for_screen() -> SqlAlchemyUniverseThemeRepository:
    return SqlAlchemyUniverseThemeRepository()


def get_theme_tickers_use_case_for_screen(
    theme_repo: SqlAlchemyUniverseThemeRepository = Depends(get_theme_repository_for_screen),
) -> GetThemeTickersUseCase:
    return GetThemeTickersUseCase(theme_repo)


@router.post("/screen", response_model=ScreenResultSchema)
def screen_stocks(
    body: ScreenRequestSchema,
    use_case: ScreenStocksUseCase = Depends(get_screen_use_case),
    theme_tickers_use_case: GetThemeTickersUseCase = Depends(get_theme_tickers_use_case_for_screen),
) -> ScreenResultSchema:
    """Screen against an explicit ticker list (capped 15) OR a named
    theme (capped 40) — the two ways this is used from chat, exposed
    identically here. Fixed-band scoring, a different methodology from
    factor-rankings — see scoring_note."""
    if body.theme_name:
        try:
            tickers = theme_tickers_use_case.execute(body.theme_name)[:40]
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        tickers = (body.tickers or [])[:15]

    if not tickers:
        raise HTTPException(
            status_code=422, detail="No tickers to screen — theme is empty or no tickers were provided."
        )

    result = use_case.execute(tickers)
    return ScreenResultSchema(
        scoring_note=(
            "LOWER score is ALWAYS better/more attractive for value_score, "
            "quality_score, and composite_score. A score of 1 means this "
            "ticker ranked BEST among the group screened; a higher score "
            "means it ranked worse."
        ),
        excluded=result.excluded,
        results=[
            ScreenedStockSchema(
                ticker=s.ticker, price=s.price, price_to_earnings=s.price_to_earnings,
                price_to_sales=s.price_to_sales, ev_to_ebitda=s.ev_to_ebitda,
                return_on_equity=s.return_on_equity, net_margin=s.net_margin,
                debt_to_equity=s.debt_to_equity, value_score=s.value_score,
                quality_score=s.quality_score, composite_score=s.composite_score,
            )
            for s in result.results
        ],
    )


# --- Per-ticker news ----------------------------------------------------------

@router.get("/{ticker}/news", response_model=list[NewsArticleSchema])
def get_ticker_news(
    ticker: str,
    limit: int = Query(default=10, ge=1, le=50),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> list[NewsArticleSchema]:
    if not hasattr(provider, "get_stock_news"):
        raise HTTPException(status_code=503, detail="This data provider does not support stock news.")
    try:
        articles = provider.get_stock_news(ticker, limit=limit)
    except (NotImplementedError, DataProviderError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return [
        NewsArticleSchema(
            ticker=a.ticker, title=a.title, published_at=a.published_at,
            source=a.source, url=a.url, snippet=a.snippet,
        )
        for a in articles
    ]


# --- Speculative growth assessment ("100x hunter") ---------------------------

from src.api.schemas import SpeculativeGrowthAssessmentSchema
from src.application.use_cases.assess_speculative_growth import (
    AssessSpeculativeGrowthUseCase,
)


def get_speculative_growth_use_case(
    get_financials: GetCompanyFinancialsUseCase = Depends(get_financials_use_case),
    compute_valuation: ComputeValuationUseCase = Depends(get_valuation_use_case),
) -> AssessSpeculativeGrowthUseCase:
    return AssessSpeculativeGrowthUseCase(get_financials, compute_valuation)


@router.get("/{ticker}/speculative-growth", response_model=SpeculativeGrowthAssessmentSchema)
def get_speculative_growth_assessment(
    ticker: str,
    use_case: AssessSpeculativeGrowthUseCase = Depends(get_speculative_growth_use_case),
) -> SpeculativeGrowthAssessmentSchema:
    """A deliberately different kind of analysis than /valuation or
    /factor-score — see AssessSpeculativeGrowthUseCase's own docstring
    for why standard factor scoring would actively work against
    finding genuine early-stage growth candidates. Never a single
    confidence score — always the structured breakdown plus explicit
    risk_flags, so nothing here can be mistaken for a recommendation."""
    try:
        result = use_case.execute(ticker)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return SpeculativeGrowthAssessmentSchema(
        ticker=result.ticker,
        as_of=result.as_of,
        market_cap=result.market_cap,
        revenue_growth_latest_yoy=result.revenue_growth_latest_yoy,
        revenue_growth_prior_yoy=result.revenue_growth_prior_yoy,
        growth_trend=result.growth_trend,
        is_profitable=result.is_profitable,
        net_income_latest=result.net_income_latest,
        cash_runway_months=result.cash_runway_months,
        years_of_data_available=result.years_of_data_available,
        risk_flags=result.risk_flags,
    )
