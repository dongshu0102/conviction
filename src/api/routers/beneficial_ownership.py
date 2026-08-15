"""Schedule 13D/13G beneficial ownership disclosure routes.

Genuinely different from institutional_holdings.py: there is no free,
official SEC bulk data set for these schedules (unlike Form 13F), so
there is no local database and no ingestion pipeline here at all --
every request is genuinely, always live against FMP's real, current
data. No "freshness fallback" concept applies, since there is no local
data to ever be stale relative to.

Deliberately platform-wide, not per-user — same rationale as
capital_flow.py and institutional_holdings.py: this is public SEC
data, identical for every user, so no get_authenticated_user_id()
dependency here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.schemas import (
    BeneficialOwnershipDisclosureSchema,
    BeneficialOwnershipDisclosuresResponseSchema,
)
from src.application.use_cases.get_beneficial_ownership_disclosures import (
    GetBeneficialOwnershipDisclosuresError,
    GetBeneficialOwnershipDisclosuresUseCase,
)
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider

router = APIRouter(prefix="/beneficial-ownership", tags=["beneficial-ownership"])


def get_data_provider() -> FinancialModelingPrepProvider:
    return FinancialModelingPrepProvider(settings=get_settings())


def _to_schema(d) -> BeneficialOwnershipDisclosureSchema:
    return BeneficialOwnershipDisclosureSchema(
        cik=d.cik, filing_date=d.filing_date, accepted_date=d.accepted_date,
        cusip=d.cusip, name_of_reporting_person=d.name_of_reporting_person,
        citizenship_or_place_of_organization=d.citizenship_or_place_of_organization,
        sole_voting_power=d.sole_voting_power, shared_voting_power=d.shared_voting_power,
        sole_dispositive_power=d.sole_dispositive_power, shared_dispositive_power=d.shared_dispositive_power,
        amount_beneficially_owned=d.amount_beneficially_owned, percent_of_class=d.percent_of_class,
        type_of_reporting_person=d.type_of_reporting_person, form_type=d.form_type,
        source_url=d.source_url,
    )


@router.get("/disclosures", response_model=BeneficialOwnershipDisclosuresResponseSchema)
def get_disclosures(
    ticker: str = Query(..., min_length=1, description="Ticker symbol, e.g. \"AAPL\"."),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> BeneficialOwnershipDisclosuresResponseSchema:
    use_case = GetBeneficialOwnershipDisclosuresUseCase(provider)
    try:
        result = use_case.execute(ticker)
    except GetBeneficialOwnershipDisclosuresError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return BeneficialOwnershipDisclosuresResponseSchema(
        ticker=result.ticker,
        disclosures=[_to_schema(d) for d in result.disclosures],
    )
