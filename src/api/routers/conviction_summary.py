"""Conviction Summary -- combines three genuinely independent SEC
disclosure regimes (13F institutional accumulation, 13D activist
intent, and Form 4 insider buying) into one, honest summary for a
single ticker.

Deliberately platform-wide, not per-user, same rationale as
institutional_holdings.py, beneficial_ownership.py, and
insider_transactions.py: this is public SEC/market data, identical for
every user.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.api.schemas import (
    BeneficialOwnershipDisclosureSchema,
    ConvictionSummaryResponseSchema,
    InsiderTransactionSchema,
    InstitutionalHolderSignalSchema,
)
from src.application.use_cases.detect_position_changes import DetectPositionChangesUseCase
from src.application.use_cases.get_beneficial_ownership_disclosures import (
    GetBeneficialOwnershipDisclosuresUseCase,
)
from src.application.use_cases.get_conviction_summary import GetConvictionSummaryUseCase
from src.application.use_cases.get_insider_transactions import GetInsiderTransactionsUseCase
from src.application.use_cases.get_institutional_holders import GetInstitutionalHoldersUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.institutional_holding_repository_impl import (
    SqlAlchemyInstitutionalHoldingRepository,
)

router = APIRouter(prefix="/conviction-summary", tags=["conviction-summary"])


def get_data_provider() -> FinancialModelingPrepProvider:
    return FinancialModelingPrepProvider(settings=get_settings())


def get_conviction_summary_use_case(
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> GetConvictionSummaryUseCase:
    repository = SqlAlchemyInstitutionalHoldingRepository()
    return GetConvictionSummaryUseCase(
        get_institutional_holders=GetInstitutionalHoldersUseCase(repository, provider),
        detect_position_changes=DetectPositionChangesUseCase(repository, provider),
        get_beneficial_ownership_disclosures=GetBeneficialOwnershipDisclosuresUseCase(provider),
        get_insider_transactions=GetInsiderTransactionsUseCase(provider),
        company_repository=SqlAlchemyCompanyRepository(),
    )


@router.get("", response_model=ConvictionSummaryResponseSchema)
def get_conviction_summary(
    ticker: str = Query(..., min_length=1, description="Ticker symbol, e.g. \"AAPL\"."),
    use_case: GetConvictionSummaryUseCase = Depends(get_conviction_summary_use_case),
) -> ConvictionSummaryResponseSchema:
    result = use_case.execute(ticker)

    return ConvictionSummaryResponseSchema(
        ticker=result.ticker,
        institutional_holders=[
            InstitutionalHolderSignalSchema(
                filer_name=h.filer_name, current_shares=h.current_shares,
                current_value_usd=h.current_value_usd, is_increasing=h.is_increasing,
            )
            for h in result.institutional_holders
        ],
        institutional_signal=result.institutional_signal,
        activist_disclosures_13d=[
            BeneficialOwnershipDisclosureSchema(
                cik=d.cik, filing_date=d.filing_date, accepted_date=d.accepted_date,
                cusip=d.cusip, name_of_reporting_person=d.name_of_reporting_person,
                citizenship_or_place_of_organization=d.citizenship_or_place_of_organization,
                sole_voting_power=d.sole_voting_power, shared_voting_power=d.shared_voting_power,
                sole_dispositive_power=d.sole_dispositive_power, shared_dispositive_power=d.shared_dispositive_power,
                amount_beneficially_owned=d.amount_beneficially_owned, percent_of_class=d.percent_of_class,
                type_of_reporting_person=d.type_of_reporting_person, form_type=d.form_type,
                source_url=d.source_url,
            )
            for d in result.activist_disclosures_13d
        ],
        activist_signal=result.activist_signal,
        insider_purchases=[
            InsiderTransactionSchema(
                filing_date=t.filing_date, transaction_date=t.transaction_date,
                reporting_cik=t.reporting_cik, company_cik=t.company_cik,
                reporting_name=t.reporting_name, type_of_owner=t.type_of_owner,
                transaction_type=t.transaction_type, acquisition_or_disposition=t.acquisition_or_disposition,
                direct_or_indirect=t.direct_or_indirect, security_name=t.security_name,
                securities_transacted=t.securities_transacted, securities_owned=t.securities_owned,
                price=t.price, source_url=t.source_url,
            )
            for t in result.insider_purchases
        ],
        insider_signal=result.insider_signal,
        signal_count=result.signal_count,
    )
