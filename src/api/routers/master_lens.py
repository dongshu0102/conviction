"""Master Lens: ten historically significant investors, each applied
as a real analytical MODEL to a ticker's own, real financial data --
not a biography, not a quote generator. Every score is computed by
exact, deterministic arithmetic before the LLM is ever called; the LLM
only explains an already-fixed score through that investor's own
documented framework. See get_master_lens_analysis.py's own docstring
for the full grounding discipline.

Deliberately on-demand, not persisted -- computed fresh on every
request, one ticker at a time, matching the explicit scope chosen for
this feature's first version rather than a pre-computed,
whole-watchlist batch job.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.api.routers.companies import get_company_repository, get_statement_repository
from src.api.schemas import MasterLensAnalysisSchema, MasterLensResultSchema
from src.application.interfaces.master_lens_narrative_generator import MasterLensGenerationError
from src.application.use_cases.compute_financial_analysis import ComputeFinancialAnalysisUseCase
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.application.use_cases.get_master_lens_analysis import GetMasterLensAnalysisUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.llm_providers.anthropic_master_lens_narrative_generator import (
    AnthropicMasterLensNarrativeGenerator,
)
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.financial_statement_repository_impl import (
    SqlAlchemyFinancialStatementRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/master-lens", tags=["master-lens"])


def get_master_lens_narrative_generator() -> AnthropicMasterLensNarrativeGenerator:
    return AnthropicMasterLensNarrativeGenerator(settings=get_settings())


def get_master_lens_use_case(
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
    statement_repo: SqlAlchemyFinancialStatementRepository = Depends(get_statement_repository),
    narrative_generator: AnthropicMasterLensNarrativeGenerator = Depends(get_master_lens_narrative_generator),
) -> GetMasterLensAnalysisUseCase:
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    provider = FinancialModelingPrepProvider(settings=get_settings())
    compute_valuation = ComputeValuationUseCase(get_financials, provider)
    return GetMasterLensAnalysisUseCase(compute_analysis, compute_valuation, narrative_generator)


@router.get("/{ticker}", response_model=MasterLensAnalysisSchema)
def get_master_lens_analysis(
    ticker: str,
    use_case: GetMasterLensAnalysisUseCase = Depends(get_master_lens_use_case),
) -> MasterLensAnalysisSchema:
    try:
        analysis = use_case.execute(ticker)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MasterLensGenerationError as exc:
        logger.warning("Master Lens narrative generation failed for %s: %s", ticker, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return MasterLensAnalysisSchema(
        ticker=analysis.ticker,
        generated_at=analysis.generated_at,
        model_used=analysis.model_used,
        results=[
            MasterLensResultSchema(
                master_name=r.master_name, lens_label=r.lens_label,
                score=r.score, score_basis=r.score_basis, narrative=r.narrative,
            )
            for r in analysis.results
        ],
    )
