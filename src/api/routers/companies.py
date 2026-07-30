from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.schemas import (
    BalanceSheetSchema,
    CashFlowStatementSchema,
    CompanyFinancialAnalysisSchema,
    CompanyFinancialsSchema,
    CompanySchema,
    IncomeStatementSchema,
    IngestResultSchema,
    SP500ConstituentsSchema,
    ValuationSnapshotSchema,
    YearlyRatiosSchema,
)
from src.application.interfaces.data_provider import DataProviderError
from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_valuation import (
    ComputeValuationUseCase,
    NoFinancialDataError as NoValuationDataError,
)
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.application.use_cases.ingest_company_data import IngestCompanyDataUseCase
from src.domain.entities.financial_statement import Period
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.company_repository_impl import (
    SqlAlchemyCompanyRepository,
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
