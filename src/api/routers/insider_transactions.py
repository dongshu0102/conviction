"""Form 3/4/5 insider transaction routes.

Genuinely different from institutional_holdings.py: there is no free,
structured SEC bulk data set for these forms (unlike Form 13F), so
there is no local database and no ingestion pipeline here at all --
every request is genuinely, always live against FMP's real, current
data. No "freshness fallback" concept applies, since there is no local
data to ever be stale relative to.

Deliberately platform-wide, not per-user — same rationale as
capital_flow.py, institutional_holdings.py, and beneficial_ownership.py:
this is public SEC data, identical for every user, so no
get_authenticated_user_id() dependency here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.schemas import InsiderTransactionSchema, InsiderTransactionsResponseSchema
from src.application.use_cases.get_insider_transactions import (
    GetInsiderTransactionsError,
    GetInsiderTransactionsUseCase,
)
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider

router = APIRouter(prefix="/insider-transactions", tags=["insider-transactions"])


def get_data_provider() -> FinancialModelingPrepProvider:
    return FinancialModelingPrepProvider(settings=get_settings())


def _to_schema(t) -> InsiderTransactionSchema:
    return InsiderTransactionSchema(
        filing_date=t.filing_date, transaction_date=t.transaction_date,
        reporting_cik=t.reporting_cik, company_cik=t.company_cik,
        reporting_name=t.reporting_name, type_of_owner=t.type_of_owner,
        transaction_type=t.transaction_type, acquisition_or_disposition=t.acquisition_or_disposition,
        direct_or_indirect=t.direct_or_indirect, security_name=t.security_name,
        securities_transacted=t.securities_transacted, securities_owned=t.securities_owned,
        price=t.price, source_url=t.source_url,
    )


@router.get("", response_model=InsiderTransactionsResponseSchema)
def get_transactions(
    ticker: str = Query(..., min_length=1, description="Ticker symbol, e.g. \"AAPL\"."),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> InsiderTransactionsResponseSchema:
    use_case = GetInsiderTransactionsUseCase(provider)
    try:
        result = use_case.execute(ticker)
    except GetInsiderTransactionsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return InsiderTransactionsResponseSchema(
        ticker=result.ticker,
        transactions=[_to_schema(t) for t in result.transactions],
    )
